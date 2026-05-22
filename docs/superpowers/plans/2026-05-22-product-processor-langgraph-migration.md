# Product Processor LangGraph Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the DB-backed product processing task so each product is processed by a LangGraph `StateGraph` while preserving existing Celery progress, DB statuses, and frontend behavior.

**Architecture:** Celery remains the batch runner. `_run_db_pipeline` loads the import and products, then invokes a one-product LangGraph for each non-completed product. The graph owns product-level stages and persistence; Celery owns batch progress metadata and final import status.

**Tech Stack:** Python, FastAPI service code, Celery, SQLAlchemy async sessions, LangGraph `StateGraph`, pytest, pytest-asyncio.

---

## File Structure

- Modify `services/processor/requirements.txt`
  - Add LangGraph runtime dependency.
- Create `services/processor/requirements-dev.txt`
  - Add LangGraph Studio CLI dependency for local development.
- Create `services/processor/graphs/__init__.py`
  - Makes graph modules importable.
- Create `services/processor/graphs/product_processor.py`
  - Defines graph state, runtime context, progress emitter, nodes, graph builder, and `process_product_with_graph`.
- Modify `services/processor/tasks.py`
  - Keep Celery task wrappers and legacy Excel pipeline intact.
  - Replace inline per-product DB processing with `process_product_with_graph`.
- Create `services/processor/tests/test_product_processor_graph.py`
  - Unit tests for graph success, failure, and metadata compatibility.
- Modify `services/processor/tests/test_tasks.py`
  - Add a compatibility test proving `_run_db_pipeline` delegates per-product work and preserves progress metadata shape.
- Create `langgraph.json`
  - Enables LangGraph Studio local development with `langgraph dev`.

## Task 1: Add LangGraph Dependencies And Import Surface

**Files:**
- Modify: `services/processor/requirements.txt`
- Create: `services/processor/requirements-dev.txt`
- Create: `services/processor/graphs/__init__.py`
- Test: `services/processor/tests/test_product_processor_graph.py`

- [ ] **Step 1: Write the failing import test**

Create `services/processor/tests/test_product_processor_graph.py`:

```python
import pytest


def test_product_processor_graph_import_surface():
    from graphs.product_processor import (
        ProductProcessingContext,
        build_product_processing_graph,
        process_product_with_graph,
    )

    assert ProductProcessingContext is not None
    assert callable(build_product_processing_graph)
    assert callable(process_product_with_graph)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd services/processor
pytest tests/test_product_processor_graph.py::test_product_processor_graph_import_surface -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'graphs'` or `No module named 'graphs.product_processor'`.

- [ ] **Step 3: Add runtime/dev dependencies and graph package skeleton**

Append to `services/processor/requirements.txt`:

```text
langgraph
```

Create `services/processor/requirements-dev.txt`:

```text
-r requirements.txt
langgraph-cli[inmem]
```

Create `services/processor/graphs/__init__.py`:

```python
"""LangGraph workflows for the processor service."""
```

Create `services/processor/graphs/product_processor.py`:

```python
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypedDict


class ProductProcessingState(TypedDict, total=False):
    import_id: str
    product_id: str
    original_name: str
    refined_name: str
    keywords: list[str]
    warnings: list[dict[str, Any]]
    filtered_keywords: list[str]
    naver_category: dict[str, Any]
    coupang_category: str
    stage_timings: dict[str, dict[str, float | int]]
    processing_time_ms: int
    error: str


ProgressEmitter = Callable[[str, ProductProcessingState], Awaitable[None]]


async def noop_progress_emitter(_stage_name: str, _state: ProductProcessingState) -> None:
    return None


@dataclass
class ProductProcessingContext:
    db: Any
    import_run: Any
    product: Any
    llm_client: Any
    keyword_engine: Any
    category_mapper: Any
    progress_emitter: ProgressEmitter = noop_progress_emitter
    completed_rows: list[dict[str, Any]] = field(default_factory=list)
    all_warnings: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    row_index: int = 0
    total_rows: int = 1


def build_product_processing_graph():
    raise NotImplementedError("LangGraph implementation is added in Task 2")


async def process_product_with_graph(context: ProductProcessingContext) -> ProductProcessingState:
    raise NotImplementedError("LangGraph implementation is added in Task 2")
```

- [ ] **Step 4: Run the import test**

Run:

