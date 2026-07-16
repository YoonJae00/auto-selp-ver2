import os
import asyncio
import json
import time
import uuid
import logging
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request, Header
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Dict, Optional, List
from celery.result import AsyncResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, text, delete
from sqlalchemy.orm import selectinload
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import io
import urllib.parse
from collections import Counter
from datetime import datetime

from tasks import process_excel_task, process_db_products_task
from celery_app import celery_app
from database import get_db, engine, Base
from models import Prompt, ProcessingTask, ProductImport, Product, ProductPlatformMapping, WholesaleSite
from schemas import (
    ProcessRequest, 
    PromptUpdate, 
    PromptResponse, 
    DBProcessRequest, 
    ProductListResponse,
    ProductStatsResponse,
    ProductResponse,
    ProductImportResponse,
    WholesaleSiteCreate,
    WholesaleSiteUpdate,
    WholesaleSiteResponse,
    MarketplaceSnapshotResponse,
    MarketplaceNameRequest,
    MarketplaceNameResponse,
    ProductDeleteRequest,
    ProductDeleteResponse,
    WholesaleMappingSuggestionRequest,
    WholesaleMappingPreviewRequest,
)
from utils.prompt_manager import PromptManager
from utils.wholesale_upload import (
    STANDARD_PRODUCT_EXAMPLE,
    build_mapping_preview,
    json_safe_row,
    parse_wholesale_row,
    sanitize_column_mapping,
    validate_required_mappings,
)
from utils.product_name import select_product_name
from clients.llm_factory import get_llm_client
from clients.marketplace_client import MarketplaceClient
from clients.openai_client import OpenAIClient
from config import settings

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Auto-Selp Product Processor")
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

from init_prompts import seed_prompts

@app.on_event("startup")
async def startup():
    await seed_prompts()

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# --- JWT Auth Dependency ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


def apply_product_sort(stmt, sort_by: Optional[str], sort_order: str):
    if sort_by == "price_wholesale":
        sort_column = Product.price_wholesale
        if sort_order == "asc":
            return stmt.order_by(sort_column.asc().nullslast(), Product.created_at.desc())
        return stmt.order_by(sort_column.desc().nullslast(), Product.created_at.desc())
    if sort_by == "option_count":
        option_count = func.coalesce(func.json_array_length(Product.option_variants), 0)
        if sort_order == "asc":
            return stmt.order_by(option_count.asc(), Product.created_at.desc())
        return stmt.order_by(option_count.desc(), Product.created_at.desc())

    return stmt.order_by(Product.created_at.desc())


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    token = request.cookies.get("access_token") or token
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Query the 'users' table directly to avoid circular model mapping
    result = await db.execute(
        text("SELECT id, username, is_admin FROM users WHERE username = :username"),
        {"username": username}
    )
    user = result.fetchone()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}


async def require_task_owner(task_id: str, user_id: uuid.UUID, db: AsyncSession):
    result = await db.execute(
        select(ProcessingTask.task_id).where(
            and_(ProcessingTask.task_id == task_id, ProcessingTask.user_id == user_id)
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Task not found.")


def require_internal_service_token(
    internal_token: str | None = Header(default=None, alias="X-Internal-Service-Token")
):
    if internal_token != settings.INTERNAL_SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid internal service token")


# --- Wholesale Sites API ---


async def require_wholesale_site(site_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession):
    result = await db.execute(
        select(WholesaleSite).where(
            and_(WholesaleSite.id == site_id, WholesaleSite.user_id == user_id)
        )
    )
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail="Wholesale site not found")
    return site


def get_uploaded_file_path(file_id: str) -> str:
    files = [filename for filename in os.listdir(UPLOAD_DIR) if filename.startswith(f"{file_id}_")]
    if not files:
        raise HTTPException(status_code=404, detail="File not found.")
    return os.path.join(UPLOAD_DIR, files[0])


def read_mapping_sample(file_id: str) -> pd.DataFrame:
    try:
        return pd.read_excel(get_uploaded_file_path(file_id), nrows=5)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"Failed to read excel: {error}")


