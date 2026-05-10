import asyncio
import pandas as pd
import logging
from celery_app import celery_app
from utils.keyword_engine import KeywordEngine
from utils.category_mapper import CategoryMapper
from clients.llm_factory import get_llm_client

logger = logging.getLogger(__name__)

@celery_app.task(bind=True)
def process_excel_task(self, file_path: str, column_mapping: dict, llm_provider: str = "gemini"):
    """
    엑셀 가공 전체 파이프라인 Celery Task
    """
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(self._run_pipeline(file_path, column_mapping, llm_provider))

async def _run_pipeline(self, file_path: str, column_mapping: dict, llm_provider: str):
    df = pd.read_excel(file_path)
    total_rows = len(df)
    
    # LLM 클라이언트 팩토리 사용
    llm_client = get_llm_client(llm_provider)
    
    keyword_engine = KeywordEngine(llm_client)
    category_mapper = CategoryMapper()
    
    # 컬럼 매핑 (사용자 지정)
    orig_col = column_mapping.get("original_name")
    name_col = column_mapping.get("refined_name", "정제상품명")
    kw_col = column_mapping.get("keywords", "키워드")
    cat_col = column_mapping.get("category", "카테고리")
    
    # Output 컬럼 생성 (없으면)
    for col in [name_col, kw_col, cat_col]:
        if col not in df.columns:
            df[col] = ""

    for index, row in df.iterrows():
        original_name = str(row[orig_col])
        
        try:
            # Stage 1: 정제
            refined_name = await llm_client.refine_product_name(original_name)
            
            # Stage 2: 키워드
            keywords = await keyword_engine.curate_keywords(refined_name)
            
            # Stage 3: 카테고리
            naver_cat = await category_mapper.get_naver_category(refined_name)
            coupang_cat_id = await category_mapper.get_coupang_category(refined_name)
            
            # 결과 업데이트
            df.at[index, name_col] = refined_name
            df.at[index, kw_col] = ", ".join(keywords)
            df.at[index, cat_col] = f"Naver:{naver_cat['id']} | Coupang:{coupang_cat_id}"
        except Exception as e:
            logger.error(f"Error processing row {index}: {e}")
            df.at[index, name_col] = "Error"
        
        # 진행률 업데이트
        progress = int((index + 1) / total_rows * 100)
        self.update_state(state='PROGRESS', meta={'current': index + 1, 'total': total_rows, 'percent': progress})

    # 결과 파일 저장
    output_path = file_path.replace(".xlsx", "_processed.xlsx")
    df.to_excel(output_path, index=False)
    
    return {"status": "Completed", "output_path": output_path}
