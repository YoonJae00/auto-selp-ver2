from __future__ import annotations

from PySide6.QtCore import QElapsedTimer


def stop_workers(workers: list[object], timeout_ms: int = 1500) -> list[object]:
    """Cooperatively stop threads, then terminate only as a last-resort shutdown guard."""
    unique = list(dict.fromkeys(worker for worker in workers if worker is not None))
    for worker in unique:
        if hasattr(worker, "requestInterruption"):
            worker.requestInterruption()
    timer = QElapsedTimer()
    timer.start()
    for worker in unique:
        if getattr(worker, "isRunning", lambda: False)() and hasattr(worker, "wait"):
            worker.wait(max(0, timeout_ms - timer.elapsed()))
    running = [worker for worker in unique if getattr(worker, "isRunning", lambda: False)()]
    for worker in running:
        if hasattr(worker, "terminate"):
            worker.terminate()
    for worker in running:
        if hasattr(worker, "wait"):
            worker.wait(500)
    return [worker for worker in running if getattr(worker, "isRunning", lambda: False)()]
