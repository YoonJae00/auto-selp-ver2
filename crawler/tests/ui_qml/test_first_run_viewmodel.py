from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMetaObject, QObject

from app.config import AppConfig
from app.ui_qml.application import create_engine
from app.ui_qml.viewmodels.first_run import FirstRunViewModel


def make_first_run_vm(
    tmp_path: Path,
    *,
    keys: dict[str, str] | None = None,
    saved: list[AppConfig] | None = None,
    quit_calls: list[bool] | None = None,
) -> FirstRunViewModel:
    key_store = dict(keys or {})
    saved_configs = saved if saved is not None else []
    quit_log = quit_calls if quit_calls is not None else []

    return FirstRunViewModel(
        marker_dir=lambda: tmp_path,
        config_saver=saved_configs.append,
        key_loader=lambda provider: key_store.get(provider),
        key_saver=lambda provider, api_key: key_store.__setitem__(provider, api_key),
        app_quitter=lambda: quit_log.append(True),
    )


def test_first_run_requires_provider_key_and_browser(qt_app, tmp_path) -> None:
    vm = make_first_run_vm(tmp_path)

    assert vm.required is True
    assert vm.complete("gemini", "msedge", "") is False
    assert vm.fieldErrors["apiKey"] == "API 키를 입력하세요."
    assert not (tmp_path / ".first_run_done").exists()


def test_completion_creates_marker_and_flips_required(qt_app, tmp_path) -> None:
    saved: list[AppConfig] = []
    vm = make_first_run_vm(tmp_path, saved=saved)

    assert vm.complete("openai", "msedge", "new-secret") is True

    assert saved[-1].llm_provider == "openai"
    assert saved[-1].browser_channel == "msedge"
    assert (tmp_path / ".first_run_done").exists()
    assert vm.required is False


def test_completion_uses_existing_key_without_requiring_new_secret(qt_app, tmp_path) -> None:
    vm = make_first_run_vm(tmp_path, keys={"gemini": "stored-secret"})

    assert vm.complete("gemini", "msedge", "") is True
    assert vm.required is False


def test_cancellation_does_not_create_marker(qt_app, tmp_path) -> None:
    quit_calls: list[bool] = []
    vm = make_first_run_vm(tmp_path, quit_calls=quit_calls)

    vm.cancel()

    assert quit_calls == [True]
    assert vm.required is True
    assert not (tmp_path / ".first_run_done").exists()


def test_first_run_key_save_failure_does_not_echo_submitted_key(qt_app, tmp_path) -> None:
    vm = FirstRunViewModel(
        marker_dir=lambda: tmp_path,
        config_saver=lambda _config: None,
        key_loader=lambda _provider: None,
        key_saver=lambda _provider, api_key: (_ for _ in ()).throw(RuntimeError(f"failed {api_key}")),
        app_quitter=lambda: None,
    )

    assert vm.complete("gemini", "msedge", "TOPSECRET") is False
    assert "TOPSECRET" not in repr(vm.fieldErrors)
    assert not (tmp_path / ".first_run_done").exists()


def test_first_run_marker_routes_qml_to_first_run_screen(qt_app, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "app.ui_qml.application.FirstRunViewModel",
        lambda parent=None: make_first_run_vm(tmp_path),
    )

    engine = create_engine()
    root = engine.rootObjects()[0]

    assert b"firstRunViewModel" in engine.dynamicPropertyNames()
    assert root.findChild(QObject, "firstRunScreen") is not None
    assert root.findChild(QObject, "sidebar") is None


def test_first_run_completion_switches_to_shell_without_restart(qt_app, tmp_path) -> None:
    vm = make_first_run_vm(tmp_path)
    from app.ui_qml import application

    original = application.FirstRunViewModel
    application.FirstRunViewModel = lambda parent=None: vm
    try:
        engine = create_engine()
    finally:
        application.FirstRunViewModel = original
    root = engine.rootObjects()[0]

    assert root.findChild(QObject, "firstRunScreen") is not None
    api_key_input = root.findChild(QObject, "firstRunApiKeyInput")
    api_key_input.setProperty("text", "secret")
    complete_button = root.findChild(QObject, "firstRunCompleteButton")

    assert QMetaObject.invokeMethod(complete_button, "click") is True
    qt_app.processEvents()

    assert api_key_input.property("text") == ""
    assert root.findChild(QObject, "sidebar") is not None
