from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtQml import QQmlApplicationEngine

from app.ui_qml.viewmodels.app import AppViewModel
from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel
from app.ui_qml.viewmodels.suppliers import SuppliersViewModel
from app.ui_qml.viewmodels.monitor import MonitorViewModel
from app.ui_qml.viewmodels.settings import SettingsViewModel
from app.ui_qml.viewmodels.first_run import FirstRunViewModel
from app.workers.lifecycle import drain_surviving_workers
from app.ui_qml.viewmodels.crawl import CrawlViewModel
from app.ui_qml.viewmodels.export import ExportViewModel


QML_DIRECTORY = Path(__file__).parent / "qml"


def _shutdown_view_models(adapter_studio, crawl, export=None, *, drain=drain_surviving_workers) -> None:
    adapter_studio.shutdown()
    crawl.shutdown()
    if export is not None:
        export.shutdown()
    drain()


def create_engine() -> QQmlApplicationEngine:
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(QML_DIRECTORY))
    app_view_model = AppViewModel(engine)
    suppliers_view_model = SuppliersViewModel(engine)
    adapter_studio_view_model = AdapterStudioViewModel(engine, app_view_model=app_view_model)
    crawl_view_model = CrawlViewModel(engine, app_view_model=app_view_model)
    monitor_view_model = MonitorViewModel(engine)
    export_view_model = ExportViewModel(engine, app_view_model=app_view_model)
    settings_view_model = SettingsViewModel(engine)
    first_run_view_model = FirstRunViewModel(engine)
    application = QCoreApplication.instance()
    if application is not None:
        application.aboutToQuit.connect(
            lambda: _shutdown_view_models(adapter_studio_view_model, crawl_view_model, export_view_model)
        )
    engine.rootContext().setContextProperty("AppVM", app_view_model)
    engine.rootContext().setContextProperty("SuppliersVM", suppliers_view_model)
    engine.rootContext().setContextProperty("AdapterStudioVM", adapter_studio_view_model)
    engine.rootContext().setContextProperty("CrawlVM", crawl_view_model)
    engine.rootContext().setContextProperty("MonitorVM", monitor_view_model)
    engine.rootContext().setContextProperty("ExportVM", export_view_model)
    engine.rootContext().setContextProperty("SettingsVM", settings_view_model)
    engine.rootContext().setContextProperty("FirstRunVM", first_run_view_model)
    engine.setProperty("appViewModel", app_view_model)
    engine.setProperty("suppliersViewModel", suppliers_view_model)
    engine.setProperty("adapterStudioViewModel", adapter_studio_view_model)
    engine.setProperty("crawlViewModel", crawl_view_model)
    engine.setProperty("monitorViewModel", monitor_view_model)
    engine.setProperty("exportViewModel", export_view_model)
    engine.setProperty("settingsViewModel", settings_view_model)
    engine.setProperty("firstRunViewModel", first_run_view_model)
    engine.load(QUrl.fromLocalFile(str(QML_DIRECTORY / "Main.qml")))
    if not engine.rootObjects():
        raise RuntimeError("Failed to load the QML application")
    return engine
