from __future__ import annotations

import re
from collections.abc import Mapping

from PySide6.QtCore import QObject, Property, Signal


_AUTHORIZATION = re.compile(
    r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+"
)
_BEARER = re.compile(r"(?i)(\bbearer\s+)[^\s,;]+")
_CREDENTIAL = re.compile(
    r"(?i)(\b(?:api[_ -]?key|access[_ -]?token|token|password|passwd|secret)"
    r"\b[\"']?\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;}]+)"
)


def sanitize_diagnostic(value: object) -> str:
    """Redact common credential forms before text reaches the UI."""
    text = str(value)
    text = _AUTHORIZATION.sub(r"\1[REDACTED]", text)
    text = _BEARER.sub(r"\1[REDACTED]", text)

    def redact_credential(match: re.Match[str]) -> str:
        credential = match.group(2)
        quote = credential[0] if credential[:1] in {'"', "'"} else ""
        return f"{match.group(1)}{quote}[REDACTED]{quote}"

    return _CREDENTIAL.sub(redact_credential, text)


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
