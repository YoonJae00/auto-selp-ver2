import asyncio
import time
import re as _re
import uuid
from datetime import datetime
import pandas as pd
import logging
from celery_app import celery_app
from utils.keyword_engine import KeywordEngine
from utils.category_mapper import CategoryMapper
from utils.prompt_manager import PromptManager
from utils.wholesale_upload import merge_product_warnings
from clients.llm_factory import get_llm_client, get_vision_llm_client
from clients.marketplace_client import MarketplaceClient
from database import SessionLocal
from graphs.product_processor import ProductProcessingContext, process_product_with_graph
from utils.main_image import download_image, process_main_image, save_processed_image

logger = logging.getLogger(__name__)


@celery_app.task(bind=True)
def process_excel_task(
    self,
    file_path: str,
    column_mapping: dict,
    llm_provider: str = "gemini",
    vision_llm_provider: str = "gemini",
):
    """엑셀 가공 전체 파이프라인 Celery Task"""
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(
        _run_pipeline(self, file_path, column_mapping, llm_provider, vision_llm_provider)
    )


async def _run_pipeline(
    task_instance,
    file_path: str,
    column_mapping: dict,
    llm_provider: str,
    vision_llm_provider: str = "gemini",
):
    df = pd.read_excel(file_path)
    total_rows = len(df)
    all_warnings: dict = {}
    completed_rows: list = []   # 완료된 행 상세 기록 (trace UI용)

    async with SessionLocal() as db:
        prompt_manager = PromptManager(db)
        llm_client = get_llm_client(llm_provider, prompt_manager)
        vision_llm_client = get_vision_llm_client(vision_llm_provider, prompt_manager)
        keyword_engine = KeywordEngine(llm_client)
        category_mapper = CategoryMapper()

        orig_col       = column_mapping.get("original_name")
        name_col       = column_mapping.get("refined_name", "정제상품명")
        kw_col         = column_mapping.get("keywords", "키워드")
        naver_cat_col  = column_mapping.get("naver_category", "네이버카테고리")
        coupang_cat_col = column_mapping.get("coupang_category", "쿠팡카테고리")

        for col in [name_col, kw_col, naver_cat_col, coupang_cat_col]:
            if col:
                if col not in df.columns:
                    df[col] = ""
                df[col] = df[col].astype(object)

        for index, row in df.iterrows():
            original_name = str(row[orig_col])
            row_start = time.time()

            # stage_timings: {stage_name: {'start': float, 'ms': int}}
            stage_timings: dict = {}

            def _finish_stage(stage_name: str):
                if stage_name in stage_timings and 'ms' not in stage_timings[stage_name]:
                    stage_timings[stage_name]['ms'] = int(
                        (time.time() - stage_timings[stage_name]['start']) * 1000
                    )

            def _finish_all():
                for sn in list(stage_timings):
                    _finish_stage(sn)

            def _emit(stage_name: str):
                """단계 시작 → 이전 단계 마감 → Redis emit"""
                if stage_timings:
                    last = list(stage_timings)[-1]
                    _finish_stage(last)
                stage_timings[stage_name] = {'start': time.time()}
                pct = int(index / total_rows * 100)
                task_instance.update_state(
                    state='PROGRESS',
                    meta={
                        'percent': pct,
                        'current': index + 1,
                        'total': total_rows,
                        'stage': stage_name,
                        'current_name': original_name,
                        'completed_rows': completed_rows,
                        'warnings': all_warnings,
                    },
                )

            try:
                # ── Stage 1: 상품명 정제 ─────────────────────────────────
                _emit('refining')
                refined_name = await llm_client.refine_product_name(original_name)
                _finish_stage('refining')

                # ── Stage 2: 키워드 생성 ─────────────────────────────────
                _emit('keywords')
                keywords, warnings = await keyword_engine.curate_keywords(refined_name)
                _finish_stage('keywords')
                if warnings:
                    all_warnings[index] = warnings
                # 상표권 경고 키워드만 별도 수집
                filtered_kw = [
                    w['keyword'] for w in (warnings or [])
                    if isinstance(w, dict) and w.get('keyword')
                ]

                # ── Stage 3: 카테고리 매핑 ──────────────────────────────
                _emit('categorizing')
                naver_cat    = await category_mapper.get_naver_category(refined_name)
                coupang_cat  = await category_mapper.get_coupang_category(refined_name)
                _finish_stage('categorizing')

                # ── 결과 DataFrame 업데이트 ──────────────────────────────
                if name_col:        df.at[index, name_col]        = refined_name
                if kw_col:          df.at[index, kw_col]          = ", ".join(keywords)
                if naver_cat_col:   df.at[index, naver_cat_col]   = naver_cat.get('id', '')
                if coupang_cat_col: df.at[index, coupang_cat_col] = coupang_cat

                # ── 완료 행 기록 (트레이스 UI용) ─────────────────────────
                completed_rows.append({
                    'name': original_name,
                    'total_ms': int((time.time() - row_start) * 1000),
                    'stages': [
                        {
                            'name': 'refining',
                            'ms': stage_timings.get('refining', {}).get('ms', 0),
                            'refined_name': refined_name,
                        },
                        {
                            'name': 'keywords',
                            'ms': stage_timings.get('keywords', {}).get('ms', 0),
                            'keywords': keywords,
                            'filtered': filtered_kw,
                        },
                        {
                            'name': 'categorizing',
                            'ms': stage_timings.get('categorizing', {}).get('ms', 0),
                            'naver_category': naver_cat.get('id') or naver_cat.get('path') or '',
                            'coupang_category': str(coupang_cat),
                        },
                    ],
                })

            except Exception as e:
                logger.error(f"Error processing row {index}: {e}")
                _finish_all()
                if name_col:
                    df.at[index, name_col] = "Error"
                completed_rows.append({
                    'name': original_name,
                    'total_ms': int((time.time() - row_start) * 1000),
                    'stages': [],
                    'error': str(e),
                })

            # ── 행 완료 emit ─────────────────────────────────────────────
            progress = int((index + 1) / total_rows * 100)
            task_instance.update_state(
                state='PROGRESS',
                meta={
                    'percent': progress,
                    'current': index + 1,
                    'total': total_rows,
                    'stage': 'completed_row',
                    'current_name': original_name,
                    'completed_rows': completed_rows,
                    'warnings': all_warnings,
                },
            )

    # ── 결과 파일 저장 (.xls/.xlsx 모두 → _processed.xlsx) ───────────────
    output_path = _re.sub(r'\.xlsx?$', '_processed.xlsx', file_path, flags=_re.IGNORECASE)
    df.to_excel(output_path, index=False, engine='openpyxl')

    return {
        "status": "Completed",
        "output_path": output_path,
        "warnings": all_warnings,
        "completed_rows": completed_rows,   # ← 완료 후에도 트레이스 데이터 보존
        "total": total_rows,
    }


