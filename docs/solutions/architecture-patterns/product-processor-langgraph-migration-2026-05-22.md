---
title: "DB Product Processor LangGraph Migration"
date: "2026-05-22"
category: "docs/solutions/architecture-patterns"
module: "processor"
problem_type: "architecture_pattern"
component: "background_task"
severity: "medium"
applies_when:
  - "When a Celery task is growing into a multi-stage AI workflow"
  - "When product processing needs more future stages without expanding one large loop"
  - "When existing API, task polling, and frontend progress contracts must remain stable"
tags:
  - "langgraph"
  - "celery"
  - "stategraph"
  - "product-processing"
  - "workflow"
---

# DB Product Processor LangGraph Migration

## Context

The DB-backed product processor originally handled product name refinement, keyword curation, category mapping, persistence, progress emission, and failure handling inside `_run_db_pipeline`. That worked for the current three stages, but the processor is expected to gain supplier normalization, image checks, price-policy validation, marketplace attribute generation, and review steps.

The migration needed to introduce LangGraph without changing the public shape of `/process-db`, Celery task polling, or the frontend Intelligence Capsule progress metadata.

## Guidance

Keep Celery as the batch runner and move one product's processing into a LangGraph `StateGraph`.

```text
Celery process_db_products_task
  -> load ProductImport
  -> select products where status != completed
  -> for each product:
       create ProductProcessingContext
       await process_product_with_graph(context)
       emit completed_row progress metadata
  -> finalize ProductImport status
```

The graph owns the product-level workflow:

```text
START
  -> load_product_context
  -> mark_processing
  -> refine_name
  -> curate_keywords
  -> map_categories
  -> persist_success
  -> END
```

Use a serializable `ProductProcessingState` for product data and a runtime `ProductProcessingContext` for non-serializable dependencies such as the async DB session, LLM client, keyword engine, category mapper, progress emitter, and shared trace collections.

Model selection should remain outside graph nodes. The Celery task still creates the LLM client through `get_llm_client(llm_provider, prompt_manager)`, then passes the client into the graph context. This keeps provider/model replacement as a configuration concern rather than a graph rewrite.

## Why This Matters

LangGraph gives future processing stages explicit node boundaries. Adding a step such as `validate_price_policy` or `generate_market_attributes` becomes a graph extension instead of another block inside a large loop.

The migration also keeps operational behavior stable:

- Celery task ids and task polling remain unchanged.
- Progress metadata still uses `percent`, `current`, `total`, `stage`, `current_name`, `completed_rows`, and `warnings`.
- Existing stage names such as `refining`, `keywords`, `categorizing`, and `completed_row` stay compatible with the frontend.
- Product-level failures are isolated so the batch can continue processing later products.

## Implementation Notes

Failure handling belongs at the `process_product_with_graph` wrapper boundary:

- Re-raise `asyncio.CancelledError` so worker shutdown and cancellation signals are not converted into product failures.
- Capture initial success and failure counts before graph invocation.
- If a late-stage exception occurs after partial success mutations, restore `success_count` and increment `failed_count` exactly once.
- Append a failure row to `completed_rows` with the original product name, empty `stages`, and the error string.

Keep production code strict. Do not add broad `except Exception` fallbacks that create dynamic ORM stubs for tests. If tests need to avoid import-time settings or DB coupling, patch at the test boundary or move imports inside persistence helpers while preserving real production behavior.

Use `time.monotonic()` for stage duration calculations instead of wall-clock time.

## When to Apply

Use this pattern when:

- an async task has several AI or external-service stages,
- future conditional branches are likely,
- the existing queue/task mechanism must stay in place,
- model providers should be swappable by config,
- developers need LangGraph Studio visibility for local debugging.

Avoid this pattern for very small one-step jobs where a graph would add orchestration overhead without making future changes safer.

## Verification

Useful checks after this migration:

```bash
cd services/processor
PYTHONPATH=. python -m pytest tests/test_product_processor_graph.py tests/test_tasks.py -q
```

For DB-backed regression coverage, run the full processor suite against a local Postgres container with test environment variables set:

```bash
python -m pytest tests -q
```

In the verified migration, the graph/task focused tests passed with 9 tests, and the full processor suite passed with 42 tests against local Postgres.

## Related

- `services/processor/graphs/product_processor.py`
- `services/processor/tasks.py`
- `services/processor/tests/test_product_processor_graph.py`
- `services/processor/tests/test_tasks.py`
- `docs/superpowers/specs/2026-05-22-product-processor-langgraph-migration-design.md`
- `docs/superpowers/plans/2026-05-22-product-processor-langgraph-migration.md`
