# Product Processor LangGraph Migration Design

Date: 2026-05-22

## Goal

Migrate the DB-backed product processing pipeline to LangGraph while preserving the current API, Celery task contract, database status model, and frontend progress UI.

The first migration should focus on `process_db_products_task` and `_run_db_pipeline`. Legacy file-based Excel processing remains unchanged unless a later migration explicitly targets it.

## Current Context

The current DB-backed flow is:

1. `POST /process-db` reads the uploaded Excel file.
2. The API creates a `ProductImport` row and pending `Product` rows.
3. `process_db_products_task` runs in Celery.
4. `_run_db_pipeline` loops through non-completed products.
5. Each product runs these stages inline:
   - product name refinement
   - keyword curation and brand-suspicion warnings
   - Naver and Coupang category mapping
   - product and platform mapping persistence
6. Celery `update_state` emits progress metadata consumed by the frontend Intelligence Capsule.

This works, but every new processing step currently makes `_run_db_pipeline` longer and mixes orchestration, business logic, progress emission, error handling, and persistence in one function.

## Recommended Architecture

Keep Celery as the batch execution wrapper and move one-product processing into a LangGraph `StateGraph`.

```text
Celery task
  -> load ProductImport
  -> select products requiring processing
  -> for each product:
       invoke product-processing LangGraph
       emit existing Celery progress metadata
  -> finalize ProductImport status
```

The LangGraph handles a single product:

```text
START
  -> load_product_context
  -> refine_name
  -> curate_keywords
  -> map_categories
  -> persist_success
  -> END

On node failure:
  -> persist_failure
  -> END
```

This gives the project the benefits of explicit workflow nodes without changing the external task lifecycle.

## LangGraph Design

Use a typed state object for serializable product workflow data:

```python
class ProductProcessingState(TypedDict, total=False):
    import_id: str
    product_id: str
    original_name: str
    refined_name: str
    keywords: list[str]
    warnings: list[dict]
    filtered_keywords: list[str]
    naver_category: dict
    coupang_category: str
    stage_timings: dict[str, dict]
    processing_time_ms: int
    error: str
```

Use runtime context or a graph factory for non-serializable dependencies:

- async database session
- `PromptManager`
- LLM client
- `KeywordEngine`
- `CategoryMapper`
- progress emitter
- row index and total count
- accumulated `completed_rows` and `all_warnings`

The state should stay plain and serializable so the graph can later support checkpointing, Studio debugging, and replay more cleanly.

## Model Configuration

Model/provider selection should remain configuration-driven.

The graph must not hardcode Gemini, OpenAI, or any other model inside individual nodes. It should receive `llm_provider`, optional `model_name`, and prompt configuration through the existing request/config path and construct clients through the existing `get_llm_client(llm_provider, prompt_manager)` boundary.

This keeps model replacement easy:

- API request or environment config selects provider/model.
- The graph receives a prepared LLM client or provider config.
- Nodes call the abstract client methods, such as `refine_product_name`.
- Future experiments can swap one node's model without rewriting the whole pipeline.

## LangGraph Studio Support

The graph should live in an importable module, for example:

```text
services/processor/graphs/product_processor.py
```

That module should expose a compiled graph or graph factory suitable for local development.

A later implementation can add a development `langgraph.json` similar to:

```json
{
  "dependencies": ["."],
  "graphs": {
    "product_processor": "./services/processor/graphs/product_processor.py:graph"
  },
  "env": ".env"
}
```

Context7 documentation confirms that LangGraph Studio/local development uses `langgraph.json` graph entries and `langgraph dev`. This is a development and debugging UI, not a replacement for the product's existing frontend. The production progress UI should continue using Celery task metadata.

## Progress And UI Compatibility

The migration must preserve the existing Celery metadata shape:

```python
{
    "percent": int,
    "current": int,
    "total": int,
    "stage": str,
    "current_name": str,
    "completed_rows": list,
    "warnings": dict,
}
```

Existing stage names should remain stable:

- `refining`
- `keywords`
- `categorizing`
- `completed_row`

New future stages may be added, but the current stages should not be renamed in the initial migration.

## Persistence And Retry Strategy

The first migration should continue to use database state as the source of truth:

- `Product.status = "pending"` before work starts.
- `Product.status = "processing"` while the graph runs.
- `Product.status = "completed"` after successful persistence.
- `Product.status = "failed"` after unrecoverable product-level failure.
- `ProductImport.success_count` and `failed_count` are updated as they are today.

This keeps partial retry behavior compatible with the current product DB migration design. Completed products are skipped on reruns.

LangGraph checkpointing should be treated as a second-phase enhancement. If added later, use a persistent checkpointer such as Postgres and a stable thread id:

```text
product-processing:{import_id}:{product_id}
```

Checkpointing is useful for replay and deeper debugging, but it is not required for the first safe migration because the database already tracks product-level completion.

## Failure Handling

Failures should be isolated to the current product.

If a graph node fails:

1. Capture the error in state.
2. Finish any open stage timing.
3. Persist product status as `failed`.
4. Increment `ProductImport.failed_count`.
5. Append an error row to `completed_rows`.
6. Continue processing the next product.

Batch status is finalized after all selected products are attempted:

- `failed` if all attempted products failed.
- `completed` if at least one product completed successfully.

## Why LangGraph Is Worth It Here

LangGraph is valuable for this project because the product processing flow is expected to gain more steps. Future stages may include:

- supplier-specific normalization
- price policy validation
- image validation
- marketplace attribute generation
- channel-specific compliance checks
- human review
- selective retry by failed stage
- model A/B tests per node

With the current inline function, these additions would make orchestration harder to reason about. With LangGraph, each step becomes a named node with explicit inputs, outputs, and edges.

## Non-Goals

This migration does not:

- remove Celery
- change `/process-db` request or response shape
- replace the Intelligence Capsule UI with LangGraph Studio
- migrate legacy `/process` Excel output flow
- introduce human-in-the-loop review in the first implementation
- require LangGraph checkpoint persistence in the first implementation

## Implementation Outline

1. Add LangGraph dependencies to the processor service.
2. Create `services/processor/graphs/product_processor.py`.
3. Define `ProductProcessingState` and optional runtime context schema.
4. Move the current per-product stages into graph nodes:
   - `load_product_context`
   - `refine_name`
   - `curate_keywords`
   - `map_categories`
   - `persist_success`
   - `persist_failure`
5. Update `_run_db_pipeline` to invoke the graph once per product.
6. Preserve current progress metadata and stage names.
7. Add unit tests for graph success and failure paths.
8. Add compatibility tests for Celery progress metadata shape.
9. Optionally add `langgraph.json` for local Studio debugging.

## Test Plan

Unit tests:

- graph success path persists `refined_name`, `keywords`, warnings, processing time, and platform mappings
- graph failure path marks only that product as failed
- warning merge preserves supplier warnings and appends processing warnings
- model provider config is passed through the existing LLM factory boundary

Compatibility tests:

- `_run_db_pipeline` still skips completed products
- progress metadata still contains `percent`, `current`, `total`, `stage`, `current_name`, `completed_rows`, and `warnings`
- stage names used by the frontend remain stable

Regression tests:

- existing wholesale upload and smart upsert behavior remains unchanged
- pending update flags on platform mappings are not reset by processing

## Open Decisions For Implementation

- Whether to expose a compiled `graph` directly for Studio or expose a factory plus a lightweight Studio-only dependency setup.
- Whether to add LangGraph checkpointer dependencies in the first implementation or defer them until graph-level replay is needed.
- Whether future model selection should remain request-scoped only or move to persisted per-import configuration.
