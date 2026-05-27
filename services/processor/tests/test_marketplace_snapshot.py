import os
import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient


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
os.environ.setdefault("KIPRIS_API_KEY", "test")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "internal-test-token")

import main as processor_main


class FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeDB:
    def __init__(self, product=None):
        self.product = product
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        if self.product is None:
            return FakeScalarResult(None)

        params = stmt.compile().params
        requested_product_id = next((v for k, v in params.items() if k.startswith("id")), None)
        requested_user_id = next((v for k, v in params.items() if k.startswith("user_id")), None)

        if requested_product_id == self.product.id and requested_user_id == self.product.user_id:
            return FakeScalarResult(self.product)
        return FakeScalarResult(None)


def build_product(product_id: uuid.UUID, user_id: uuid.UUID):
    return SimpleNamespace(
        id=product_id,
        user_id=user_id,
        updated_at=datetime(2026, 5, 27, 12, 30, 45),
        product_code="P-100",
        wholesale_product_id="W-200",
        original_name="원본 상품명",
        refined_name="정제 상품명",
        brand_name="브랜드",
        keywords=["키워드1", "키워드2"],
        origin="해외|아시아|중국",
        price_wholesale=12000,
        price_retail=18000,
        price_min_selling=15000,
        images_list=["https://img.example/1.jpg", "https://img.example/2.jpg"],
        image_detail="<img src='detail.jpg'>",
        option_variants=[
            {"name": "L자형", "price_wholesale": 12000, "position": 1},
            {"name": "V자형", "price_wholesale": 13000, "position": 2},
        ],
        platform_mappings=[
            SimpleNamespace(
                platform_name="naver",
                category_id="50000001",
                category_path="생활/주방",
                mapped_attributes={"color": "red"},
            ),
            SimpleNamespace(
                platform_name="coupang",
                category_id="12345",
                category_path="가전디지털",
                mapped_attributes={"delivery": "rocket"},
            ),
            SimpleNamespace(
                platform_name="11st",
                category_id="888",
                category_path="기타",
                mapped_attributes={"x": "y"},
            ),
        ],
    )


def make_client(fake_db: FakeDB, monkeypatch):
    async def override_get_db():
        yield fake_db

    monkeypatch.setattr(processor_main, "seed_prompts", AsyncMock())
    processor_main.app.dependency_overrides[processor_main.get_db] = override_get_db
    client = TestClient(processor_main.app)
    return client


def test_marketplace_snapshot_success(monkeypatch):
    product_id = uuid.uuid4()
    user_id = uuid.uuid4()
    fake_db = FakeDB(product=build_product(product_id, user_id))
    client = make_client(fake_db, monkeypatch)

    try:
        response = client.get(
            f"/internal/products/{product_id}/marketplace-snapshot",
            params={"user_id": str(user_id)},
            headers={"X-Internal-Service-Token": "internal-test-token"},
        )
    finally:
        processor_main.app.dependency_overrides.clear()
        client.close()

    assert response.status_code == 200
    body = response.json()
    assert body["product_id"] == str(product_id)
    assert body["version"] == "2026-05-27T12:30:45"
    assert body["product_code"] == "P-100"
    assert body["wholesale_product_id"] == "W-200"
    assert body["original_name"] == "원본 상품명"
    assert body["refined_name"] == "정제 상품명"
    assert body["brand_name"] == "브랜드"
    assert body["keywords"] == ["키워드1", "키워드2"]
    assert body["origin"] == "해외|아시아|중국"
    assert body["price"] == {
        "wholesale": 12000,
        "retail": 18000,
        "minimum_selling": 15000,
    }
    assert body["images"] == {
        "list": ["https://img.example/1.jpg", "https://img.example/2.jpg"],
        "detail_content": "<img src='detail.jpg'>",
    }
    assert body["options"] == [
        {"name": "L자형", "price_wholesale": 12000, "position": 1},
        {"name": "V자형", "price_wholesale": 13000, "position": 2},
    ]
    assert body["market_categories"] == {
        "smartstore": {
            "category_id": "50000001",
            "category_path": "생활/주방",
            "mapped_attributes": {"color": "red"},
        },
        "coupang": {
            "category_id": "12345",
            "category_path": "가전디지털",
            "mapped_attributes": {"delivery": "rocket"},
        },
        "11st": {
            "category_id": "888",
            "category_path": "기타",
            "mapped_attributes": {"x": "y"},
        },
    }

    stmt = fake_db.statements[0]
    params = stmt.compile().params
    assert any("user_id" in key for key in params)
    assert any(key.startswith("id") for key in params)
    assert len(stmt._with_options) == 1


def test_marketplace_snapshot_missing_or_invalid_token_returns_401(monkeypatch):
    product_id = uuid.uuid4()
    user_id = uuid.uuid4()
    fake_db = FakeDB(product=build_product(product_id, user_id))
    client = make_client(fake_db, monkeypatch)

    try:
        missing = client.get(
            f"/internal/products/{product_id}/marketplace-snapshot",
            params={"user_id": str(user_id)},
        )
        invalid = client.get(
            f"/internal/products/{product_id}/marketplace-snapshot",
            params={"user_id": str(user_id)},
            headers={"X-Internal-Service-Token": "wrong-token"},
        )
    finally:
        processor_main.app.dependency_overrides.clear()
        client.close()

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert fake_db.statements == []


def test_marketplace_snapshot_returns_404_for_absent_or_wrong_owner(monkeypatch):
    product_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    fake_db = FakeDB(product=build_product(product_id, owner_id))
    client = make_client(fake_db, monkeypatch)

    try:
        wrong_owner = client.get(
            f"/internal/products/{product_id}/marketplace-snapshot",
            params={"user_id": str(other_user_id)},
            headers={"X-Internal-Service-Token": "internal-test-token"},
        )
    finally:
        processor_main.app.dependency_overrides.clear()
        client.close()

    assert wrong_owner.status_code == 404

    absent_db = FakeDB(product=None)
    absent_client = make_client(absent_db, monkeypatch)
    try:
        absent = absent_client.get(
            f"/internal/products/{uuid.uuid4()}/marketplace-snapshot",
            params={"user_id": str(owner_id)},
            headers={"X-Internal-Service-Token": "internal-test-token"},
        )
    finally:
        processor_main.app.dependency_overrides.clear()
        absent_client.close()

    assert absent.status_code == 404
