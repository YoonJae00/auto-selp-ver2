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
