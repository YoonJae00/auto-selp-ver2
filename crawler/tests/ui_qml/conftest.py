from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication


@pytest.fixture(scope="session")
def qt_app() -> QGuiApplication:
    app = QGuiApplication.instance() or QGuiApplication([])
    return app
