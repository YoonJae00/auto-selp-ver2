---
title: Persist crawl runs before asynchronous setup and retain workers through teardown
date: 2026-06-24
category: integration-issues
module: crawler
problem_type: integration_issue
component: background_job
symptoms:
  - Adapter and browser startup failures produced no CrawlRun audit record
  - A cancelled worker allowed another crawl to start while the original thread was still unwinding
  - Late worker signals could mutate shared task state after cancellation or shutdown
root_cause: async_timing
resolution_type: code_fix
severity: high
tags: [crawler, qthread, asyncio, persistence, cancellation, concurrency]
---

# Persist crawl runs before asynchronous setup and retain workers through teardown

## Problem

The crawler originally created its `CrawlRun` only after adapter loading and browser startup. Failures during setup were therefore invisible in history, while cancellation released the UI busy guard before the QThread had actually stopped.

## Symptoms

- Missing-adapter, browser-start, and browser-close errors did not consistently leave a failed run.
- Cancel followed immediately by Start could overlap two Playwright lifecycles.
- Completion or error signals arriving after shutdown could overwrite the shared task state.

## What Didn't Work

- Treating a cancellation request as thread completion. `asyncio.Task.cancel()` is cooperative; cleanup still runs afterward.
- Marking the run completed before `engine.close()`. A teardown failure then contradicted the persisted status.
- Clearing the active worker reference immediately without retaining it. This allowed Python/Qt lifetime and concurrency races.

## Solution

Create and commit the `CrawlRun(status="running")` before adapter checks or browser setup. Perform browser close before persisting `completed`; translate setup, crawl, and teardown exceptions into a sanitized `failed` run with `finished_at`.

At the view-model boundary, retain cancelled or completed workers until `isRunning()` becomes false. Reject starts while any retained worker is still running, and invalidate the operation generation during shutdown so queued signals become no-ops.

```python
run = CrawlRun(status="running", ...)
session.add(run)
session.commit()

try:
    await engine.start()
    await crawl_products()
    await engine.close()
    finish_run(run, "completed")
except asyncio.CancelledError:
    await engine.close()
    finish_run(run, "cancelled")
    raise
except Exception as exc:
    finish_run(run, "failed", error=sanitize(exc))
    raise
```

## Why This Works

The database record now spans the complete observable operation, including setup and teardown. Worker retention reflects actual thread lifetime rather than requested state, while generation checks make queued Qt signals harmless after cancellation or shutdown.

## Prevention

- Test missing adapters, browser start failures, browser close failures, cancellation, and normal completion against persisted run status.
- Test cancel-then-immediate-start with a worker whose `isRunning()` remains true during cleanup.
- Invalidate operation IDs before shutdown cancellation and assert late result, error, and cancelled signals do not mutate shared state.
- Never persist success until all failure-producing teardown required by the operation has completed.

## Related Issues

- [PySide QThread async cancellation and application fixture](../test-failures/pyside-qthread-async-cancellation-and-application-fixture-2026-06-24.md)