def mapping_preview_response(
    dataframe: pd.DataFrame,
    mapping: dict,
    notes: list[str] | None = None,
    mapping_warnings: list[str] | None = None,
):
    preview, row_warnings = build_mapping_preview(dataframe, mapping)
    warnings = [{"message": warning} for warning in (mapping_warnings or [])] + row_warnings
    missing = validate_required_mappings(mapping, list(dataframe.columns))
    if missing:
        warnings.append({"message": f"Required mappings are missing: {', '.join(missing)}"})
    return {
        "column_mapping": mapping,
        "preview": preview,
        "standard_example": STANDARD_PRODUCT_EXAMPLE,
        "warnings": warnings,
        "notes": notes or [],
    }

@app.post("/wholesale-sites", response_model=WholesaleSiteResponse)
async def create_wholesale_site(
    site: WholesaleSiteCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    new_site = WholesaleSite(
        id=uuid.uuid4(),
        user_id=current_user["id"],
        name=site.name,
        homepage_url=site.homepage_url,
        column_mapping=site.column_mapping
    )
    db.add(new_site)
    await db.commit()
    await db.refresh(new_site)
    return new_site

@app.get("/wholesale-sites", response_model=List[WholesaleSiteResponse])
async def list_wholesale_sites(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(WholesaleSite).where(WholesaleSite.user_id == current_user["id"]).order_by(WholesaleSite.created_at.desc())
    )
    return result.scalars().all()

@app.get("/wholesale-sites/{site_id}", response_model=WholesaleSiteResponse)
async def get_wholesale_site(
    site_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(WholesaleSite).where(
            and_(WholesaleSite.id == site_id, WholesaleSite.user_id == current_user["id"])
        )
    )
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail="Wholesale site not found")
    return site

@app.put("/wholesale-sites/{site_id}", response_model=WholesaleSiteResponse)
async def update_wholesale_site(
    site_id: uuid.UUID,
    site_data: WholesaleSiteUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(WholesaleSite).where(
            and_(WholesaleSite.id == site_id, WholesaleSite.user_id == current_user["id"])
        )
    )
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail="Wholesale site not found")
    
    if site_data.name is not None:
        site.name = site_data.name
    if site_data.homepage_url is not None:
        site.homepage_url = site_data.homepage_url
    if site_data.column_mapping is not None:
        site.column_mapping = site_data.column_mapping
        
    await db.commit()
    await db.refresh(site)
    return site

@app.delete("/wholesale-sites/{site_id}")
async def delete_wholesale_site(
    site_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(WholesaleSite).where(
            and_(WholesaleSite.id == site_id, WholesaleSite.user_id == current_user["id"])
        )
    )
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail="Wholesale site not found")
        
    await db.delete(site)
    await db.commit()
    return {"status": "success"}


