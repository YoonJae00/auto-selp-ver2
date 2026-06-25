---
title: Make QML export startup atomic and reuse the shell detail drawer
date: 2026-06-24
category: integration-issues
module: crawler QML export
problem_type: integration_issue
component: background_job
symptoms:
  - Export worker factory or start exceptions could escape into the UI event handler
  - A start failure could leave the shared task active with a stale owner and busy state
  - Validation issue clicks navigated away instead of showing the affected product and exact issue
root_cause: missing_validation
resolution_type: code_fix
severity: high
related_components:
  - "crawler QML shell"
  - "export worker lifecycle"
tags:
  - "qml"
  - "pyside6"
  - "qthread"
  - "task-owner"
  - "startup-atomicity"
  - "detail-drawer"
---

# Make QML export startup atomic and reuse the shell detail drawer

## Problem

The export view model treated worker construction, shared-task acquisition, signal wiring, and thread start as if they could not fail. Its validation decision came from a bounded display sample rather than authoritative full-scope aggregates, and recent history was inferred by scanning one directory. It also handled validation issue clicks as navigation commands, losing the selected issue context and bypassing the shell's responsive detail presentation.

## Symptoms

- A worker-factory exception propagated before the view model could provide a sanitized inline error.
- A `worker.start()` exception occurred after task acquisition, leaving a running shared task unless every acquired state field was explicitly rolled back.
- Clicking one of several issues for the same product could show the wrong issue when selection was identified only by product code.
- Export details were unavailable in the shell's wide drawer and its 900-pixel overlay mode.
- A blocking issue beyond the first 50 displayed rows could be missed, and database changes after UI validation could cross the write boundary.
- Custom destinations and failed or cancelled attempts disappeared from directory-derived history.

## What Didn't Work

- Acquiring the shared task before constructing the worker. A factory failure then had an owner to release even though no operation existed.
- Clearing only `busy` after a start failure. The worker reference, task owner, and shared task state form one startup transaction and must be restored together.
- Resolving a clicked issue by product ID alone. A product can have multiple validation findings, so the virtualized delegate index identifies the exact issue row.
- Navigating to another route for details. This discarded export context and duplicated behavior already owned by the shell drawer.

## Solution

Treat startup as a small transaction. Validate the command, construct the typed worker before acquiring the task, then acquire with a fresh opaque owner. Signal connections, publishing busy state, and `start()` belong to one rollback-protected block because even a test double or deleted Qt object can fail during `connect`. If construction fails, sanitize and expose the error without acquiring. If connection or start fails after acquisition, clear busy/current references, run bounded worker cleanup, fail the task with the same owner, clear that owner, and return `False` so retry remains possible.

```python
try:
    worker = worker_factory(request)
except Exception as exc:
    show_error(sanitize(exc))
    return False

owner = object()
if not app.acquire_task("export", "Excel export", owner):
    return False

try:
    worker.start()
except Exception as exc:
    busy = False
    current_worker = None
    stop_workers([worker], timeout_ms=100)
    app.fail_owned_task(owner, sanitize(exc))
    task_owner = None
    return False
```

For validation detail, pass the virtualized row index to the view model. Reject out-of-range rows and summary rows without a product ID, load only the referenced `Product` through an injected session factory, and expose a compact `selectedIssueDetail` map containing product fields plus the exact issue message and severity. Opening detail toggles `AppVM.detailPanelOpen` without changing `currentRoute`.

Separate validation truth from its presentation. `validate_export_scope(session, supplier_id)` uses aggregate conditional counts over the complete supplier scope for blocking and warning totals, derives a fingerprint, and loads at most 50 representative issue rows plus a summary. `canExport` uses the aggregate counts, never the sample. The view model revalidates immediately before task acquisition and preserves warning acknowledgement only when the fingerprint is unchanged. The worker repeats authoritative validation in the same database session immediately before calling the exporter, closing the final mutation window for blocking errors.

Persist attempts in a bounded JSON operation log using temp-file plus atomic replace. Record `pending` before startup and update the same attempt to `success`, `failed`, or `cancelled`, including custom destination, supplier scope, row count, and sanitized error. Reading a corrupt store returns an empty history and the next write repairs it; history no longer depends on workbook inspection or one destination directory.

Define the export detail body as a route-specific `Component`. The application shell chooses the route's title and body once, then supplies that same component to both `DetailDrawer` instances. This extends the shared-drawer pattern without adding another breakpoint, scrim, focus trap, or Escape handler.

## Why This Works

The shared task owner is a capability: only the owner that acquired the task may fail or complete it. Ordering fallible construction before acquisition reduces rollback scope, while explicit rollback after `start()` preserves the invariant that no active task exists without a live operation. Sanitizing both paths keeps diagnostics useful without exposing secrets.

An issue index preserves identity even when multiple findings reference one product. Injected session creation keeps database access testable and bounded. Route-aware component selection keeps responsive and accessibility behavior centralized in the shell, so wide and overlay layouts render equivalent data.

## Prevention

- Test factory exceptions separately from `start()` exceptions; assert busy state, worker reference, owner, shared task state, sanitized error, and immediate retry.
- Do not acquire a shared task until all failure-prone request and worker construction that can run without ownership has succeeded.
- On post-acquisition failure, mutate the shared task only through the exact opaque owner used to acquire it.
- Pass stable row identity from virtualized delegates and reject summary rows before querying the database.
- Test route detail content on both sides of the shell breakpoint, including title, exact issue message, and representative product fields.
- Clear selected detail and close the panel when its export scope becomes stale.
- Put an explicit placeholder at supplier index zero and bind the ComboBox index back to view-model selection so the visual scope cannot disagree with the command scope.
- Make virtualized issue rows and their list keyboard-focusable; Enter, Return, Space, pointer taps, and accessibility press actions must share one activation signal.
- Place a blocking issue beyond the display cap in tests and mutate the database between UI validation and export in both view-model and worker tests.

## Related Issues

- [Persist crawl runs before asynchronous setup and retain workers through teardown](crawl-run-persistence-worker-lifecycle-2026-06-24.md)
- [Shared responsive detail drawers for QML dashboard screens](../design-patterns/qml-shared-responsive-detail-drawer-2026-06-24.md)
- [PySide QThread async cancellation and application fixture](../test-failures/pyside-qthread-async-cancellation-and-application-fixture-2026-06-24.md)
