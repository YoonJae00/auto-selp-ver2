import os
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "internal-test-token")
import pytest
import uuid
import pandas as pd
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from database import Base, engine

from config import settings
from schemas import ProcessRequest, WholesaleMappingSuggestionRequest, WholesaleMappingPreviewRequest
import main as processor_main
from utils.wholesale_upload import parse_wholesale_row

# Import models
from models import WholesaleSite, Product, ProductPlatformMapping, ProductImport

@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"

@pytest.fixture(scope="module")
async def test_db():
    # Setup test database tables
    await engine.dispose()
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
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS standard_options JSON"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS change_type VARCHAR"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS changed_fields JSON DEFAULT '[]'"))
        
        await conn.execute(text("ALTER TABLE product_platform_mappings ADD COLUMN IF NOT EXISTS price_changed BOOLEAN DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE product_platform_mappings ADD COLUMN IF NOT EXISTS stock_changed BOOLEAN DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE product_platform_mappings ADD COLUMN IF NOT EXISTS last_synced_price INTEGER"))
        await conn.execute(text("ALTER TABLE product_platform_mappings ADD COLUMN IF NOT EXISTS last_synced_status VARCHAR"))
        await conn.execute(text("ALTER TABLE product_platform_mappings ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMP"))
        await conn.execute(text("ALTER TABLE product_platform_mappings ADD COLUMN IF NOT EXISTS last_changed_at TIMESTAMP"))
    
    async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    yield async_session
    
    # We can clean up here if needed, but since we use unique IDs, it is generally safe.
    await engine.dispose()

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


