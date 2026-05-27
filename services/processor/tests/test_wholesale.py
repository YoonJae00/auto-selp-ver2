import os
import pytest
import uuid
import pandas as pd
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from database import Base, engine

os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "internal-test-token")

from config import settings
from schemas import ProcessRequest
import main as processor_main

# Import models
from models import WholesaleSite, Product, ProductPlatformMapping, ProductImport

@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"

@pytest.fixture(scope="module")
async def test_db():
    # Setup test database tables
    async with engine.begin() as conn:
        # Create all tables (in case they do not exist or are missing columns)
        await conn.run_sync(Base.metadata.create_all)
        
        # Apply manual migrations for columns added to existing tables
        from sqlalchemy import text
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
    
    async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    yield async_session
    
    # We can clean up here if needed, but since we use unique IDs, it is generally safe.

@pytest.mark.anyio
async def test_wholesale_site_crud(test_db):
    user_id = uuid.uuid4()
    
    async with test_db() as session:
        # 1. Create
        new_site = WholesaleSite(
            id=uuid.uuid4(),
            user_id=user_id,
            name="Test Wholesale Co.",
            homepage_url="https://testwholesale.com",
            column_mapping={
                "product_code": "도매상품코드",
                "price_wholesale": "공급가",
                "wholesale_status": "품절유무"
            }
        )
        session.add(new_site)
        await session.commit()
        site_id = new_site.id

    async with test_db() as session:
        # 2. Retrieve & Verify
        result = await session.execute(select(WholesaleSite).where(WholesaleSite.id == site_id))
        fetched_site = result.scalar_one_or_none()
        assert fetched_site is not None
        assert fetched_site.name == "Test Wholesale Co."
        assert fetched_site.column_mapping["price_wholesale"] == "공급가"

        # 3. Update Mapping JSONB
        fetched_site.column_mapping = {**fetched_site.column_mapping, "origin": "원산지"}
        session.add(fetched_site)
        await session.commit()

    async with test_db() as session:
        result = await session.execute(select(WholesaleSite).where(WholesaleSite.id == site_id))
        updated_site = result.scalar_one_or_none()
        assert updated_site.column_mapping["origin"] == "원산지"

        # 4. Delete
        await session.delete(updated_site)
        await session.commit()

        result = await session.execute(select(WholesaleSite).where(WholesaleSite.id == site_id))
        deleted_site = result.scalar_one_or_none()
        assert deleted_site is None


