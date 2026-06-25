from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.config import AppConfig
from app.ui_qml.viewmodels.first_run import FirstRunViewModel
from app.ui_qml.viewmodels.settings import SettingsViewModel


@pytest.fixture(scope="session")
def qt_app() -> QApplication:
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture(autouse=True)
def completed_first_run_for_qml_engine_tests(request, monkeypatch, tmp_path):
    if request.module.__name__.endswith("test_first_run_viewmodel"):
        return
    marker = tmp_path / ".first_run_done"
    marker.write_text("done\n", encoding="utf-8")

    def make_first_run(parent=None):
        return FirstRunViewModel(parent, marker_dir=lambda: tmp_path)

    def make_settings(parent=None):
        return SettingsViewModel(
            parent,
            config_loader=lambda: AppConfig(),
            config_saver=lambda _config: None,
            key_loader=lambda _provider: None,
            key_saver=lambda _provider, _key: None,
            key_deleter=lambda _provider: None,
        )

    monkeypatch.setattr("app.ui_qml.application.FirstRunViewModel", make_first_run)
    monkeypatch.setattr("app.ui_qml.application.SettingsViewModel", make_settings)
