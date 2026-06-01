import asyncio
from sqlalchemy import select, text
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
        # Create new tables first (e.g. wholesale_sites)
        await conn.run_sync(Base.metadata.create_all)
        
        # Apply manual migrations for columns added to existing tables
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS wholesale_site_id UUID REFERENCES wholesale_sites(id) ON DELETE SET NULL"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS product_code VARCHAR"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS wholesale_product_id VARCHAR"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS price_wholesale INTEGER"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS option_values_raw TEXT"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS price_wholesale_raw TEXT"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS price_retail INTEGER"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS price_min_selling INTEGER"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS origin VARCHAR"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS options TEXT"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS option_variants JSON"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS standard_options JSON"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS images_list JSON"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS image_detail TEXT"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS wholesale_status VARCHAR"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS wholesale_registered_at VARCHAR"))
        
        await conn.execute(text("ALTER TABLE product_platform_mappings ADD COLUMN IF NOT EXISTS price_changed BOOLEAN DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE product_platform_mappings ADD COLUMN IF NOT EXISTS stock_changed BOOLEAN DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE product_platform_mappings ADD COLUMN IF NOT EXISTS last_synced_price INTEGER"))
        await conn.execute(text("ALTER TABLE product_platform_mappings ADD COLUMN IF NOT EXISTS last_synced_status VARCHAR"))
        await conn.execute(text("ALTER TABLE product_platform_mappings ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMP"))
        await conn.execute(text("ALTER TABLE product_platform_mappings ADD COLUMN IF NOT EXISTS last_changed_at TIMESTAMP"))
        
    async with SessionLocal() as db:
        for key, data in DEFAULT_PROMPTS.items():
            result = await db.execute(select(Prompt).where(Prompt.key == key))
            if not result.scalar_one_or_none():
                db.add(Prompt(key=key, template=data["template"], description=data["description"]))
        await db.commit()

if __name__ == "__main__":
    asyncio.run(seed_prompts())
