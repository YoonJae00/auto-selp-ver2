from __future__ import annotations

import logging
import re
import sys
import traceback
from logging.handlers import RotatingFileHandler

from app.paths import data_dir


_QUOTED_VALUE = r'"(?:\\.|[^"\\])*"' + "|" + r"'(?:\\.|[^'\\])*'"
_AUTHORIZATION = re.compile(
    rf"(?i)(authorization\b[\"']?\s*[:=]\s*)"
    rf"({_QUOTED_VALUE}|bearer\s+[^\s,;}}]+|[^\s,;}}]+)"
)
_BEARER = re.compile(r"(?i)(\bbearer\s+)[^\s,;]+")
_CREDENTIAL = re.compile(
    r"(?i)(\b(?:api[_ -]?key|access[_ -]?token|token|password|passwd|secret)"
    rf"\b[\"']?\s*[:=]\s*)({_QUOTED_VALUE}|[^\s,;}}]+)"
)


def _redact_match(match: re.Match[str]) -> str:
    value = match.group(2)
    quote = value[0] if value[:1] in {'"', "'"} else ""
    return f"{match.group(1)}{quote}[REDACTED]{quote}"


def sanitize_diagnostic(value: object) -> str:
    """Redact credential-shaped values for persistence, logs, and UI text."""
    text = str(value)
    text = _AUTHORIZATION.sub(_redact_match, text)
    text = _BEARER.sub(r"\1[REDACTED]", text)
    return _CREDENTIAL.sub(_redact_match, text)


def configure_logging() -> None:
    log_path = data_dir() / "crawler.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
        force=True,
    )
    logging.getLogger(__name__).info("log file: %s", log_path)


def log_exception(logger: logging.Logger, message: str, exc: BaseException) -> None:
    trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error("%s: %s\n%s", message, sanitize_diagnostic(exc), sanitize_diagnostic(trace))
