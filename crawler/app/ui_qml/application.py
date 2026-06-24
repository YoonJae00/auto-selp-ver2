from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtQml import QQmlApplicationEngine

from app.ui_qml.viewmodels.app import AppViewModel
from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel
from app.ui_qml.viewmodels.suppliers import SuppliersViewModel
from app.workers.lifecycle import drain_surviving_workers
from app.ui_qml.viewmodels.crawl import CrawlViewModel


QML_DIRECTORY = Path(__file__).parent / "qml"


def _shutdown_view_models(adapter_studio, crawl, *, drain=drain_surviving_workers) -> None:
    adapter_studio.shutdown()
    crawl.shutdown()
    drain()


def create_engine() -> QQmlApplicationEngine:
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(QML_DIRECTORY))
    app_view_model = AppViewModel(engine)
    suppliers_view_model = SuppliersViewModel(engine)
    adapter_studio_view_model = AdapterStudioViewModel(engine, app_view_model=app_view_model)
    crawl_view_model = CrawlViewModel(engine, app_view_model=app_view_model)
    application = QCoreApplication.instance()
    if application is not None:
        application.aboutToQuit.connect(
            lambda: _shutdown_view_models(adapter_studio_view_model, crawl_view_model)
        )
    engine.rootContext().setContextProperty("AppVM", app_view_model)
    engine.rootContext().setContextProperty("SuppliersVM", suppliers_view_model)
    engine.rootContext().setContextProperty("AdapterStudioVM", adapter_studio_view_model)
    engine.rootContext().setContextProperty("CrawlVM", crawl_view_model)
    engine.setProperty("appViewModel", app_view_model)
    engine.setProperty("suppliersViewModel", suppliers_view_model)
    engine.setProperty("adapterStudioViewModel", adapter_studio_view_model)
    engine.setProperty("crawlViewModel", crawl_view_model)
    engine.load(QUrl.fromLocalFile(str(QML_DIRECTORY / "Main.qml")))
    if not engine.rootObjects():
        raise RuntimeError("Failed to load the QML application")
    return engine