```bash
cd services/processor
pytest tests/test_product_processor_graph.py::test_product_processor_graph_import_surface -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/processor/requirements.txt services/processor/requirements-dev.txt services/processor/graphs/__init__.py services/processor/graphs/product_processor.py services/processor/tests/test_product_processor_graph.py
git commit -m "chore(processor): add langgraph processor surface"
```

## Task 2: Build The Product Graph Skeleton

**Files:**
- Modify: `services/processor/graphs/product_processor.py`
- Modify: `services/processor/tests/test_product_processor_graph.py`

- [ ] **Step 1: Add a failing graph compile test**

Append to `services/processor/tests/test_product_processor_graph.py`:

```python
def test_build_product_processing_graph_compiles():
    from graphs.product_processor import build_product_processing_graph

    graph = build_product_processing_graph()

    assert hasattr(graph, "ainvoke")
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd services/processor
pytest tests/test_product_processor_graph.py::test_build_product_processing_graph_compiles -v
```

Expected: FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement the minimal compiled graph**

Replace `build_product_processing_graph` in `services/processor/graphs/product_processor.py` and add the imports shown here:

```python
import time
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime


async def load_product_context(
    state: ProductProcessingState,
    runtime: Runtime[ProductProcessingContext],
) -> ProductProcessingState:
    product = runtime.context.product
    return {
        **state,
        "import_id": str(runtime.context.import_run.id),
        "product_id": str(product.id),
        "original_name": product.original_name,
        "stage_timings": {},
    }


async def mark_processing(
    state: ProductProcessingState,
    runtime: Runtime[ProductProcessingContext],
) -> ProductProcessingState:
    runtime.context.product.status = "processing"
    await runtime.context.db.commit()
    return state


def build_product_processing_graph():
    graph = StateGraph(
        state_schema=ProductProcessingState,
        context_schema=ProductProcessingContext,
    )
    graph.add_node("load_product_context", load_product_context)
    graph.add_node("mark_processing", mark_processing)
    graph.add_edge(START, "load_product_context")
    graph.add_edge("load_product_context", "mark_processing")
    graph.add_edge("mark_processing", END)
    return graph.compile()
```

- [ ] **Step 4: Run the graph compile test**

Run:

```bash
cd services/processor
pytest tests/test_product_processor_graph.py::test_build_product_processing_graph_compiles -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/processor/graphs/product_processor.py services/processor/tests/test_product_processor_graph.py
git commit -m "feat(processor): compile product processing graph"
```

## Task 3: Implement Successful Product Processing Nodes

**Files:**
- Modify: `services/processor/graphs/product_processor.py`
- Modify: `services/processor/tests/test_product_processor_graph.py`

- [ ] **Step 1: Add fake test helpers**

Append these helpers near the top of `services/processor/tests/test_product_processor_graph.py`:

```python
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock


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
```

- [ ] **Step 2: Add the failing success-path test**

Append:

```python
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
```

- [ ] **Step 3: Run the test to verify it fails**

Run:

```bash
cd services/processor
pytest tests/test_product_processor_graph.py::test_process_product_with_graph_success_updates_product_and_trace -v
```

Expected: FAIL because graph only marks the product as processing.

- [ ] **Step 4: Implement timing helpers and success nodes**

In `services/processor/graphs/product_processor.py`, add:

