import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("NAVER_API_KEY", "test")
os.environ.setdefault("NAVER_SECRET_KEY", "test")
os.environ.setdefault("NAVER_CUSTOMER_ID", "test")
os.environ.setdefault("NAVER_CLIENT_ID", "test")
os.environ.setdefault("NAVER_CLIENT_SECRET", "test")
os.environ.setdefault("Coupang_Access_Key", "test")
os.environ.setdefault("Coupang_Secret_Key", "test")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "internal-test-token")

import pytest
import uuid
from sqlalchemy import select
from httpx import AsyncClient
from main import app
from models import Product, ProductPlatformMapping, WholesaleSite
from database import Base, engine
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

TEST_USER_ID = uuid.uuid4()

@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"

@pytest.fixture(scope="module")
async def test_session():
    # Setup test database tables if needed, similar to other integration tests
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    yield async_session

@pytest.fixture(autouse=True)
def mock_auth():
    from main import get_current_user
    app.dependency_overrides[get_current_user] = lambda: {"id": TEST_USER_ID, "username": "test_user", "is_admin": False}
    yield
    app.dependency_overrides.clear()

@pytest.mark.anyio
async def test_delete_endpoint_fails_due_to_sync_warning(test_session):
    async with test_session() as session:
        # 1. Create a dummy Wholesale Site specifically for this test case
        site_id = uuid.uuid4()
        site = WholesaleSite(
            id=site_id,
            user_id=TEST_USER_ID,
            name="Test Site Deletion Warning",
            homepage_url="http://test.com",
            column_mapping={}
        )
        session.add(site)

        # 2. Create products (one normal, one synced to market)
        prod1_id = uuid.uuid4()
        prod1 = Product(
            id=prod1_id,
            user_id=site.user_id,
            wholesale_site_id=site_id,
            original_name="Normal Product Warning",
            status="completed"
        )
        prod2_id = uuid.uuid4()
        prod2 = Product(
            id=prod2_id,
            user_id=site.user_id,
            wholesale_site_id=site_id,
            original_name="Synced Product Warning",
            status="completed"
        )
        session.add_all([prod1, prod2])

        # 3. Mark prod2 as synced in mappings
        mapping = ProductPlatformMapping(
            id=uuid.uuid4(),
            product_id=prod2_id,
            platform_name="naver",
            sync_status="synced"
        )
        session.add(mapping)
        await session.commit()

    # 4. Trigger DELETE api without force flag
    async with AsyncClient(app=app, base_url="http://test") as ac:
        headers = {"Authorization": "Bearer internal-test-token"}
        response = await ac.post(
            "/products/delete",
            json={"product_ids": [str(prod1_id), str(prod2_id)], "force": False},
            headers=headers
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["warning_synced_count"] == 1
    assert data["deleted_count"] == 0

@pytest.mark.anyio
async def test_delete_endpoint_success_with_force(test_session):
    # Make this test completely self-contained with its own unique data setup
    async with test_session() as session:
        # 1. Create a dummy Wholesale Site specifically for this test case
        site_id = uuid.uuid4()
        site = WholesaleSite(
            id=site_id,
            user_id=TEST_USER_ID,
            name="Test Site Deletion Force Success",
            homepage_url="http://test.com",
            column_mapping={}
        )
        session.add(site)

        # 2. Create products (one normal, one synced to market)
        prod1_id = uuid.uuid4()
        prod1 = Product(
            id=prod1_id,
            user_id=site.user_id,
            wholesale_site_id=site_id,
            original_name="Normal Product Force",
            status="completed"
        )
        prod2_id = uuid.uuid4()
        prod2 = Product(
            id=prod2_id,
            user_id=site.user_id,
            wholesale_site_id=site_id,
            original_name="Synced Product Force",
            status="completed"
        )
        session.add_all([prod1, prod2])

        # 3. Mark prod2 as synced in mappings
        mapping = ProductPlatformMapping(
            id=uuid.uuid4(),
            product_id=prod2_id,
            platform_name="naver",
            sync_status="synced"
        )
        session.add(mapping)
        await session.commit()

    # 4. Trigger DELETE api with force flag = True
    async with AsyncClient(app=app, base_url="http://test") as ac:
        headers = {"Authorization": "Bearer internal-test-token"}
        response = await ac.post(
            "/products/delete",
            json={"wholesale_site_id": str(site_id), "force": True},
            headers=headers
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["deleted_count"] >= 2

    # 5. Explicitly query Product and ProductPlatformMapping tables to assert they are completely deleted
    async with test_session() as session:
        # Verify Product records are deleted from database
        prod_stmt = select(Product).where(Product.wholesale_site_id == site_id)
        prod_res = await session.execute(prod_stmt)
        products = prod_res.scalars().all()
        assert len(products) == 0

        # Verify ProductPlatformMapping records are deleted from database
        mapping_stmt = select(ProductPlatformMapping).where(
            ProductPlatformMapping.product_id.in_([prod1_id, prod2_id])
        )
        mapping_res = await session.execute(mapping_stmt)
        mappings = mapping_res.scalars().all()
        assert len(mappings) == 0


@pytest.mark.anyio
async def test_delete_endpoint_prevents_unauthorized_deletion(test_session):
    other_user_id = uuid.uuid4()
    async with test_session() as session:
        # Create a product belonging to a completely different user
        site_id = uuid.uuid4()
        site = WholesaleSite(
            id=site_id,
            user_id=other_user_id,
            name="Other User Site",
            homepage_url="http://other.com",
            column_mapping={}
        )
        session.add(site)

        prod_id = uuid.uuid4()
        prod = Product(
            id=prod_id,
            user_id=other_user_id,
            wholesale_site_id=site_id,
            original_name="Other User Product",
            status="completed"
        )
        session.add(prod)
        await session.commit()

    # Trigger DELETE api for the other user's product under the current mock user context
    async with AsyncClient(app=app, base_url="http://test") as ac:
        headers = {"Authorization": "Bearer internal-test-token"}
        response = await ac.post(
            "/products/delete",
            json={"product_ids": [str(prod_id)], "force": True},
            headers=headers
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["deleted_count"] == 0  # Should be 0 because it belongs to a different user
    assert data["message"] == "삭제할 상품이 존재하지 않습니다."

    # Verify the product is still safe and NOT deleted in the database
    async with test_session() as session:
        prod_stmt = select(Product).where(Product.id == prod_id)
        prod_res = await session.execute(prod_stmt)
        prod_in_db = prod_res.scalar_one_or_none()
        assert prod_in_db is not None
        assert prod_in_db.original_name == "Other User Product"
