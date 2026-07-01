from __future__ import annotations

import logging

from app.diagnostics import log_exception


def test_log_exception_redacts_credentials(caplog) -> None:
    logger = logging.getLogger("test.crawler.diagnostics")

    caplog.set_level(logging.ERROR, logger=logger.name)
    try:
        raise RuntimeError("password=pwvalue token=abc123")
    except RuntimeError as exc:
        log_exception(logger, "failed", exc)

    assert "password=[REDACTED]" in caplog.text
    assert "token=[REDACTED]" in caplog.text
    assert "pwvalue" not in caplog.text
    assert "abc123" not in caplog.text
