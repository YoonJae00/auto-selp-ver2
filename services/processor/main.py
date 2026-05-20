import os
import uuid
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Dict, Optional, List
from celery.result import AsyncResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, text
from sqlalchemy.orm import selectinload
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import io
import urllib.parse
from datetime import datetime

from tasks import process_excel_task, process_db_products_task
from celery_app import celery_app
from database import get_db, engine, Base
from models import Prompt, ProductImport, Product, ProductPlatformMapping, WholesaleSite
from schemas import (
    ProcessRequest, 
    PromptUpdate, 
    PromptResponse, 
    DBProcessRequest, 
    ProductListResponse, 
    ProductResponse, 
    ProductImportResponse,
    WholesaleSiteCreate,
    WholesaleSiteUpdate,
    WholesaleSiteResponse
)
from utils.prompt_manager import PromptManager
from utils.wholesale_upload import parse_wholesale_row, validate_required_mappings
from config import settings

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Auto-Selp Product Processor")

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


# --- Wholesale Sites API ---

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
    task = process_excel_task.delay(file_path, request.column_mapping, request.llm_provider, request.kipris_enabled)
    return {"task_id": task.id}


# --- New DB-Backed Processing Endpoints ---

@app.post("/process-db")
async def start_db_processing(
    request: ProcessRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    files = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(request.file_id)]
    if not files:
        raise HTTPException(status_code=404, detail="File not found.")
    
    file_path = os.path.join(UPLOAD_DIR, files[0])
    
    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read excel: {e}")
    
    # 1. ProductImport 생성
    import_id = uuid.uuid4()
    import_run = ProductImport(
        id=import_id,
        user_id=current_user["id"],
        filename=files[0][37:], # Remove UUID prefix
        total_count=len(df),
        status="pending"
    )
    db.add(import_run)
    
    col_mapping = dict(request.column_mapping)
    if request.wholesale_site_id:
        result = await db.execute(select(WholesaleSite).where(WholesaleSite.id == request.wholesale_site_id))
        site = result.scalar_one_or_none()
        if site and site.column_mapping:
            col_mapping = {**site.column_mapping, **col_mapping}

    missing_required = validate_required_mappings(col_mapping, list(df.columns))
    if missing_required:
        raise HTTPException(
            status_code=400,
            detail=f"Required mapped columns missing in excel: {', '.join(missing_required)}",
        )
        
    for index, row in df.iterrows():
        parsed_row = parse_wholesale_row(row, col_mapping)
        product_data = parsed_row["product_data"]
        row_warnings = parsed_row["warnings"]

        original_name = product_data["original_name"]
        product_code = product_data["product_code"]
        price_wholesale = product_data["price_wholesale"]
        wholesale_status = product_data["wholesale_status"]
        product_warnings = (
            {"warnings": row_warnings, "supplier_warnings": row_warnings}
            if row_warnings
            else None
        )

        # Check for smart upsert if product_code exists
        existing_product = None
        if product_code:
            stmt_existing = select(Product).where(
                and_(Product.product_code == product_code, Product.user_id == current_user["id"])
            )
            res_existing = await db.execute(stmt_existing)
            existing_product = res_existing.scalar_one_or_none()

        if existing_product:
            existing_product.original_name = original_name
            existing_product.import_id = import_id
            existing_product.wholesale_site_id = request.wholesale_site_id
            existing_product.wholesale_product_id = product_data["wholesale_product_id"]
            existing_product.price_wholesale = product_data["price_wholesale"]
            existing_product.price_wholesale_raw = product_data["price_wholesale_raw"]
            existing_product.price_retail = product_data["price_retail"]
            existing_product.price_min_selling = product_data["price_min_selling"]
            existing_product.origin = product_data["origin"]
            existing_product.options = product_data["option_values_raw"]
            existing_product.option_values_raw = product_data["option_values_raw"]
            existing_product.option_variants = product_data["option_variants"]
            existing_product.images_list = product_data["images_list"]
            existing_product.image_detail = product_data["image_detail"]
            existing_product.wholesale_status = product_data["wholesale_status"]
            existing_product.wholesale_registered_at = product_data["wholesale_registered_at"]
            existing_product.status = "pending"
            existing_product.warnings = product_warnings
            existing_product.raw_metadata = product_data["raw_metadata"]
            
            mappings_res = await db.execute(
                select(ProductPlatformMapping).where(ProductPlatformMapping.product_id == existing_product.id)
            )
            platform_mappings = mappings_res.scalars().all()
            for pm in platform_mappings:
                price_changed = False
                stock_changed = False
                
                if price_wholesale is not None and pm.last_synced_price is not None and pm.last_synced_price != price_wholesale:
                    price_changed = True
                    pm.price_changed = True
                
                if wholesale_status is not None and pm.last_synced_status is not None and pm.last_synced_status != wholesale_status:
                    stock_changed = True
                    pm.stock_changed = True
                    
                if price_changed or stock_changed:
                    pm.sync_status = "pending_update"
                    pm.last_changed_at = datetime.utcnow()
                    db.add(pm)
            
            db.add(existing_product)
        else:
            product = Product(
                user_id=current_user["id"],
                import_id=import_id,
                wholesale_site_id=request.wholesale_site_id,
                wholesale_product_id=product_data["wholesale_product_id"],
                product_code=product_code,
                price_wholesale=product_data["price_wholesale"],
                price_wholesale_raw=product_data["price_wholesale_raw"],
                price_retail=product_data["price_retail"],
                price_min_selling=product_data["price_min_selling"],
                origin=product_data["origin"],
                options=product_data["option_values_raw"],
                option_values_raw=product_data["option_values_raw"],
                option_variants=product_data["option_variants"],
                images_list=product_data["images_list"],
                image_detail=product_data["image_detail"],
                wholesale_status=product_data["wholesale_status"],
                wholesale_registered_at=product_data["wholesale_registered_at"],
                original_name=original_name,
                status="pending",
                warnings=product_warnings,
                raw_metadata=product_data["raw_metadata"],
            )
            db.add(product)

    await db.commit()
    
    # 3. Celery 비동기 태스크 시작
    task = process_db_products_task.delay(
        str(import_id),
        col_mapping,
        request.llm_provider,
        request.kipris_enabled
    )
    
    return {
        "task_id": task.id,
        "import_id": import_id,
        "total": len(df)
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
    
    stmt = stmt.order_by(Product.created_at.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    items = result.scalars().all()
    
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": items
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
                naver_cat = m.category_path or m.category_id or ""
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
async def get_status(task_id: str):
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
async def download_result(task_id: str):
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
