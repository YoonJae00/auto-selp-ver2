import asyncio
import time
import re as _re
import pandas as pd
import logging
from celery_app import celery_app
from utils.keyword_engine import KeywordEngine
from utils.category_mapper import CategoryMapper
from utils.prompt_manager import PromptManager
from utils.wholesale_upload import merge_product_warnings
from clients.llm_factory import get_llm_client
from database import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(bind=True)
def process_excel_task(
    self,
    file_path: str,
    column_mapping: dict,
    llm_provider: str = "gemini",
    kipris_enabled: bool = True,
):
    """엑셀 가공 전체 파이프라인 Celery Task"""
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(
        _run_pipeline(self, file_path, column_mapping, llm_provider, kipris_enabled)
    )


async def _run_pipeline(
    task_instance,
    file_path: str,
    column_mapping: dict,
    llm_provider: str,
    kipris_enabled: bool = True,
):
    df = pd.read_excel(file_path)
    total_rows = len(df)
    all_warnings: dict = {}
    completed_rows: list = []   # 완료된 행 상세 기록 (trace UI용)

    async with SessionLocal() as db:
        prompt_manager = PromptManager(db)
        llm_client = get_llm_client(llm_provider, prompt_manager)
        keyword_engine = KeywordEngine(llm_client, kipris_enabled=kipris_enabled)
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
                            # naver_cat = {path, id}  →  path 가 사람이 읽기 좋음
                            'naver_category': naver_cat.get('path') or naver_cat.get('id') or '',
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
    import_id: str,
    column_mapping: dict,
    llm_provider: str = "gemini",
    kipris_enabled: bool = True,
):
    """DB에 등록된 상품 가공 전체 파이프라인 Celery Task"""
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(
        _run_db_pipeline(self, import_id, column_mapping, llm_provider, kipris_enabled)
    )


async def _run_db_pipeline(
    task_instance,
    import_id: str,
    column_mapping: dict,
    llm_provider: str,
    kipris_enabled: bool = True,
):
    import uuid
    from models import ProductImport, Product, ProductPlatformMapping
    from sqlalchemy import select

    all_warnings: dict = {}
    completed_rows: list = []

    async with SessionLocal() as db:
        # Import 정보 조회
        import_uuid = uuid.UUID(import_id)
        result = await db.execute(select(ProductImport).where(ProductImport.id == import_uuid))
        import_run = result.scalar_one_or_none()
        if not import_run:
            raise ValueError(f"Import run {import_id} not found")

        # Import 가공 상태 변경
        import_run.status = "processing"
        await db.commit()

        # 미가공 상품 목록 조회
        prod_result = await db.execute(
            select(Product).where(Product.import_id == import_uuid, Product.status != "completed")
        )
        products = prod_result.scalars().all()
        total_rows = len(products)
        if total_rows == 0:
            import_run.status = "completed"
            await db.commit()
            return {"status": "Completed", "total": 0, "import_id": import_id}

        prompt_manager = PromptManager(db)
        llm_client = get_llm_client(llm_provider, prompt_manager)
        keyword_engine = KeywordEngine(llm_client, kipris_enabled=kipris_enabled)
        category_mapper = CategoryMapper()

        orig_col = column_mapping.get("original_name")

        for index, product in enumerate(products):
            original_name = product.original_name
            row_start = time.time()
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
                # 상품 상태 변경
                product.status = "processing"
                await db.commit()

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
                filtered_kw = [
                    w['keyword'] for w in (warnings or [])
                    if isinstance(w, dict) and w.get('keyword')
                ]

                # ── Stage 3: 카테고리 매핑 ──────────────────────────────
                _emit('categorizing')
                naver_cat = await category_mapper.get_naver_category(refined_name)
                coupang_cat = await category_mapper.get_coupang_category(refined_name)
                _finish_stage('categorizing')

                # ── 결과 DB 저장 ─────────────────────────────────────────
                product.refined_name = refined_name
                product.keywords = keywords
                product.warnings = merge_product_warnings(product.warnings, warnings)
                product.processing_time_ms = int((time.time() - row_start) * 1000)
                product.status = "completed"

                # 네이버 매핑 저장
                naver_mapping_result = await db.execute(
                    select(ProductPlatformMapping).where(
                        ProductPlatformMapping.product_id == product.id,
                        ProductPlatformMapping.platform_name == "naver"
                    )
                )
                naver_mapping = naver_mapping_result.scalar_one_or_none()
                if not naver_mapping:
                    naver_mapping = ProductPlatformMapping(
                        product_id=product.id,
                        platform_name="naver"
                    )
                    db.add(naver_mapping)
                    naver_mapping.sync_status = "draft"
                naver_mapping.category_id = str(naver_cat.get('id', ''))
                naver_mapping.category_path = naver_cat.get('path', '')

                # 쿠팡 매핑 저장
                coupang_mapping_result = await db.execute(
                    select(ProductPlatformMapping).where(
                        ProductPlatformMapping.product_id == product.id,
                        ProductPlatformMapping.platform_name == "coupang"
                    )
                )
                coupang_mapping = coupang_mapping_result.scalar_one_or_none()
                if not coupang_mapping:
                    coupang_mapping = ProductPlatformMapping(
                        product_id=product.id,
                        platform_name="coupang"
                    )
                    db.add(coupang_mapping)
                    coupang_mapping.sync_status = "draft"
                coupang_mapping.category_id = str(coupang_cat)
                coupang_mapping.category_path = str(coupang_cat)

                import_run.success_count += 1
                await db.commit()

                # 트레이스 UI 리스트 축적
                completed_rows.append({
                    'name': original_name,
                    'total_ms': product.processing_time_ms,
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
                            'naver_category': naver_cat.get('path') or naver_cat.get('id') or '',
                            'coupang_category': str(coupang_cat),
                        },
                    ],
                })

            except Exception as e:
                logger.error(f"Error processing product row {index} (ID: {product.id}): {e}")
                _finish_all()
                product.status = "failed"
                import_run.failed_count += 1
                await db.commit()

                completed_rows.append({
                    'name': original_name,
                    'total_ms': int((time.time() - row_start) * 1000),
                    'stages': [],
                    'error': str(e),
                })

            # Progress Emit
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

        # 배치 전체 가공 상태 변경
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
