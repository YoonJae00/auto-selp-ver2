from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QObject, Property, Signal

from app.diagnostics import sanitize_diagnostic


class BaseViewModel(QObject):
    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._field_errors: dict[str, str] = {}

    fieldErrors = Property(
        "QVariantMap", lambda self: dict(self._field_errors), notify=changed
    )

    def set_field_errors(self, errors: Mapping[str, object]) -> None:
        sanitized = {key: sanitize_diagnostic(value) for key, value in errors.items()}
        if sanitized != self._field_errors:
            self._field_errors = sanitized
            self.changed.emit()