```python
from models import ProductPlatformMapping
from sqlalchemy import select
from utils.wholesale_upload import merge_product_warnings


def _finish_stage(state: ProductProcessingState, stage_name: str) -> None:
    timings = state.setdefault("stage_timings", {})
    stage = timings.get(stage_name)
    if stage and "ms" not in stage:
        stage["ms"] = int((time.time() - float(stage["start"])) * 1000)


def _finish_previous_stage(state: ProductProcessingState) -> None:
    timings = state.setdefault("stage_timings", {})
    if timings:
        _finish_stage(state, list(timings)[-1])


async def _start_stage(
    state: ProductProcessingState,
    runtime: Runtime[ProductProcessingContext],
    stage_name: str,
) -> None:
    _finish_previous_stage(state)
    state.setdefault("stage_timings", {})[stage_name] = {"start": time.time()}
    await runtime.context.progress_emitter(stage_name, state)


async def refine_name(
    state: ProductProcessingState,
    runtime: Runtime[ProductProcessingContext],
) -> ProductProcessingState:
    await _start_stage(state, runtime, "refining")
    refined_name = await runtime.context.llm_client.refine_product_name(state["original_name"])
    _finish_stage(state, "refining")
    return {**state, "refined_name": refined_name}


async def curate_keywords(
    state: ProductProcessingState,
    runtime: Runtime[ProductProcessingContext],
) -> ProductProcessingState:
    await _start_stage(state, runtime, "keywords")
    keywords, warnings = await runtime.context.keyword_engine.curate_keywords(state["refined_name"])
    _finish_stage(state, "keywords")
    filtered_keywords = [
        warning["keyword"]
        for warning in (warnings or [])
        if isinstance(warning, dict) and warning.get("keyword")
    ]
    if warnings:
        runtime.context.all_warnings[runtime.context.row_index] = warnings
    return {
        **state,
        "keywords": keywords,
        "warnings": warnings or [],
        "filtered_keywords": filtered_keywords,
    }


async def map_categories(
    state: ProductProcessingState,
    runtime: Runtime[ProductProcessingContext],
) -> ProductProcessingState:
    await _start_stage(state, runtime, "categorizing")
    naver_category = await runtime.context.category_mapper.get_naver_category(state["refined_name"])
    coupang_category = await runtime.context.category_mapper.get_coupang_category(state["refined_name"])
    _finish_stage(state, "categorizing")
    return {
        **state,
        "naver_category": naver_category,
        "coupang_category": str(coupang_category),
    }


async def _get_or_create_mapping(runtime: Runtime[ProductProcessingContext], platform_name: str):
    result = await runtime.context.db.execute(
        select(ProductPlatformMapping).where(
            ProductPlatformMapping.product_id == runtime.context.product.id,
            ProductPlatformMapping.platform_name == platform_name,
        )
    )
    mapping = result.scalar_one_or_none()
    if mapping is None:
        mapping = ProductPlatformMapping(
            product_id=runtime.context.product.id,
            platform_name=platform_name,
        )
        mapping.sync_status = "draft"
        runtime.context.db.add(mapping)
    return mapping


async def persist_success(
    state: ProductProcessingState,
    runtime: Runtime[ProductProcessingContext],
) -> ProductProcessingState:
    product = runtime.context.product
    product.refined_name = state["refined_name"]
    product.keywords = state["keywords"]
    product.warnings = merge_product_warnings(product.warnings, state.get("warnings", []))
    product.processing_time_ms = int(
        sum(int(stage.get("ms", 0)) for stage in state.get("stage_timings", {}).values())
    )
    product.status = "completed"

    naver_mapping = await _get_or_create_mapping(runtime, "naver")
    naver_mapping.category_id = str(state["naver_category"].get("id", ""))
    naver_mapping.category_path = state["naver_category"].get("path", "")

    coupang_mapping = await _get_or_create_mapping(runtime, "coupang")
    coupang_mapping.category_id = state["coupang_category"]
    coupang_mapping.category_path = state["coupang_category"]

    runtime.context.import_run.success_count += 1
    await runtime.context.db.commit()

    completed_row = {
        "name": state["original_name"],
        "total_ms": product.processing_time_ms,
        "stages": [
            {
                "name": "refining",
                "ms": state.get("stage_timings", {}).get("refining", {}).get("ms", 0),
                "refined_name": state["refined_name"],
            },
            {
                "name": "keywords",
                "ms": state.get("stage_timings", {}).get("keywords", {}).get("ms", 0),
                "keywords": state["keywords"],
                "filtered": state.get("filtered_keywords", []),
            },
            {
                "name": "categorizing",
                "ms": state.get("stage_timings", {}).get("categorizing", {}).get("ms", 0),
                "naver_category": state["naver_category"].get("path")
                or state["naver_category"].get("id")
                or "",
                "coupang_category": state["coupang_category"],
            },
        ],
    }
    runtime.context.completed_rows.append(completed_row)
    return {**state, "processing_time_ms": product.processing_time_ms}
```

Replace `build_product_processing_graph` with:

