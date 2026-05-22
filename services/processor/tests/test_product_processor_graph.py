import pytest
import uuid
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock


class FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeDB:
    def __init__(self, commit_side_effects=None):
        self.commits = 0
        self.added = []
        self.execute = AsyncMock(return_value=FakeScalarResult(None))
        self.commit_side_effects = list(commit_side_effects or [])

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1
        if self.commit_side_effects:
            effect = self.commit_side_effects.pop(0)
            if effect is not None:
                raise effect


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


class FailingLLMClient:
    async def refine_product_name(self, _original_name):
        raise RuntimeError("llm unavailable")


class CancelledLLMClient:
    async def refine_product_name(self, _original_name):
        raise asyncio.CancelledError()


def make_context(progress_events=None, db=None):
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
        db=db or FakeDB(),
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
    from graphs import product_processor

    progress_events = []
    context = make_context(progress_events)

    async def fake_get_or_create_mapping(_runtime, _platform_name):
        return SimpleNamespace(category_id=None, category_path=None, sync_status="draft")

    original = product_processor._get_or_create_mapping
    product_processor._get_or_create_mapping = fake_get_or_create_mapping
    try:
        result = await product_processor.process_product_with_graph(context)
    finally:
        product_processor._get_or_create_mapping = original

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


@pytest.mark.asyncio
async def test_process_product_with_graph_failure_marks_product_failed_and_continues_shape():
    from graphs.product_processor import process_product_with_graph

    context = make_context([])
    context.llm_client = FailingLLMClient()

    result = await process_product_with_graph(context)

    assert result["error"] == "llm unavailable"
    assert context.product.status == "failed"
    assert context.import_run.success_count == 0
    assert context.import_run.failed_count == 1
    assert context.completed_rows[0]["name"] == "원본 상품명"
    assert context.completed_rows[0]["error"] == "llm unavailable"
    assert context.completed_rows[0]["stages"] == []


@pytest.mark.asyncio
async def test_process_product_with_graph_cancellation_propagates_without_failure_side_effects():
    from graphs.product_processor import process_product_with_graph

    context = make_context([])
    context.llm_client = CancelledLLMClient()

    with pytest.raises(asyncio.CancelledError):
        await process_product_with_graph(context)

    assert context.product.status != "failed"
    assert context.import_run.success_count == 0
    assert context.import_run.failed_count == 0
    assert context.completed_rows == []


@pytest.mark.asyncio
async def test_process_product_with_graph_late_failure_restores_success_and_increments_failed_once():
    from graphs import product_processor

    db = FakeDB(commit_side_effects=[None, RuntimeError("commit exploded"), None])
    context = make_context([], db=db)
    context.import_run.success_count = 5
    context.import_run.failed_count = 2

    async def fake_get_or_create_mapping(_runtime, _platform_name):
        return SimpleNamespace(category_id=None, category_path=None, sync_status="draft")

    original = product_processor._get_or_create_mapping
    product_processor._get_or_create_mapping = fake_get_or_create_mapping
    try:
        result = await product_processor.process_product_with_graph(context)
    finally:
        product_processor._get_or_create_mapping = original

    assert result["error"] == "commit exploded"
    assert context.product.status == "failed"
    assert context.import_run.success_count == 5
    assert context.import_run.failed_count == 3
    assert context.completed_rows[0]["error"] == "commit exploded"
