import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from sqlalchemy import select
from utils.wholesale_upload import merge_product_warnings


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


def _finish_stage(state: ProductProcessingState, stage_name: str) -> None:
    timings = state.setdefault("stage_timings", {})
    stage = timings.get(stage_name)
    if stage and "ms" not in stage:
        stage["ms"] = int((time.monotonic() - float(stage["start"])) * 1000)


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
    state.setdefault("stage_timings", {})[stage_name] = {"start": time.monotonic()}
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
    from models import ProductPlatformMapping

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


async def process_product_with_graph(context: ProductProcessingContext) -> ProductProcessingState:
    graph = build_product_processing_graph()
    return await graph.ainvoke({}, context=context)