@app.post("/wholesale-sites/{site_id}/mapping-suggestion")
async def suggest_wholesale_site_mapping(
    site_id: uuid.UUID,
    request: WholesaleMappingSuggestionRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    site = await require_wholesale_site(site_id, current_user["id"], db)
    dataframe = read_mapping_sample(request.file_id)
    current_mapping = {**(site.column_mapping or {}), **(request.column_mapping or {})}
    sample_rows = []
    for _, row in dataframe.iterrows():
        sample_rows.append({
            str(key): str(value)[:1_000]
            for key, value in json_safe_row(row).items()
        })
    try:
        suggestion = await OpenAIClient().suggest_wholesale_mapping(
            [str(column) for column in dataframe.columns],
            sample_rows,
            current_mapping,
            request.instruction,
        )
    except Exception as error:
        logger.error("OpenAI wholesale mapping suggestion failed: %s", error)
        raise HTTPException(status_code=502, detail="Could not generate a mapping suggestion.")

    logger.info(
        "Wholesale mapping suggestion for site %s (instruction=%r): %s",
        site_id,
        request.instruction,
        json.dumps(suggestion["column_mapping"], ensure_ascii=False),
    )
    proposed_mapping = {**current_mapping, **suggestion["column_mapping"]}
    sanitized, mapping_warnings = sanitize_column_mapping(
        proposed_mapping,
        [str(column) for column in dataframe.columns],
    )
    return mapping_preview_response(
        dataframe,
        sanitized,
        notes=suggestion.get("notes", []),
        mapping_warnings=mapping_warnings,
    )


@app.post("/wholesale-sites/{site_id}/mapping-preview")
async def preview_wholesale_site_mapping(
    site_id: uuid.UUID,
    request: WholesaleMappingPreviewRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_wholesale_site(site_id, current_user["id"], db)
    dataframe = read_mapping_sample(request.file_id)
    sanitized, mapping_warnings = sanitize_column_mapping(
        request.column_mapping,
        [str(column) for column in dataframe.columns],
    )
    return mapping_preview_response(dataframe, sanitized, mapping_warnings=mapping_warnings)




# --- Excel Preview & File Upload ---

@app.post("/upload")
async def upload_excel(file: UploadFile = File(...)):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only Excel files are allowed.")
    
    file_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())
    
    try:
        df = pd.read_excel(file_path, nrows=5)
        # Handle NaN values which are not JSON compliant
        df = df.fillna("")
        columns = df.columns.tolist()
        preview = df.to_dict(orient="records")
        return {
            "file_id": file_id,
            "filename": file.filename,
            "columns": columns,
            "preview": preview
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read excel: {e}")


# --- Legacy Processing Endpoints (For compatibility) ---

@app.post("/process")
async def start_processing(request: ProcessRequest):
    files = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(request.file_id)]
    if not files:
        raise HTTPException(status_code=404, detail="File not found.")
    
    file_path = os.path.join(UPLOAD_DIR, files[0])
    task = process_excel_task.delay(
        file_path,
        request.column_mapping,
        request.llm_provider,
        request.kipris_enabled,
        request.vision_llm_provider,
    )
    return {"task_id": task.id}


# --- New DB-Backed Processing Endpoints ---

CANONICAL_IMPORT_FIELDS = (
    "wholesale_product_id",
    "original_name",
    "price_wholesale",
    "price_wholesale_raw",
    "price_retail",
    "price_min_selling",
    "origin",
    "option_values_raw",
    "option_variants",
    "standard_options",
    "images_list",
    "image_detail",
    "wholesale_status",
    "wholesale_registered_at",
)

# Fields whose change actually requires re-running the AI pipeline; other changes
# (price/stock/etc.) are data-only and reflected without reprocessing.
REPROCESS_TRIGGER_FIELDS = {"original_name", "images_list", "image_detail"}
# JSON-typed fields: record only that they changed, not the full blob.
_JSON_CHANGE_FIELDS = {"option_variants", "standard_options", "images_list"}

@app.post("/process-db")
async def start_db_processing(
    request: ProcessRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    file_path = get_uploaded_file_path(request.file_id)
    filename = os.path.basename(file_path).split("_", 1)[1]
    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read excel: {e}")
    
    col_mapping = dict(request.column_mapping)
    if request.wholesale_site_id:
        site = await require_wholesale_site(request.wholesale_site_id, current_user["id"], db)
        if site.column_mapping:
            col_mapping = {**site.column_mapping, **col_mapping}

    col_mapping, _ = sanitize_column_mapping(col_mapping, [str(column) for column in df.columns])

    missing_required = validate_required_mappings(col_mapping, list(df.columns))
    if missing_required:
        raise HTTPException(
            status_code=400,
            detail=f"Required mapped columns missing in excel: {', '.join(missing_required)}",
        )

    parsed_rows = []
    for _, row in df.iterrows():
        parsed_row = parse_wholesale_row(row, col_mapping)
        product_data = parsed_row["product_data"]
        row_warnings = parsed_row["warnings"]
        product_warnings = (
            {"warnings": row_warnings, "supplier_warnings": row_warnings}
            if row_warnings
            else None
        )
        parsed_rows.append((product_data, product_warnings))

    duplicate_codes = [
        code
        for code, count in Counter(
            product_data["product_code"]
            for product_data, _ in parsed_rows
            if product_data["product_code"]
        ).items()
        if count > 1
    ]
    if duplicate_codes:
        sample = ", ".join(duplicate_codes[:10])
        suffix = " ..." if len(duplicate_codes) > 10 else ""
        raise HTTPException(
            status_code=400,
            detail=f"Duplicate product_code values in excel: {sample}{suffix}",
        )

    product_codes = {
        product_data["product_code"]
        for product_data, _ in parsed_rows
        if product_data["product_code"]
    }
    existing_by_code = {}
    if product_codes:
        site_filter = (
            Product.wholesale_site_id == request.wholesale_site_id
            if request.wholesale_site_id
            else Product.wholesale_site_id.is_(None)
        )
        existing_result = await db.execute(
            select(Product)
            .where(
                Product.user_id == current_user["id"],
                site_filter,
                Product.product_code.in_(product_codes),
            )
            .options(selectinload(Product.platform_mappings))
        )
        existing_by_code = {
            product.product_code: product for product in existing_result.scalars().all()
        }

    import_id = uuid.uuid4()
    import_run = ProductImport(
        id=import_id,
        user_id=current_user["id"],
        filename=filename,
        total_count=0,
        status="pending",
    )
    db.add(import_run)
    new_count = updated_count = unchanged_count = reprocess_count = 0

    for product_data, product_warnings in parsed_rows:
        product_code = product_data["product_code"]
        existing_product = existing_by_code.get(product_code) if product_code else None
        if existing_product:
            changed_fields = []
            field_changes = {}
            for field_name in CANONICAL_IMPORT_FIELDS:
                old_value = getattr(existing_product, field_name)
                new_value = product_data[field_name]
                if old_value != new_value:
                    changed_fields.append(field_name)
                    field_changes[field_name] = (
                        {"old": None, "new": None}
                        if field_name in _JSON_CHANGE_FIELDS
                        else {"old": old_value, "new": new_value}
                    )
            if not changed_fields:
                unchanged_count += 1
                continue

            needs_reprocess = existing_product.status != "completed" or any(
                field_name in changed_fields for field_name in REPROCESS_TRIGGER_FIELDS
            )

            for field_name in CANONICAL_IMPORT_FIELDS:
                setattr(existing_product, field_name, product_data[field_name])
            existing_product.options = product_data["option_values_raw"]
            existing_product.import_id = import_id
            if needs_reprocess:
                existing_product.status = "pending"
            existing_product.change_type = "updated"
            existing_product.changed_fields = changed_fields
            existing_product.field_changes = field_changes
            existing_product.warnings = product_warnings
            existing_product.raw_metadata = product_data["raw_metadata"]

            changed_at = datetime.utcnow()
            for platform_mapping in existing_product.platform_mappings:
                platform_mapping.sync_status = "pending_update"
                platform_mapping.last_changed_at = changed_at
                if any(
                    field_name in changed_fields
                    for field_name in ("price_wholesale", "price_wholesale_raw", "option_variants", "standard_options")
                ):
                    platform_mapping.price_changed = True
                if "wholesale_status" in changed_fields:
                    platform_mapping.stock_changed = True
            updated_count += 1
            if needs_reprocess:
                reprocess_count += 1
        else:
            product = Product(
                user_id=current_user["id"],
                import_id=import_id,
                wholesale_site_id=request.wholesale_site_id,
                product_code=product_code,
                options=product_data["option_values_raw"],
                status="pending",
                change_type="new",
                changed_fields=[],
                field_changes=None,
                warnings=product_warnings,
                raw_metadata=product_data["raw_metadata"],
                **{field_name: product_data[field_name] for field_name in CANONICAL_IMPORT_FIELDS},
            )
            db.add(product)
            if product_code:
                existing_by_code[product_code] = product
            new_count += 1
            reprocess_count += 1

    # 단종(discontinued): supplier-scoped products absent from this ledger.
    removed_count = 0
    if request.wholesale_site_id:
        removed_conditions = [
            Product.user_id == current_user["id"],
            Product.wholesale_site_id == request.wholesale_site_id,
            Product.product_code.isnot(None),
            Product.product_code != "",
            Product.change_type.is_distinct_from("removed"),
        ]
        if product_codes:
            removed_conditions.append(Product.product_code.notin_(product_codes))
        removed_result = await db.execute(
            select(Product).where(*removed_conditions).options(selectinload(Product.platform_mappings))
        )
        removed_at = datetime.utcnow()
        for product in removed_result.scalars().all():
            product.field_changes = {"wholesale_status": {"old": product.wholesale_status, "new": "단종"}}
            product.wholesale_status = "단종"
            product.change_type = "removed"
            product.changed_fields = ["wholesale_status"]
            for platform_mapping in product.platform_mappings:
                platform_mapping.sync_status = "pending_update"
                platform_mapping.stock_changed = True
                platform_mapping.last_changed_at = removed_at
            removed_count += 1

    import_run.total_count = reprocess_count

    if not request.start_processing:
        import_run.status = "imported"
        await db.commit()
        return {
            "task_id": None,
            "import_id": import_id,
            "total": reprocess_count,
            "new_count": new_count,
            "updated_count": updated_count,
            "unchanged_count": unchanged_count,
            "removed_count": removed_count,
            "reprocessed_count": reprocess_count,
        }

    if reprocess_count == 0:
        import_run.status = "completed"
        await db.commit()
        return {
            "task_id": None,
            "import_id": import_id,
            "total": 0,
            "new_count": new_count,
            "updated_count": updated_count,
            "unchanged_count": unchanged_count,
            "removed_count": removed_count,
            "reprocessed_count": 0,
        }

    await db.commit()

    # 3. Celery 비동기 태스크 시작
    task = process_db_products_task.delay(
        str(import_id),
        col_mapping,
        request.llm_provider,
        request.kipris_enabled,
        None,
        request.vision_llm_provider,
    )
    db.add(ProcessingTask(task_id=task.id, user_id=current_user["id"]))
    await db.commit()

    return {
        "task_id": task.id,
        "import_id": import_id,
        "total": reprocess_count,
        "new_count": new_count,
        "updated_count": updated_count,
        "unchanged_count": unchanged_count,
        "removed_count": removed_count,
        "reprocessed_count": reprocess_count,
    }


@app.post("/process-products")
async def start_selected_products_processing(
    request: DBProcessRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not request.product_ids and not request.import_id:
        raise HTTPException(status_code=400, detail="Select products or provide an import_id.")

    product_ids = [str(pid) for pid in (request.product_ids or [])]
    total = 0
    filename = "선택 상품 가공"

    if product_ids:
        result = await db.execute(
            select(Product.id).where(
                and_(
                    Product.user_id == current_user["id"],
                    Product.id.in_(request.product_ids),
                )
            )
        )
        owned_ids = [str(pid) for pid in result.scalars().all()]
        if len(owned_ids) != len(product_ids):
            raise HTTPException(status_code=404, detail="Some selected products were not found.")
        total = len(owned_ids)
        product_ids = owned_ids
    elif request.import_id:
        import_result = await db.execute(
            select(ProductImport).where(
                and_(
                    ProductImport.id == request.import_id,
                    ProductImport.user_id == current_user["id"],
                )
            )
        )
        import_run = import_result.scalar_one_or_none()
        if not import_run:
            raise HTTPException(status_code=404, detail="Import run not found.")
        filename = import_run.filename
        total_result = await db.execute(
            select(func.count(Product.id)).where(
                and_(
                    Product.user_id == current_user["id"],
                    Product.import_id == request.import_id,
                    Product.status != "completed",
                )
            )
        )
        total = total_result.scalar() or 0

    task = process_db_products_task.delay(
        str(request.import_id) if request.import_id else None,
        request.column_mapping,
        request.llm_provider,
        request.kipris_enabled,
        product_ids or None,
        request.vision_llm_provider,
    )
    db.add(ProcessingTask(task_id=task.id, user_id=current_user["id"]))
    await db.commit()

    return {
        "task_id": task.id,
        "import_id": request.import_id,
        "filename": filename,
        "total": total
    }


@app.get("/products", response_model=ProductListResponse)
async def list_products(
    page: int = 1,
    size: int = 20,
    search: Optional[str] = None,
    status: Optional[str] = None,
    import_id: Optional[uuid.UUID] = None,
    wholesale_site_id: Optional[uuid.UUID] = None,
    needs_sync: Optional[bool] = None,
    sort_by: Optional[str] = None,
    sort_order: str = "desc",
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Product).where(Product.user_id == current_user["id"]).options(
        selectinload(Product.platform_mappings)
    )
    
    filters = []
    if search:
        filters.append(Product.original_name.ilike(f"%{search}%"))
    if status:
        filters.append(Product.status == status)
    if import_id:
        filters.append(Product.import_id == import_id)
    if wholesale_site_id:
        filters.append(Product.wholesale_site_id == wholesale_site_id)
        
    if filters:
        stmt = stmt.where(and_(*filters))
        
    if needs_sync:
        stmt = stmt.join(ProductPlatformMapping).where(ProductPlatformMapping.sync_status == "pending_update")
        
    # Count total
    count_stmt = select(func.count(Product.id)).select_from(Product).where(Product.user_id == current_user["id"])
    if filters:
        count_stmt = count_stmt.where(and_(*filters))
    if needs_sync:
        count_stmt = count_stmt.join(ProductPlatformMapping).where(ProductPlatformMapping.sync_status == "pending_update")
        
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0
    
    stmt = apply_product_sort(stmt, sort_by, sort_order).offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    items = result.scalars().all()
    
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": items
    }


@app.get("/products/stats", response_model=ProductStatsResponse)
async def product_stats(
    wholesale_site_id: Optional[uuid.UUID] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    site_filter = [Product.wholesale_site_id == wholesale_site_id] if wholesale_site_id else []

    status_stmt = (
        select(Product.status, func.count())
        .where(Product.user_id == current_user["id"], *site_filter)
        .group_by(Product.status)
    )
    status_result = await db.execute(status_stmt)
    counts = {status: count for status, count in status_result.all()}

    named_stmt = (
        select(func.count())
        .select_from(ProductPlatformMapping)
        .join(Product, ProductPlatformMapping.product_id == Product.id)
        .where(
            ProductPlatformMapping.platform_name == "naver",
            ProductPlatformMapping.product_name.isnot(None),
            Product.user_id == current_user["id"],
            *site_filter
        )
    )
    named_result = await db.execute(named_stmt)

    return {
        "total": sum(counts.values()),
        "pending": counts.get("pending", 0),
        "processing": counts.get("processing", 0),
        "completed": counts.get("completed", 0),
        "failed": counts.get("failed", 0),
        "smartstore_named": named_result.scalar() or 0
    }


@app.post("/products/generate-marketplace-names", response_model=MarketplaceNameResponse)
async def generate_marketplace_names(
    request: MarketplaceNameRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    request_started = time.perf_counter()
    product_ids = list(dict.fromkeys(request.product_ids))
    result = await db.execute(
        select(Product)
        .where(and_(Product.user_id == current_user["id"], Product.id.in_(product_ids)))
        .options(selectinload(Product.platform_mappings))
    )
    products = result.scalars().all()
    if len(products) != len(product_ids):
        raise HTTPException(status_code=404, detail="Some selected products were not found.")
    if any(product.status != "completed" or not product.refined_name or not product.keywords for product in products):
        raise HTTPException(status_code=422, detail="Selected products must have completed processing results.")

    prompt_manager = PromptManager(db)
    try:
        llm_client = get_llm_client(request.llm_provider, prompt_manager)
    except Exception as error:
        logger.error("Could not initialize %s for Smartstore names: %s", request.llm_provider, error)
        llm_client = None
    contexts = []
    for product in products:
        mapping = next(
            (item for item in product.platform_mappings if item.platform_name == "naver"), None
        )
        if mapping is None:
            mapping = ProductPlatformMapping(product_id=product.id, platform_name="naver")
            db.add(mapping)
        contexts.append({
            "product": product,
            "mapping": mapping,
            "refined_name": product.refined_name,
            "keywords": product.keywords,
            "brand_name": product.brand_name,
            "original_name": product.original_name,
            "category_path": mapping.category_path,
        })

    # ponytail: fixed concurrency fits HTTP batches; move to a queue if request timeouts become common.
    semaphore = asyncio.Semaphore(4)

    async def generate_candidates(context):
        if llm_client is None:
            return [], 0
        async with semaphore:
            llm_started = time.perf_counter()
            try:
                candidates = await llm_client.generate_smartstore_name_candidates(
                    context["refined_name"],
                    context["keywords"],
                    context["brand_name"],
                    context["category_path"],
                )
            except Exception as error:
                logger.error("Smartstore candidate generation failed for %s: %s", context["product"].id, error)
                candidates = []
            return candidates, int((time.perf_counter() - llm_started) * 1000)

    candidate_results = await asyncio.gather(*(generate_candidates(context) for context in contexts))

    items = []
    for context, (candidates, llm_ms) in zip(contexts, candidate_results):
        product = context["product"]
        mapping = context["mapping"]
        validation_started = time.perf_counter()
        product_name, used_llm = select_product_name(
            candidates,
            context["keywords"],
            context["refined_name"],
            context["brand_name"],
            context["original_name"],
        )
        validation_ms = int((time.perf_counter() - validation_started) * 1000)
        if not product_name:
            raise HTTPException(status_code=422, detail="Could not generate a marketplace product name.")
        mapping.product_name = product_name
        product.updated_at = datetime.utcnow()
        items.append({
            "product_id": product.id,
            "original_name": product.original_name,
            "candidates": candidates,
            "product_name": mapping.product_name,
            "generation_method": "llm" if used_llm else "fallback",
            "llm_ms": llm_ms,
            "validation_ms": validation_ms,
            "total_ms": llm_ms + validation_ms,
        })

    await db.commit()

    marketplace_client = MarketplaceClient()
    for product in products:
        try:
            await marketplace_client.request_draft_generation(product)
        except Exception as error:
            logger.error("Failed to request marketplace draft generation for %s: %s", product.id, error)

    return {
        "generated_count": len(items),
        "items": items,
        "processing_time_ms": int((time.perf_counter() - request_started) * 1000),
    }


@app.get("/internal/products/{product_id}/marketplace-snapshot", response_model=MarketplaceSnapshotResponse)
async def get_marketplace_snapshot(
    product_id: uuid.UUID,
    user_id: uuid.UUID,
    _: None = Depends(require_internal_service_token),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Product)
        .where(and_(Product.id == product_id, Product.user_id == user_id))
        .options(selectinload(Product.platform_mappings))
    )
    result = await db.execute(stmt)
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    platform_mappings = product.platform_mappings or []
    has_explicit_smartstore = any(mapping.platform_name == "smartstore" for mapping in platform_mappings)

    market_categories = {}
    for mapping in platform_mappings:
        if has_explicit_smartstore and mapping.platform_name == "naver":
            continue
        platform_name = "smartstore" if mapping.platform_name == "naver" else mapping.platform_name
        market_categories[platform_name] = {
            "category_id": mapping.category_id,
            "category_path": mapping.category_path,
            "product_name": getattr(mapping, "product_name", None),
            "mapped_attributes": mapping.mapped_attributes,
        }

    return {
        "product_id": product.id,
        "version": product.updated_at.isoformat(),
        "product_code": product.product_code,
        "wholesale_product_id": product.wholesale_product_id,
        "original_name": product.original_name,
        "refined_name": product.refined_name,
        "brand_name": product.brand_name,
        "keywords": product.keywords or [],
        "origin": product.origin,
        "price": {
            "wholesale": product.price_wholesale,
            "retail": product.price_retail,
            "minimum_selling": product.price_min_selling,
        },
        "images": {
            "list": product.images_list or [],
            "detail_content": product.image_detail,
        },
        "options": product.option_variants or [],
        "standard_options": product.standard_options or [],
        "market_categories": market_categories,
    }


@app.post("/products/export")
async def export_products(
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    product_ids = request.get("product_ids", [])
    
    stmt = select(Product).where(Product.user_id == current_user["id"]).options(
        selectinload(Product.platform_mappings)
    )
    
    if product_ids:
        uuid_ids = [uuid.UUID(pid) for pid in product_ids]
        stmt = stmt.where(Product.id.in_(uuid_ids))
    else:
        stmt = stmt.where(Product.status == "completed")
        
    result = await db.execute(stmt)
    products = result.scalars().all()
    
    if not products:
        raise HTTPException(status_code=404, detail="No products found to export")
        
    data = []
    for p in products:
        kws_str = ", ".join(p.keywords) if p.keywords else ""
        
        naver_cat = ""
        coupang_cat = ""
        for m in p.platform_mappings:
            if m.platform_name == "naver":
                naver_cat = m.category_id or m.category_path or ""
            elif m.platform_name == "coupang":
                coupang_cat = m.category_id or ""
                
        row_data = {
            "상품고유ID": str(p.id),
            "원래상품명": p.original_name,
            "정제상품명": p.refined_name or "",
            "키워드": kws_str,
            "네이버카테고리": naver_cat,
            "쿠팡카테고리": coupang_cat,
            "가공상태": p.status,
            "등록일": p.created_at.strftime("%Y-%m-%d %H:%M:%S")
        }
        data.append(row_data)
        
    df = pd.DataFrame(data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="가공상품목록")
    output.seek(0)
    
    filename = "exported_products.xlsx"
    headers = {
        'Content-Disposition': f'attachment; filename="{urllib.parse.quote(filename)}"'
    }
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )


@app.post("/products/delete", response_model=ProductDeleteResponse)
async def delete_products(
    req: ProductDeleteRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not req.product_ids and not req.wholesale_site_id:
        return ProductDeleteResponse(
            success=False,
            deleted_count=0,
            message="삭제 대상(product_ids 또는 wholesale_site_id)을 입력해주세요."
        )

    # 1. Resolve product targets belonging to current user
    target_stmt = select(Product.id).where(Product.user_id == current_user["id"])
    if req.product_ids:
        target_stmt = target_stmt.where(Product.id.in_(req.product_ids))
    elif req.wholesale_site_id:
        target_stmt = target_stmt.where(Product.wholesale_site_id == req.wholesale_site_id)

    res = await db.execute(target_stmt)
    target_ids = [row[0] for row in res.all()]

    if not target_ids:
        return ProductDeleteResponse(
            success=True,
            deleted_count=0,
            message="삭제할 상품이 존재하지 않습니다."
        )

    # 2. Check for synced platform mappings
    sync_stmt = select(ProductPlatformMapping.product_id).where(
        and_(
            ProductPlatformMapping.product_id.in_(target_ids),
            ProductPlatformMapping.sync_status == "synced"
        )
    )
    sync_res = await db.execute(sync_stmt)
    synced_ids = [row[0] for row in sync_res.all()]
    synced_count = len(synced_ids)

    # 3. Warnings intercept if force is False
    if synced_count > 0 and not req.force:
        return ProductDeleteResponse(
            success=False,
            deleted_count=0,
            warning_synced_count=synced_count,
            message="이미 마켓에 연동(동기화) 완료된 상품이 포함되어 있어 삭제를 진행하지 않았습니다."
        )

    # 4. Perform cascade deletion (Postgres cascade configured in relationships)
    del_stmt = delete(Product).where(
        and_(
            Product.id.in_(target_ids),
            Product.user_id == current_user["id"]
        )
    )
    res_del = await db.execute(del_stmt)
    await db.commit()

    deleted_count = res_del.rowcount
    return ProductDeleteResponse(
        success=True,
        deleted_count=deleted_count,
        message=f"성공적으로 {deleted_count}개의 상품이 삭제되었습니다."
    )



@app.get("/imports", response_model=List[ProductImportResponse])
async def list_imports(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ProductImport)
        .where(ProductImport.user_id == current_user["id"])
        .order_by(ProductImport.created_at.desc())
    )
    return result.scalars().all()


# --- Celery Task Control & Status ---

@app.get("/status/{task_id}")
async def get_status(
    task_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_task_owner(task_id, current_user["id"], db)
    res = AsyncResult(task_id, app=celery_app)
    if res.state == 'PENDING':
        return {"state": res.state, "status": "Waiting for worker..."}
    elif res.state == 'PROGRESS':
        return {"state": res.state, "meta": res.info}
    elif res.state == 'SUCCESS':
        return {"state": res.state, "result": res.result}
    elif res.state == 'FAILURE':
        return {"state": res.state, "error": str(res.info)}
    return {"state": res.state}

@app.get("/download/{task_id}")
async def download_result(
    task_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_task_owner(task_id, current_user["id"], db)
    res = AsyncResult(task_id, app=celery_app)
    if res.state == 'SUCCESS':
        output_path = res.result.get("output_path")
        if output_path and os.path.exists(output_path):
            return FileResponse(output_path, filename=os.path.basename(output_path))
    raise HTTPException(status_code=404, detail="Result file not found or task not finished.")


# --- Admin Prompt Management ---

@app.get("/prompts", response_model=List[PromptResponse])
async def list_prompts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Prompt))
    return result.scalars().all()

@app.put("/prompts/{key}", response_model=PromptResponse)
async def update_prompt(key: str, prompt_in: PromptUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Prompt).where(Prompt.key == key))
    prompt = result.scalar_one_or_none()
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    prompt.template = prompt_in.template
    if prompt_in.description:
        prompt.description = prompt_in.description
    
    await db.commit()
    await db.refresh(prompt)
    
    # Clear cache
    pm = PromptManager(db)
    await pm.clear_cache(key)
    
    return prompt