@pytest.mark.anyio
async def test_smart_upsert_and_change_tracking(test_db):
    user_id = uuid.uuid4()
    import_id = uuid.uuid4()
    
    async with test_db() as session:
        # Setup pre-existing import run
        import_run = ProductImport(
            id=import_id,
            user_id=user_id,
            filename="test_sync.xlsx",
            status="completed"
        )
        session.add(import_run)
        
        # Setup pre-existing product
        product = Product(
            id=uuid.uuid4(),
            user_id=user_id,
            import_id=import_id,
            original_name="Pre-existing Product",
            product_code="P-CODE-999",
            wholesale_product_id="OLD-123",
            price_wholesale=10000,
            option_values_raw="기본형",
            price_wholesale_raw="10000",
            option_variants=[{"name": "기본형", "price_wholesale": 10000, "position": 1}],
            wholesale_status="판매중",
            wholesale_registered_at="2026-05-01",
            status="completed"
        )
        session.add(product)
        await session.flush()
        
        # Setup pre-existing synced platform mapping
        mapping = ProductPlatformMapping(
            id=uuid.uuid4(),
            product_id=product.id,
            platform_name="naver",
            category_id="50000001",
            category_path="의류",
            sync_status="synced",
            last_synced_price=10000,
            last_synced_status="판매중",
            last_synced_at=datetime.utcnow(),
            price_changed=False,
            stock_changed=False
        )
        session.add(mapping)
        await session.commit()
        
        product_id = product.id
        mapping_id = mapping.id

    # Simulate smart upsert with changed values
    async with test_db() as session:
        # Query product by product_code and user_id
        res = await session.execute(
            select(Product).where(Product.product_code == "P-CODE-999", Product.user_id == user_id)
        )
        existing_product = res.scalar_one_or_none()
        assert existing_product is not None
        
        # New upload data: price changed from 10000 to 12000, stock status changed from "판매중" to "품절"
        new_price = 12000
        new_status = "품절"
        
        # Update product fields
        existing_product.wholesale_product_id = "NEW-123"
        existing_product.price_wholesale = new_price
        existing_product.option_values_raw = "L자형,V자형"
        existing_product.price_wholesale_raw = "12000,13000"
        existing_product.option_variants = [
            {"name": "L자형", "price_wholesale": 12000, "position": 1},
            {"name": "V자형", "price_wholesale": 13000, "position": 2},
        ]
        existing_product.wholesale_status = new_status
        existing_product.wholesale_registered_at = "2026-05-20"
        session.add(existing_product)
        
        # Perform change tracking comparison for platform mappings
        mappings_res = await session.execute(
            select(ProductPlatformMapping).where(ProductPlatformMapping.product_id == existing_product.id)
        )
        platform_mappings = mappings_res.scalars().all()
        
        for pm in platform_mappings:
            price_changed = False
            stock_changed = False
            
            # Check price change
            if pm.last_synced_price is not None and pm.last_synced_price != new_price:
                price_changed = True
                pm.price_changed = True
            
            # Check stock status change
            if pm.last_synced_status is not None and pm.last_synced_status != new_status:
                stock_changed = True
                pm.stock_changed = True
                
            if price_changed or stock_changed:
                pm.sync_status = "pending_update"
                pm.last_changed_at = datetime.utcnow()
                session.add(pm)
                
        await session.commit()

    # Verify transition state
    async with test_db() as session:
        res = await session.execute(select(ProductPlatformMapping).where(ProductPlatformMapping.id == mapping_id))
        updated_mapping = res.scalar_one_or_none()
        assert updated_mapping is not None
        assert updated_mapping.sync_status == "pending_update"
        assert updated_mapping.price_changed is True
        assert updated_mapping.stock_changed is True
        assert updated_mapping.last_changed_at is not None

        product_res = await session.execute(select(Product).where(Product.id == product_id))
        updated_product = product_res.scalar_one()
        assert updated_product.wholesale_product_id == "NEW-123"
        assert updated_product.price_wholesale_raw == "12000,13000"
        assert updated_product.option_variants[0]["price_wholesale"] == 12000
        assert updated_product.wholesale_registered_at == "2026-05-20"


@pytest.mark.anyio
async def test_process_db_rejects_wholesale_site_owned_by_another_user(test_db, tmp_path, monkeypatch):
    owner_id = uuid.uuid4()
    current_user_id = uuid.uuid4()
    site_id = uuid.uuid4()

    async with test_db() as session:
        site = WholesaleSite(
            id=site_id,
            user_id=owner_id,
            name="Other User Template",
            column_mapping={
                "wholesale_status": "상태",
                "wholesale_product_id": "제품번호",
                "product_code": "상품코드",
                "original_name": "상품명",
                "price_wholesale_raw": "가격",
                "origin": "원산지",
                "image_list_1": "목록이미지1",
                "image_detail": "상세이미지",
            },
        )
        session.add(site)
        await session.commit()

    file_id = str(uuid.uuid4())
    upload_file = tmp_path / f"{file_id}_products.xlsx"
    upload_file.write_bytes(b"placeholder")
    monkeypatch.setattr(processor_main, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(
        processor_main.pd,
        "read_excel",
        lambda _path: pd.DataFrame(
            [
                {
                    "상태": "정상",
                    "제품번호": "123",
                    "상품코드": "P-123",
                    "상품명": "테스트 상품",
                    "가격": "1000",
                    "원산지": "국내",
                    "목록이미지1": "https://img.example/1.jpg",
                    "상세이미지": "https://img.example/detail.jpg",
                }
            ]
        ),
    )

    request = ProcessRequest(
        file_id=file_id,
        column_mapping={},
        wholesale_site_id=site_id,
    )

    async with test_db() as session:
        with pytest.raises(HTTPException) as exc_info:
            await processor_main.start_db_processing(
                request,
                current_user={"id": current_user_id, "username": "current", "is_admin": False},
                db=session,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Wholesale site not found"

        import_count = await session.scalar(
            select(func.count()).select_from(ProductImport).where(ProductImport.user_id == current_user_id)
        )
        assert import_count == 0