@celery_app.task(bind=True)
def process_db_products_task(
    self,
    import_id: str | None,
    column_mapping: dict,
    llm_provider: str = "gemini",
    product_ids: list[str] | None = None,
    vision_llm_provider: str = "gemini",
):
    """DB에 등록된 상품 가공 전체 파이프라인 Celery Task"""
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(
        _run_db_pipeline(self, import_id, column_mapping, llm_provider, product_ids, vision_llm_provider)
    )


async def _run_db_pipeline(
    task_instance,
    import_id: str,
    column_mapping: dict,
    llm_provider: str,
    product_ids: list[str] | None = None,
    vision_llm_provider: str = "gemini",
):
    import uuid
    from models import ProductImport, Product, ProductPlatformMapping
    from sqlalchemy import select

    all_warnings: dict = {}
    completed_rows: list = []

    async with SessionLocal() as db:
        import_run = None
        import_uuid = uuid.UUID(import_id) if import_id else None
        if import_uuid:
            result = await db.execute(select(ProductImport).where(ProductImport.id == import_uuid))
            import_run = result.scalar_one_or_none()
            if not import_run:
                raise ValueError(f"Import run {import_id} not found")

            # Import 가공 상태 변경
            import_run.status = "processing"
            await db.commit()

        # 미가공 상품 목록 조회
        if product_ids:
            product_uuids = [uuid.UUID(pid) for pid in product_ids]
            prod_stmt = select(Product).where(Product.id.in_(product_uuids))
        else:
            prod_stmt = select(Product).where(Product.import_id == import_uuid, Product.status != "completed")

        prod_result = await db.execute(prod_stmt)
        products = prod_result.scalars().all()
        total_rows = len(products)
        if total_rows == 0:
            if import_run:
                import_run.status = "completed"
            await db.commit()
            return {"status": "Completed", "total": 0, "import_id": import_id}

        prompt_manager = PromptManager(db)
        llm_client = get_llm_client(llm_provider, prompt_manager)
        vision_llm_client = get_vision_llm_client(vision_llm_provider, prompt_manager)
        keyword_engine = KeywordEngine(llm_client)
        category_mapper = CategoryMapper()
        marketplace_client = MarketplaceClient()

        for index, product in enumerate(products):
            original_name = product.original_name

            async def emit_stage(stage_name: str, _state: dict):
                pct = int(index / total_rows * 100)
                task_instance.update_state(
                    state="PROGRESS",
                    meta={
                        "percent": pct,
                        "current": index + 1,
                        "total": total_rows,
                        "stage": stage_name,
                        "current_name": original_name,
                        "completed_rows": completed_rows,
                        "warnings": all_warnings,
                    },
                )

            context = ProductProcessingContext(
                db=db,
                import_run=import_run,
                product=product,
                llm_client=llm_client,
                vision_llm_client=vision_llm_client,
                keyword_engine=keyword_engine,
                category_mapper=category_mapper,
                marketplace_client=marketplace_client,
                progress_emitter=emit_stage,
                completed_rows=completed_rows,
                all_warnings=all_warnings,
                row_index=index,
                total_rows=total_rows,
            )

            await process_product_with_graph(context)

            # Progress Emit
            progress = int((index + 1) / total_rows * 100)
            task_instance.update_state(
                state="PROGRESS",
                meta={
                    "percent": progress,
                    "current": index + 1,
                    "total": total_rows,
                    "stage": "completed_row",
                    "current_name": original_name,
                    "completed_rows": completed_rows,
                    "warnings": all_warnings,
                },
            )

        # 배치 전체 가공 상태 변경
        if import_run:
            if import_run.failed_count == total_rows:
                import_run.status = "failed"
            else:
                import_run.status = "completed"
        await db.commit()

    return {
        "status": "Completed",
        "warnings": all_warnings,
        "completed_rows": completed_rows,
        "total": total_rows,
        "import_id": import_id,
    }