@pytest.mark.anyio
async def test_process_db_rejects_duplicate_supplier_codes_before_mutation(test_db, tmp_path, monkeypatch):
    user_id = uuid.uuid4()
    site_id = uuid.uuid4()
    product_id = uuid.uuid4()
    mapping = {
        "wholesale_status": "상태",
        "wholesale_product_id": "제품번호",
        "product_code": "상품코드",
        "original_name": "상품명",
        "price_wholesale_raw": "가격",
        "origin": "원산지",
        "image_list_1": "목록이미지1",
        "image_detail": "상세이미지",
    }
    rows = [
        {"상태": "판매중", "제품번호": "W-1", "상품코드": "DUP-1", "상품명": "중복 1", "가격": "2000", "원산지": "국내", "목록이미지1": "u1", "상세이미지": "d1"},
        {"상태": "판매중", "제품번호": "W-2", "상품코드": "DUP-1", "상품명": "중복 2", "가격": "3000", "원산지": "국내", "목록이미지1": "u2", "상세이미지": "d2"},
    ]

    async with test_db() as session:
        session.add(WholesaleSite(id=site_id, user_id=user_id, name="중복 공급처", column_mapping=mapping))
        session.add(Product(
            id=product_id,
            user_id=user_id,
            wholesale_site_id=site_id,
            product_code="DUP-1",
            original_name="기존 상품",
            price_wholesale=1000,
            status="completed",
            changed_fields=[],
        ))
        await session.commit()

    file_id = str(uuid.uuid4())
    (tmp_path / f"{file_id}_duplicates.xlsx").write_bytes(b"placeholder")
    monkeypatch.setattr(processor_main, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(processor_main.pd, "read_excel", lambda _path: pd.DataFrame(rows))

    async with test_db() as session:
        with pytest.raises(HTTPException) as exc_info:
            await processor_main.start_db_processing(
                ProcessRequest(
                    file_id=file_id,
                    column_mapping={},
                    wholesale_site_id=site_id,
                    start_processing=False,
                ),
                current_user={"id": user_id},
                db=session,
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Duplicate product_code values in excel: DUP-1"
        assert await session.scalar(
            select(func.count()).select_from(ProductImport).where(ProductImport.user_id == user_id)
        ) == 0
        assert await session.scalar(
            select(func.count()).select_from(Product).where(Product.user_id == user_id)
        ) == 1
        existing = await session.get(Product, product_id)
        assert existing.original_name == "기존 상품"
        assert existing.price_wholesale == 1000
        assert existing.status == "completed"
        assert existing.import_id is None


@pytest.mark.anyio
async def test_mapping_suggestion_repair_is_owned_sanitized_and_previewed(test_db, tmp_path, monkeypatch):
    user_id = uuid.uuid4()
    site_id = uuid.uuid4()
    file_id = str(uuid.uuid4())
    upload_file = tmp_path / f"{file_id}_products.xlsx"
    dataframe = pd.DataFrame(
        [{
            "상품코드": "1001",
            "자체상품코드": "JDM-1",
            "상품명(기본)": "족집게",
            "판매가": 370,
            "이미지": "https://img.example/1.jpg",
            "PC쇼핑몰상세설명": "detail",
        }]
    )
    dataframe.to_excel(upload_file, index=False)
    monkeypatch.setattr(processor_main, "UPLOAD_DIR", str(tmp_path))

    async with test_db() as session:
        session.add(WholesaleSite(id=site_id, user_id=user_id, name="정도매", column_mapping={"origin": {"default": "국내"}}))
        await session.commit()

    calls = []

    async def fake_suggestion(_self, headers, rows, current_mapping, instruction):
        calls.append((headers, rows, current_mapping, instruction))
        return {
            "column_mapping": {
                "wholesale_status": {"default": "판매중"},
                "wholesale_product_id": "상품코드",
                "product_code": "자체상품코드",
                "original_name": "상품명(기본)",
                "price_wholesale_raw": "판매가",
                "image_list_1": "이미지",
                "image_detail": "PC쇼핑몰상세설명",
                "made_up_field": "상품명(기본)",
                "price_retail": {"source": "없는제목"},
                "option_values_raw": {"source": "상품명(기본)", "pattern": "("},
            },
            "notes": ["사용자 지시에 따라 원산지를 유지했습니다."],
        }

    monkeypatch.setattr(processor_main.OpenAIClient, "suggest_wholesale_mapping", fake_suggestion)
    request = WholesaleMappingSuggestionRequest(
        file_id=file_id,
        column_mapping={"origin": {"default": "대한민국"}},
        instruction="원산지는 대한민국으로 고쳐줘",
    )

    async with test_db() as session:
        response = await processor_main.suggest_wholesale_site_mapping(
            site_id,
            request,
            current_user={"id": user_id},
            db=session,
        )

    assert len(calls) == 1
    assert calls[0][2]["origin"]["default"] == "대한민국"
    assert calls[0][3] == "원산지는 대한민국으로 고쳐줘"
    assert response["column_mapping"]["origin"] == {"default": "대한민국"}
    assert "made_up_field" not in response["column_mapping"]
    assert "price_retail" not in response["column_mapping"]
    assert response["preview"][0]["product_code"] == "JDM-1"
    assert response["standard_example"]["product_code"] == "SUPPLIER-001"
    assert response["notes"]
    assert any("unknown target" in item["message"] for item in response["warnings"])

    async with test_db() as session:
        with pytest.raises(HTTPException) as exc_info:
            await processor_main.preview_wholesale_site_mapping(
                site_id,
                WholesaleMappingPreviewRequest(file_id=file_id, column_mapping={}),
                current_user={"id": uuid.uuid4()},
                db=session,
            )
    assert exc_info.value.status_code == 404


@pytest.mark.anyio
async def test_process_db_only_imports_new_and_supplier_scoped_changes(test_db, tmp_path, monkeypatch):
    user_id = uuid.uuid4()
    site_id = uuid.uuid4()
    other_site_id = uuid.uuid4()
    old_import_id = uuid.uuid4()
    old_updated_at = datetime(2020, 1, 1)
    mapping = {
        "wholesale_status": "상태",
        "wholesale_product_id": "제품번호",
        "product_code": "상품코드",
        "original_name": "상품명",
        "price_wholesale_raw": "가격",
        "origin": "원산지",
        "image_list_1": "목록이미지1",
        "image_detail": "상세이미지",
    }
    rows = [
        {"상태": "판매중", "제품번호": "W-1", "상품코드": "UNCHANGED", "상품명": "그대로", "가격": "1000", "원산지": "국내", "목록이미지1": "u1", "상세이미지": "d1"},
        {"상태": "판매중", "제품번호": "W-2", "상품코드": "UPDATED", "상품명": "가격 변경", "가격": "2500", "원산지": "국내", "목록이미지1": "u2", "상세이미지": "d2"},
        {"상태": "판매중", "제품번호": "W-3", "상품코드": "NEW", "상품명": "신상품", "가격": "3000", "원산지": "국내", "목록이미지1": "u3", "상세이미지": "d3"},
    ]

    def product_from_row(site, row, *, price=None):
        data = parse_wholesale_row(pd.Series(row), mapping)["product_data"]
        if price is not None:
            data["price_wholesale"] = price
            data["price_wholesale_raw"] = str(price)
        return Product(
            user_id=user_id,
            import_id=old_import_id,
            wholesale_site_id=site,
            product_code=data["product_code"],
            options=data["option_values_raw"],
            status="completed",
            change_type=None,
            changed_fields=[],
            warnings=None,
            raw_metadata={},
            updated_at=old_updated_at,
            **{field: data[field] for field in processor_main.CANONICAL_IMPORT_FIELDS},
        )

    async with test_db() as session:
        session.add_all([
            WholesaleSite(id=site_id, user_id=user_id, name="공급처 A", column_mapping=mapping),
            WholesaleSite(id=other_site_id, user_id=user_id, name="공급처 B", column_mapping=mapping),
            ProductImport(id=old_import_id, user_id=user_id, filename="old.xlsx", status="completed"),
        ])
        unchanged = product_from_row(site_id, rows[0])
        updated = product_from_row(site_id, rows[1], price=2000)
        other_supplier = product_from_row(other_site_id, rows[1])
        session.add_all([unchanged, updated, other_supplier])
        await session.flush()
        session.add(ProductPlatformMapping(product_id=updated.id, platform_name="naver", sync_status="synced"))
        await session.commit()
        unchanged_id, updated_id, other_id = unchanged.id, updated.id, other_supplier.id

    file_id = str(uuid.uuid4())
    upload_file = tmp_path / f"{file_id}_products.xlsx"
    upload_file.write_bytes(b"placeholder")
    monkeypatch.setattr(processor_main, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(processor_main.pd, "read_excel", lambda _path: pd.DataFrame(rows))
    request = ProcessRequest(
        file_id=file_id,
        column_mapping={},
        wholesale_site_id=site_id,
        start_processing=False,
    )

    async with test_db() as session:
        response = await processor_main.start_db_processing(
            request,
            current_user={"id": user_id},
            db=session,
        )

    assert response["total"] == 2
    assert response["new_count"] == 1
    assert response["updated_count"] == 1
    assert response["unchanged_count"] == 1

    async with test_db() as session:
        unchanged = await session.get(Product, unchanged_id)
        updated = await session.get(Product, updated_id)
        other_supplier = await session.get(Product, other_id)
        new_product = (await session.execute(select(Product).where(Product.wholesale_site_id == site_id, Product.product_code == "NEW"))).scalar_one()
        import_run = await session.get(ProductImport, response["import_id"])
        platform_mapping = (await session.execute(select(ProductPlatformMapping).where(ProductPlatformMapping.product_id == updated_id))).scalar_one()

        assert unchanged.import_id == old_import_id
        assert unchanged.status == "completed"
        assert unchanged.change_type is None
        assert unchanged.updated_at == old_updated_at
        assert updated.import_id == response["import_id"]
        assert updated.status == "pending"
        assert updated.change_type == "updated"
        assert updated.changed_fields == ["price_wholesale", "price_wholesale_raw"]
        assert platform_mapping.sync_status == "pending_update"
        assert platform_mapping.price_changed is True
        assert platform_mapping.last_changed_at is not None
        assert other_supplier.import_id == old_import_id
        assert other_supplier.price_wholesale == 2500
        assert new_product.change_type == "new"
        assert new_product.changed_fields == []
        assert import_run.total_count == 2
