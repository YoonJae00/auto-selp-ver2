import pytest
import uuid
import os
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

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


class _TestBase(DeclarativeBase):
    pass


class _TestProductPlatformMapping(_TestBase):
    __tablename__ = "product_platform_mappings"
    product_id: Mapped[str] = mapped_column(String, primary_key=True)
    platform_name: Mapped[str] = mapped_column(String, primary_key=True)
    category_id: Mapped[str | None] = mapped_column(String, nullable=True)
    category_path: Mapped[str | None] = mapped_column(String, nullable=True)
    sync_status: Mapped[str | None] = mapped_column(String, nullable=True)


_models_module = types.ModuleType("models")
_models_module.ProductPlatformMapping = _TestProductPlatformMapping
sys.modules.setdefault("models", _models_module)


class FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeDB:
    def __init__(self):
        self.commits = 0
        self.added = []
        self.execute = AsyncMock(return_value=FakeScalarResult(None))

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1


class FakeLLMClient:
    async def refine_product_name(self, original_name):
        assert original_name == "원본 상품명"
        return "정제 상품명"


class FakeKeywordEngine:
    async def curate_keywords(self, refined_name):
        assert refined_name == "정제 상품명"
        return ["키워드1", "키워드2"], [{"keyword": "브랜드", "reason": "trademark"}]


class FakeCategoryMapper:
    async def get_naver_category(self, refined_name):
        assert refined_name == "정제 상품명"
        return {"id": "50000001", "path": "생활/주방"}

    async def get_coupang_category(self, refined_name):
        assert refined_name == "정제 상품명"
        return "12345"


def make_context(progress_events=None):
    from graphs.product_processor import ProductProcessingContext

    product = SimpleNamespace(
        id=uuid.uuid4(),
        original_name="원본 상품명",
        refined_name=None,
        keywords=None,
        warnings={"supplier_warnings": [{"keyword": "공급처", "reason": "raw"}]},
        processing_time_ms=None,
        status="pending",
    )
    import_run = SimpleNamespace(
        id=uuid.uuid4(),
        success_count=0,
        failed_count=0,
    )

    async def emit(stage_name, state):
        if progress_events is not None:
            progress_events.append((stage_name, dict(state)))

    return ProductProcessingContext(
        db=FakeDB(),
        import_run=import_run,
        product=product,
        llm_client=FakeLLMClient(),
        keyword_engine=FakeKeywordEngine(),
        category_mapper=FakeCategoryMapper(),
        progress_emitter=emit,
        completed_rows=[],
        all_warnings={},
        row_index=0,
        total_rows=1,
    )


def test_product_processor_graph_import_surface():
    from graphs.product_processor import (
        ProductProcessingContext,
        build_product_processing_graph,
        process_product_with_graph,
    )

    assert ProductProcessingContext is not None
    assert callable(build_product_processing_graph)
    assert callable(process_product_with_graph)


def test_build_product_processing_graph_compiles():
    from graphs.product_processor import build_product_processing_graph

    graph = build_product_processing_graph()

    assert hasattr(graph, "ainvoke")


@pytest.mark.asyncio
async def test_process_product_with_graph_success_updates_product_and_trace():
    from graphs.product_processor import process_product_with_graph

    progress_events = []
    context = make_context(progress_events)

    result = await process_product_with_graph(context)

    assert result["refined_name"] == "정제 상품명"
    assert context.product.status == "completed"
    assert context.product.refined_name == "정제 상품명"
    assert context.product.keywords == ["키워드1", "키워드2"]
    assert context.product.processing_time_ms >= 0
    assert context.import_run.success_count == 1
    assert context.import_run.failed_count == 0
    assert context.completed_rows[0]["name"] == "원본 상품명"
    assert context.completed_rows[0]["stages"][0]["name"] == "refining"
    assert context.completed_rows[0]["stages"][1]["name"] == "keywords"
    assert context.completed_rows[0]["stages"][2]["name"] == "categorizing"
    assert context.all_warnings[0][0]["keyword"] == "브랜드"
    assert [event[0] for event in progress_events] == ["refining", "keywords", "categorizing"]
