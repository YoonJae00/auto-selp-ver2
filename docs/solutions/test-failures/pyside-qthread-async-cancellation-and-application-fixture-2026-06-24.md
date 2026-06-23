---
title: PySide QML and QWidget tests require QApplication and real async cancellation
date: 2026-06-24
category: test-failures
module: crawler-ui-qml
problem_type: test_failure
component: testing_framework
symptoms:
  - Combined QML and legacy QWidget tests aborted the Python process
  - Cancelling a Site Studio task left its asyncio operation running
  - A late worker result could overwrite the shared task's cancelled state
root_cause: thread_violation
resolution_type: code_fix
severity: high
tags: [pyside6, qthread, asyncio, cancellation, qml, qwidget, pytest]
---

# PySide QML and QWidget tests require QApplication and real async cancellation

## Problem

The crawler migration introduced QML tests alongside a legacy QWidget suite. The shared test fixture created `QGuiApplication`, which can host QML but cannot later be upgraded to the `QApplication` required by QWidget. Site Studio cancellation also only set a Qt interruption flag and released the Python worker reference, while the asyncio task inside the thread continued.

## Symptoms

- A combined test command passed QML tests, then aborted when a legacy test constructed `QWidget`.
- Cancel changed the task panel to cancelled, but browser or generation work could continue.
- A worker emitting after cancellation could complete the task and mutate view-model state.
- Releasing the final Python reference while `QThread` was active risked `QThread: Destroyed while thread is still running`.

## What Didn't Work

- Running QML and QWidget tests in separate processes concealed the incompatible application fixture rather than fixing it.
- Calling only `QThread.requestInterruption()` did not cancel an asyncio task because asyncio does not observe Qt's interruption flag.
- Setting the view model's worker reference to `None` immediately was unsafe; cancellation is a request, not proof that the thread has stopped.

## Solution

Use one session-scoped `QApplication` fixture for all UI tests. It subclasses `QGuiApplication`, so it supports both QML and QWidget:

```python
@pytest.fixture(scope="session")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])
```

Workers keep their event loop and active asyncio task. Cancellation is forwarded thread-safely to the loop:

```python
def requestInterruption(self) -> None:
    super().requestInterruption()
    if self._loop and self._task and self._loop.is_running():
        self._loop.call_soon_threadsafe(self._task.cancel)
```

The worker catches `asyncio.CancelledError`, emits a distinct `cancelled` signal, and clears transient credentials in `finally`. The view model assigns each operation an ID, ignores callbacks from cancelled or superseded IDs, and retains cancelled workers until `isRunning()` becomes false.

## Why This Works

Qt allows exactly one GUI application instance. Starting with the more capable `QApplication` avoids an impossible in-process upgrade after QML tests. For cancellation, `Task.cancel()` injects `CancelledError` at the asyncio suspension point; using `call_soon_threadsafe` is necessary because the request originates from the GUI thread while the event loop runs in the worker thread. Retaining the QThread object matches Qt's lifetime requirements, while operation IDs prevent stale signals from changing current UI state.

## Prevention

- Run QML and QWidget targets together in one test command, not only as separate shards.
- Test cancellation with an async function that blocks indefinitely, then assert the worker stops and emits `cancelled`.
- Assert a deferred worker remains strongly referenced until it reports it is no longer running.
- Emit a fake late result after cancellation and assert task state and view-model data remain unchanged.
- Keep credentials in typed worker request objects only for dispatch and clear passwords in every worker's `finally` block.

## Related Issues

- [Product processor LangGraph migration](../architecture-patterns/product-processor-langgraph-migration-2026-05-22.md) also documents preserving `asyncio.CancelledError` semantics.