```python
def build_product_processing_graph():
    graph = StateGraph(
        state_schema=ProductProcessingState,
        context_schema=ProductProcessingContext,
    )
    graph.add_node("load_product_context", load_product_context)
    graph.add_node("mark_processing", mark_processing)
    graph.add_node("refine_name", refine_name)
    graph.add_node("curate_keywords", curate_keywords)
    graph.add_node("map_categories", map_categories)
    graph.add_node("persist_success", persist_success)
    graph.add_edge(START, "load_product_context")
    graph.add_edge("load_product_context", "mark_processing")
    graph.add_edge("mark_processing", "refine_name")
    graph.add_edge("refine_name", "curate_keywords")
    graph.add_edge("curate_keywords", "map_categories")
    graph.add_edge("map_categories", "persist_success")
    graph.add_edge("persist_success", END)
    return graph.compile()
```

Replace `process_product_with_graph` with:

```python
async def process_product_with_graph(context: ProductProcessingContext) -> ProductProcessingState:
    graph = build_product_processing_graph()
    return await graph.ainvoke({}, context=context)
```

- [ ] **Step 5: Run the success-path test**

Run:

```bash
cd services/processor
pytest tests/test_product_processor_graph.py::test_process_product_with_graph_success_updates_product_and_trace -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/processor/graphs/product_processor.py services/processor/tests/test_product_processor_graph.py
git commit -m "feat(processor): process product success path with langgraph"
```

## Task 4: Add Product-Level Failure Handling

**Files:**
- Modify: `services/processor/graphs/product_processor.py`
- Modify: `services/processor/tests/test_product_processor_graph.py`

- [ ] **Step 1: Add the failing failure-path test**

Append:

```python
class FailingLLMClient:
    async def refine_product_name(self, _original_name):
        raise RuntimeError("llm unavailable")


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
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd services/processor
pytest tests/test_product_processor_graph.py::test_process_product_with_graph_failure_marks_product_failed_and_continues_shape -v
```

Expected: FAIL because the graph exception bubbles out.

- [ ] **Step 3: Implement wrapper-level failure persistence**

Add to `services/processor/graphs/product_processor.py`:

```python
def _finish_all_stages(state: ProductProcessingState) -> None:
    for stage_name in list(state.get("stage_timings", {})):
        _finish_stage(state, stage_name)


async def persist_failure(
    state: ProductProcessingState,
    context: ProductProcessingContext,
    error: Exception,
) -> ProductProcessingState:
    failed_state: ProductProcessingState = {
        **state,
        "error": str(error),
    }
    _finish_all_stages(failed_state)
    context.product.status = "failed"
    context.import_run.failed_count += 1
    await context.db.commit()
    context.completed_rows.append(
        {
            "name": failed_state.get("original_name") or context.product.original_name,
            "total_ms": int(
                sum(int(stage.get("ms", 0)) for stage in failed_state.get("stage_timings", {}).values())
            ),
            "stages": [],
            "error": str(error),
        }
    )
    return failed_state
```

Replace `process_product_with_graph` with:

```python
async def process_product_with_graph(context: ProductProcessingContext) -> ProductProcessingState:
    graph = build_product_processing_graph()
    initial_state: ProductProcessingState = {
        "import_id": str(context.import_run.id),
        "product_id": str(context.product.id),
        "original_name": context.product.original_name,
        "stage_timings": {},
    }
    try:
        return await graph.ainvoke(initial_state, context=context)
    except Exception as error:
        return await persist_failure(initial_state, context, error)
```

- [ ] **Step 4: Run graph tests**

Run:

```bash
cd services/processor
pytest tests/test_product_processor_graph.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/processor/graphs/product_processor.py services/processor/tests/test_product_processor_graph.py
git commit -m "feat(processor): isolate langgraph product failures"
```

## Task 5: Delegate DB Pipeline Product Work To LangGraph

**Files:**
- Modify: `services/processor/tasks.py`
- Modify: `services/processor/tests/test_tasks.py`

- [ ] **Step 1: Add a failing delegation/progress compatibility test**

Append to `services/processor/tests/test_tasks.py`:

```python
@pytest.mark.asyncio
async def test_run_db_pipeline_delegates_products_to_langgraph_and_preserves_progress_shape():
    import uuid
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock, patch
    from tasks import _run_db_pipeline

    import_id = uuid.uuid4()
    product_id = uuid.uuid4()
    import_run = SimpleNamespace(
        id=import_id,
        status="pending",
        success_count=0,
        failed_count=0,
    )
    product = SimpleNamespace(
        id=product_id,
        original_name="원본 상품명",
        status="pending",
    )

    class FakeResult:
        def __init__(self, scalar=None, scalars=None):
            self.scalar = scalar
            self.scalars_value = scalars or []

        def scalar_one_or_none(self):
            return self.scalar

        def scalars(self):
            return self

        def all(self):
            return self.scalars_value

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[
        FakeResult(scalar=import_run),
        FakeResult(scalars=[product]),
    ])

    mock_task = MagicMock()

    async def fake_process_product_with_graph(context):
        assert context.product is product
        assert context.import_run is import_run
        context.completed_rows.append({"name": "원본 상품명", "stages": []})
        context.all_warnings[0] = [{"keyword": "브랜드"}]
        context.import_run.success_count += 1
        return {"refined_name": "정제 상품명"}

    with patch("tasks.SessionLocal") as mock_session_class, \
         patch("tasks.get_llm_client") as mock_get_llm, \
         patch("tasks.KeywordEngine") as mock_keyword_engine_class, \
         patch("tasks.CategoryMapper") as mock_category_mapper_class, \
         patch("tasks.process_product_with_graph", side_effect=fake_process_product_with_graph) as mock_graph:
        mock_session_class.return_value.__aenter__.return_value = mock_db
        mock_get_llm.return_value = object()
        mock_keyword_engine_class.return_value = object()
        mock_category_mapper_class.return_value = object()

        result = await _run_db_pipeline(mock_task, str(import_id), {}, "gemini", True)

    assert result["status"] == "Completed"
    assert result["total"] == 1
    assert mock_graph.await_count == 1
    assert import_run.status == "completed"

    progress_meta = mock_task.update_state.call_args.kwargs["meta"]
    assert set(progress_meta) == {
        "percent",
        "current",
        "total",
        "stage",
        "current_name",
        "completed_rows",
        "warnings",
    }
    assert progress_meta["stage"] == "completed_row"
    assert progress_meta["percent"] == 100
    assert progress_meta["completed_rows"][0]["name"] == "원본 상품명"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd services/processor
pytest tests/test_tasks.py::test_run_db_pipeline_delegates_products_to_langgraph_and_preserves_progress_shape -v
```

Expected: FAIL because `tasks.process_product_with_graph` is not imported and `_run_db_pipeline` still performs inline processing.

- [ ] **Step 3: Import graph helpers in tasks**

In `services/processor/tasks.py`, add near the existing imports:

```python
from graphs.product_processor import ProductProcessingContext, process_product_with_graph
```

- [ ] **Step 4: Replace the inline per-product stage body**

Inside `_run_db_pipeline`, keep this setup:

```python
prompt_manager = PromptManager(db)
llm_client = get_llm_client(llm_provider, prompt_manager)
keyword_engine = KeywordEngine(llm_client, kipris_enabled=kipris_enabled)
category_mapper = CategoryMapper()
```

Then replace the current `for index, product in enumerate(products):` body with:

```python
        for index, product in enumerate(products):
            original_name = product.original_name

            async def emit_stage(stage_name: str, _state: dict):
                pct = int(index / total_rows * 100)
                task_instance.update_state(
                    state="PROGRESS",
                    meta={
                        "percent": pct,
                        "current": index + 1,
                        "total": total_rows,
                        "stage": stage_name,
                        "current_name": original_name,
                        "completed_rows": completed_rows,
                        "warnings": all_warnings,
                    },
                )

            context = ProductProcessingContext(
                db=db,
                import_run=import_run,
                product=product,
                llm_client=llm_client,
                keyword_engine=keyword_engine,
                category_mapper=category_mapper,
                progress_emitter=emit_stage,
                completed_rows=completed_rows,
                all_warnings=all_warnings,
                row_index=index,
                total_rows=total_rows,
            )

            await process_product_with_graph(context)

            progress = int((index + 1) / total_rows * 100)
            task_instance.update_state(
                state="PROGRESS",
                meta={
                    "percent": progress,
                    "current": index + 1,
                    "total": total_rows,
                    "stage": "completed_row",
                    "current_name": original_name,
                    "completed_rows": completed_rows,
                    "warnings": all_warnings,
                },
            )
```

Keep the existing final batch status logic:

```python
        if import_run.failed_count == total_rows:
            import_run.status = "failed"
        else:
            import_run.status = "completed"
        await db.commit()
```

- [ ] **Step 5: Run the delegation test**

Run:

```bash
cd services/processor
pytest tests/test_tasks.py::test_run_db_pipeline_delegates_products_to_langgraph_and_preserves_progress_shape -v
```

Expected: PASS.

