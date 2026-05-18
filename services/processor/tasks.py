import asyncio
import pandas as pd
import logging
from celery_app import celery_app
from utils.keyword_engine import KeywordEngine
from utils.category_mapper import CategoryMapper
from utils.prompt_manager import PromptManager
from clients.llm_factory import get_llm_client
from database import SessionLocal

logger = logging.getLogger(__name__)

@celery_app.task(bind=True)
def process_excel_task(self, file_path: str, column_mapping: dict, llm_provider: str = "gemini", kipris_enabled: bool = True):
    """
    엑셀 가공 전체 파이프라인 Celery Task
    """
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(_run_pipeline(self, file_path, column_mapping, llm_provider, kipris_enabled))

async def _run_pipeline(task_instance, file_path: str, column_mapping: dict, llm_provider: str, kipris_enabled: bool = True):
    df = pd.read_excel(file_path)
    total_rows = len(df)
    all_warnings = {} # Store warnings by row index
    
    async with SessionLocal() as db:
        prompt_manager = PromptManager(db)
        
        # LLM 클라이언트 팩토리 사용 (PromptManager 전달)
        llm_client = get_llm_client(llm_provider, prompt_manager)
        
        keyword_engine = KeywordEngine(llm_client, kipris_enabled=kipris_enabled)
        category_mapper = CategoryMapper()
        
        # 컬럼 매핑 (사용자 지정)
        orig_col = column_mapping.get("original_name")
        name_col = column_mapping.get("refined_name", "정제상품명")
        kw_col = column_mapping.get("keywords", "키워드")
        naver_cat_col = column_mapping.get("naver_category", "네이버카테고리")
        coupang_cat_col = column_mapping.get("coupang_category", "쿠팡카테고리")
        
        # Output 컬럼 생성 (없으면)
        for col in [name_col, kw_col, naver_cat_col, coupang_cat_col]:
            if col:
                if col not in df.columns:
                    df[col] = ""
                # 강제로 object 타입으로 변환하여 문자열 저장이 가능하도록 함
                df[col] = df[col].astype(object)

        for index, row in df.iterrows():
            original_name = str(row[orig_col])
            
            try:
                # Stage 1: 정제
                refined_name = await llm_client.refine_product_name(original_name)
                
                # Stage 2: 키워드
                keywords, warnings = await keyword_engine.curate_keywords(refined_name)
                if warnings:
                    all_warnings[index] = warnings
                
                # Stage 3: 카테고리
                naver_cat = await category_mapper.get_naver_category(refined_name)
                coupang_cat_id = await category_mapper.get_coupang_category(refined_name)
                
                # 결과 업데이트
                if name_col:
                    df.at[index, name_col] = refined_name
                if kw_col:
                    df.at[index, kw_col] = ", ".join(keywords)
                if naver_cat_col:
                    df.at[index, naver_cat_col] = naver_cat['id']
                if coupang_cat_col:
                    df.at[index, coupang_cat_col] = coupang_cat_id
            except Exception as e:
                logger.error(f"Error processing row {index}: {e}")
                df.at[index, name_col] = "Error"
            
            # 진행률 업데이트
            progress = int((index + 1) / total_rows * 100)
            task_instance.update_state(
                state='PROGRESS', 
                meta={
                    'percent': progress, 
                    'current': index + 1, 
                    'total': total_rows,
                    'warnings': all_warnings
                }
            )

    # 결과 파일 저장
    output_path = file_path.replace(".xlsx", "_processed.xlsx")
    df.to_excel(output_path, index=False)
    
    return {"status": "Completed", "output_path": output_path, "warnings": all_warnings}
