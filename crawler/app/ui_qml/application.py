from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlApplicationEngine


QML_DIRECTORY = Path(__file__).parent / "qml"


def create_engine() -> QQmlApplicationEngine:
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(QML_DIRECTORY))
    engine.load(QUrl.fromLocalFile(str(QML_DIRECTORY / "Main.qml")))
    if not engine.rootObjects():
        raise RuntimeError("Failed to load the QML application")
    return engine