- [ ] **Step 6: Run focused processor tests**

Run:

```bash
cd services/processor
pytest tests/test_product_processor_graph.py tests/test_tasks.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add services/processor/tasks.py services/processor/tests/test_tasks.py
git commit -m "feat(processor): run db products through langgraph"
```

## Task 6: Add LangGraph Studio Configuration

**Files:**
- Create: `langgraph.json`
- Modify: `services/processor/graphs/product_processor.py`
- Modify: `services/processor/tests/test_product_processor_graph.py`

- [ ] **Step 1: Add a failing Studio export test**

Append to `services/processor/tests/test_product_processor_graph.py`:

```python
def test_product_processor_graph_exports_studio_graph():
    from graphs.product_processor import graph

    assert hasattr(graph, "ainvoke")
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd services/processor
pytest tests/test_product_processor_graph.py::test_product_processor_graph_exports_studio_graph -v
```

Expected: FAIL with `ImportError` because `graph` is not exported.

- [ ] **Step 3: Export the compiled graph**

Append to `services/processor/graphs/product_processor.py`:

```python
graph = build_product_processing_graph()
```

Create repository-root `langgraph.json`:

```json
{
  "dependencies": ["./services/processor"],
  "graphs": {
    "product_processor": "./services/processor/graphs/product_processor.py:graph"
  },
  "env": ".env"
}
```

- [ ] **Step 4: Run the Studio export test**

Run:

```bash
cd services/processor
pytest tests/test_product_processor_graph.py::test_product_processor_graph_exports_studio_graph -v
```

Expected: PASS.

- [ ] **Step 5: Verify LangGraph CLI can see the config**

If local CLI dependencies are not already installed, install dev dependencies first:

```bash
cd services/processor
pip install -r requirements-dev.txt
```

Run from repository root:

```bash
python -m langgraph.cli --help
```

Expected: command exits 0 and prints LangGraph CLI help. If the module invocation is not supported by the installed CLI package, run `langgraph --help` and expect the same result.

- [ ] **Step 6: Commit**

```bash
git add langgraph.json services/processor/graphs/product_processor.py services/processor/tests/test_product_processor_graph.py
git commit -m "chore(processor): add langgraph studio config"
```

## Task 7: Final Regression And Documentation Check

**Files:**
- Modify only files needed to fix regressions discovered by this task.

- [ ] **Step 1: Run all processor tests**

Run:

```bash
cd services/processor
pytest tests -v
```

Expected: PASS.

- [ ] **Step 2: Run repository status check**

Run:

```bash
git status --short
```

Expected: shows no unstaged files except intentional fixes from Step 1.

- [ ] **Step 3: If tests fail because `langgraph` is not installed locally, install dependencies in the processor environment**

Run:

```bash
cd services/processor
pip install -r requirements.txt
pytest tests/test_product_processor_graph.py tests/test_tasks.py -v
```

Expected: install completes and focused tests pass.

If LangGraph CLI checks are needed in this environment, install dev dependencies:

```bash
cd services/processor
pip install -r requirements-dev.txt
python -m langgraph.cli --help
```

- [ ] **Step 4: Commit regression fixes**

If Step 1 required fixes:

```bash
git add services/processor
git commit -m "test(processor): verify langgraph migration regressions"
```

If Step 1 passed without changes:

```bash
git status --short
```

Expected: clean working tree.

## Self-Review

Spec coverage:

- Celery/API/UI contract preservation is covered by Task 5.
- Product-level LangGraph migration is covered by Tasks 2 through 5.
- Model configuration remains behind `get_llm_client` and injected clients; Task 5 preserves that boundary.
- LangGraph Studio support is covered by Task 6.
- DB status retry behavior is covered by graph failure handling in Task 4 and pipeline delegation in Task 5.
- Legacy Excel `/process` non-goal is covered by only modifying `_run_db_pipeline` and not `_run_pipeline`.

Red-flag phrase scan:

- No unfinished-marker or vague catch-all implementation steps remain.
- Each code-changing task includes the concrete code or exact replacement shape needed for implementation.

Type consistency:

- `ProductProcessingContext`, `ProductProcessingState`, `build_product_processing_graph`, and `process_product_with_graph` are introduced in Task 1 and reused consistently.
- Stage names remain `refining`, `keywords`, `categorizing`, and `completed_row`.
- Celery metadata keys match the existing frontend contract.
