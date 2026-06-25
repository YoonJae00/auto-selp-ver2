from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QObject, Property, Signal

from app.ui_qml.viewmodels.base import sanitize_diagnostic


class TaskState(str, Enum):
    IDLE = "idle"
    VALIDATING = "validating"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskModel(QObject):
    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._key = ""
        self._label = ""
        self._state = TaskState.IDLE.value
        self._progress = -1.0
        self._stage = ""
        self._error_message = ""
        self._logs: list[str] = []

    key = Property(str, lambda self: self._key, notify=changed)
    label = Property(str, lambda self: self._label, notify=changed)
    state = Property(str, lambda self: self._state, notify=changed)
    progress = Property(float, lambda self: self._progress, notify=changed)
    stage = Property(str, lambda self: self._stage, notify=changed)
    errorMessage = Property(str, lambda self: self._error_message, notify=changed)
    logs = Property("QStringList", lambda self: list(self._logs), notify=changed)

    def _snapshot(self) -> tuple[object, ...]:
        return (
            self._key,
            self._label,
            self._state,
            self._progress,
            self._stage,
            self._error_message,
            tuple(self._logs),
        )

    def _emit_if_changed(self, previous: tuple[object, ...]) -> None:
        if self._snapshot() != previous:
            self.changed.emit()

    def clear(self) -> None:
        previous = self._snapshot()
        self._key = ""
        self._label = ""
        self._state = TaskState.IDLE.value
        self._progress = -1.0
        self._stage = ""
        self._error_message = ""
        self._logs = []
        self._emit_if_changed(previous)

    def start(self, key: str, label: str) -> None:
        previous = self._snapshot()
        self._key = key
        self._label = label
        self._state = TaskState.RUNNING.value
        self._progress = -1.0
        self._stage = ""
        self._error_message = ""
        self._logs = []
        self._emit_if_changed(previous)

    def update(
        self,
        stage: str,
        progress: float | None = None,
        log: str | None = None,
    ) -> None:
        previous = self._snapshot()
        self._stage = stage
        if progress is not None:
            self._progress = float(progress)
        if log is not None:
            self._logs.append(sanitize_diagnostic(log))
        self._emit_if_changed(previous)

    def complete(self) -> None:
        previous = self._snapshot()
        self._state = TaskState.COMPLETED.value
        self._progress = 1.0
        self._error_message = ""
        self._emit_if_changed(previous)

    def fail(self, message: str) -> None:
        previous = self._snapshot()
        self._state = TaskState.FAILED.value
        self._error_message = sanitize_diagnostic(message)
        self._emit_if_changed(previous)

    def cancel(self, _message: str = "") -> None:
        previous = self._snapshot()
        self._state = TaskState.CANCELLED.value
        self._error_message = ""
        self._emit_if_changed(previous)
