import asyncio
from sqlalchemy import select
from database import SessionLocal, engine, Base
from models import Prompt

DEFAULT_PROMPTS = {
    "refine_stage_1": {
        "template": "입력된 상품명에서 브랜드명, 특수문자, 중복 단어를 제거하고 검색에 최적화된 깔끔한 상품명만 추출해줘. 수량 단위는 '개'로 표준화해. 응답은 반드시 {\"refined_name\": \"...\"} 형식의 JSON이어야 해. 입력: {original_name}",
        "description": "표준 상품명 정제 프롬프트"
    },
    "refine_stage_2": {
        "template": "상품명을 쇼핑 검색에 유리하게 정제해줘. 브랜드와 불필요한 미사여구는 빼고 핵심 단어만 남겨. 응답 형식: {\"refined_name\": \"...\"}. 입력: {original_name}",
        "description": "2단계 간결한 정제"
    },
    "refine_stage_3": {
        "template": "다음 상품명에서 특수문자만 제거하고 이름을 다듬어줘. 응답 형식: {\"refined_name\": \"...\"}. 입력: {original_name}",
        "description": "3단계 최소 가공"
    },
    "get_synonyms": {
        "template": "다음 상품명과 연관된 쇼핑 검색 키워드 동의어를 3개만 추천해줘. 예: '무선 이어폰' -> '블루투스 이어셋'. 응답은 콤마로 구분. 입력: {refined_name}",
        "description": "키워드 동의어 확장"
    }
}

async def seed_prompts():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async with SessionLocal() as db:
        for key, data in DEFAULT_PROMPTS.items():
            result = await db.execute(select(Prompt).where(Prompt.key == key))
            if not result.scalar_one_or_none():
                db.add(Prompt(key=key, template=data["template"], description=data["description"]))
        await db.commit()

if __name__ == "__main__":
    asyncio.run(seed_prompts())
