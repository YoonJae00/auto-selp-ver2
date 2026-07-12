import os
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

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
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test")

import main as processor_main
from schemas import MarketplaceNameRequest
from utils.product_name import generate_product_name


class FakeResult:
    def __init__(self, products):
        self.products = products

    def scalars(self):
        return self

    def all(self):
        return self.products


class FakeDB:
    def __init__(self, products):
        self.products = products
        self.added = []
        self.committed = False

    async def execute(self, _statement):
        return FakeResult(self.products)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.committed = True


def build_product(user_id):
    mapping = SimpleNamespace(platform_name="naver", category_path="생활/공구", product_name=None)
    product = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        status="completed",
        refined_name="접이식 작업 발판 사다리",
        keywords=["작업 발판", "발판 사다리", "접이식"],
        brand_name=None,
        original_name="원본 작업 발판 사다리",
        platform_mappings=[mapping],
        updated_at=None,
    )
    return product, mapping


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "candidates", "expected"),
    [
        (
            "openai",
            ["발판 사다리 접이식 작업", "작업 발판 사다리 접이식", "접이식 작업 발판 사다리"],
            "작업 발판 사다리 접이식",
        ),
        ("gemini", [], None),
    ],
)
async def test_marketplace_name_endpoint_selects_llm_or_deterministic_fallback(
    monkeypatch, provider, candidates, expected
):
    user_id = uuid.uuid4()
    product, mapping = build_product(user_id)
    db = FakeDB([product])
    llm_client = SimpleNamespace(generate_smartstore_name_candidates=AsyncMock(return_value=candidates))
    factory = MagicMock(return_value=llm_client)
    draft_request = AsyncMock()
    monkeypatch.setattr(processor_main, "get_llm_client", factory)
    monkeypatch.setattr(
        processor_main,
        "MarketplaceClient",
        lambda: SimpleNamespace(request_draft_generation=draft_request),
    )
    request = MarketplaceNameRequest(
        product_ids=[product.id], marketplace="smartstore", llm_provider=provider
    )

    response = await processor_main.generate_marketplace_names(
        request=request,
        current_user={"id": user_id},
        db=db,
    )

    expected = expected or generate_product_name(
        product.keywords, product.refined_name, product.brand_name, product.original_name
    )
    assert factory.call_args.args[0] == provider
    llm_client.generate_smartstore_name_candidates.assert_awaited_once_with(
        product.refined_name,
        product.keywords,
        product.brand_name,
        mapping.category_path,
    )
    assert db.committed is True
    assert mapping.product_name == expected
    assert response["generated_count"] == 1
    assert response["processing_time_ms"] >= 0
    item = response["items"][0]
    assert item["product_id"] == product.id
    assert item["original_name"] == product.original_name
    assert item["candidates"] == candidates
    assert item["product_name"] == expected
    assert item["generation_method"] == ("llm" if candidates else "fallback")
    assert item["llm_ms"] >= 0
    assert item["validation_ms"] >= 0
    assert item["total_ms"] == item["llm_ms"] + item["validation_ms"]
    draft_request.assert_awaited_once_with(product)
