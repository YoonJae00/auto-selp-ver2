from __future__ import annotations

import weakref

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QTimer


_SURVIVING_WORKERS: list[object] = []
_HOOKED_APPLICATIONS: set[int] = set()


def surviving_workers() -> tuple[object, ...]:
    """Return process-owned references to threads that outlived bounded shutdown."""
    return tuple(_SURVIVING_WORKERS)


def install_shutdown_hook() -> bool:
    """Install the longer final drain while the application is fully alive."""
    application = QCoreApplication.instance()
    if application is None:
        return False
    if id(application) not in _HOOKED_APPLICATIONS:
        _HOOKED_APPLICATIONS.add(id(application))
        application.aboutToQuit.connect(drain_surviving_workers)
    return True


def _release_survivor(reference) -> None:
    worker = reference()
    if worker in _SURVIVING_WORKERS:
        _SURVIVING_WORKERS.remove(worker)


def _poll_survivor(reference) -> None:
    worker = reference()
    if worker is None or worker not in _SURVIVING_WORKERS:
        return
    if not getattr(worker, "isRunning", lambda: False)():
        _release_survivor(reference)
        return
    QTimer.singleShot(50, lambda: _poll_survivor(reference))


def _register_survivor(worker: object) -> None:
    if worker in _SURVIVING_WORKERS:
        return
    _SURVIVING_WORKERS.append(worker)
    try:
        reference = weakref.ref(worker)
    except TypeError:
        reference = lambda: worker
    finished = getattr(worker, "finished", None)
    if finished is not None and hasattr(finished, "connect"):
        try:
            finished.connect(lambda *_: _poll_survivor(reference))
        except (RuntimeError, TypeError):
            pass
    destroyed = getattr(worker, "destroyed", None)
    if destroyed is not None and hasattr(destroyed, "connect"):
        try:
            destroyed.connect(lambda *_: _release_survivor(reference))
        except (RuntimeError, TypeError):
            pass
    _poll_survivor(reference)


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
    survivors = [worker for worker in running if getattr(worker, "isRunning", lambda: False)()]
    for worker in survivors:
        _register_survivor(worker)
    return survivors


def drain_surviving_workers(timeout_ms: int = 5000) -> tuple[object, ...]:
    """Final application-shutdown drain; any survivors remain referenced for process life."""
    stop_workers(list(_SURVIVING_WORKERS), timeout_ms=timeout_ms)
    for worker in list(_SURVIVING_WORKERS):
        if not getattr(worker, "isRunning", lambda: False)():
            _SURVIVING_WORKERS.remove(worker)
    return surviving_workers()