@celery_app.task(bind=True)
def process_main_images_task(self, user_id: str, product_ids: list[str]):
    """Process representative images serially on the dedicated image queue."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(_run_main_image_pipeline(self, user_id, product_ids))


async def _run_main_image_pipeline(task_instance, user_id: str, product_ids: list[str]):
    from models import Product
    from sqlalchemy import select

    user_uuid = uuid.UUID(user_id)
    product_uuids = [uuid.UUID(product_id) for product_id in product_ids]
    completed_rows: list[dict] = []
    all_warnings: dict[str, list[dict]] = {}
    total_rows = len(product_uuids)
    marketplace_client = MarketplaceClient()

    async with SessionLocal() as db:
        result = await db.execute(
            select(Product).where(Product.user_id == user_uuid, Product.id.in_(product_uuids))
        )
        products_by_id = {product.id: product for product in result.scalars().all()}

        for index, product_id in enumerate(product_uuids):
            product = products_by_id.get(product_id)
            current_name = product.original_name if product else str(product_id)
            row = {"product_id": str(product_id), "name": current_name}

            task_instance.update_state(
                state="PROGRESS",
                meta={
                    "percent": int(index / total_rows * 100) if total_rows else 100,
                    "current": index + 1,
                    "total": total_rows,
                    "stage": "main_image_processing",
                    "current_name": current_name,
                    "completed_rows": completed_rows,
                    "warnings": all_warnings,
                },
            )

            try:
                if product is None:
                    raise ValueError("Product no longer exists.")
                source_url = next(
                    (
                        url.strip()
                        for url in (product.images_list or [])
                        if isinstance(url, str) and url.strip()
                    ),
                    None,
                )
                if product.status != "completed" or not source_url:
                    raise ValueError("Product is not eligible for representative image processing.")

                product.image_processing_status = "processing"
                await db.commit()

                source_bytes = await download_image(source_url)
                output_bytes = process_main_image(source_bytes, product.id)
                output_path = save_processed_image(output_bytes, product.user_id, product.id)
                product.processed_image_path = str(output_path)
                product.image_processing_status = "completed"
                product.updated_at = datetime.now()
                await db.commit()
                row["status"] = "completed"

                try:
                    await marketplace_client.request_draft_generation(product)
                except Exception as error:
                    logger.error(
                        "Failed to refresh marketplace drafts after image processing for %s: %s",
                        product.id,
                        error,
                    )
            except Exception as error:
                warning = {
                    "stage": "main_image_processing",
                    "key": "main_image_processing",
                    "message": str(error),
                }
                all_warnings[str(product_id)] = [warning]
                row.update({"status": "failed", "error": str(error)})
                if product is not None:
                    product.image_processing_status = "failed"
                    product.warnings = merge_product_warnings(product.warnings, warning)
                    product.updated_at = datetime.now()
                    await db.commit()
                logger.error("Representative image processing failed for %s: %s", product_id, error)

            completed_rows.append(row)
            task_instance.update_state(
                state="PROGRESS",
                meta={
                    "percent": int((index + 1) / total_rows * 100) if total_rows else 100,
                    "current": index + 1,
                    "total": total_rows,
                    "stage": "completed_row",
                    "current_name": current_name,
                    "completed_rows": completed_rows,
                    "warnings": all_warnings,
                },
            )

    return {
        "status": "Completed",
        "warnings": all_warnings,
        "completed_rows": completed_rows,
        "total": total_rows,
    }
