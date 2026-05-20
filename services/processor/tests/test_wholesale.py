import pytest
import uuid
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from database import Base, engine
from config import settings

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
            price_wholesale=10000,
            wholesale_status="판매중",
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
        existing_product.price_wholesale = new_price
        existing_product.wholesale_status = new_status
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
