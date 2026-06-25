from __future__ import annotations

import logging

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlComponent

from app.ui_qml import window_effects
from app.ui_qml.application import QML_DIRECTORY, create_engine


def test_windows_10_has_safe_color_fallback() -> None:
    assert (
        window_effects.choose_backdrop("win32", (10, 0, 19045), native_available=False)
        is window_effects.Backdrop.COLOR
    )


def test_windows_11_uses_mica_when_available() -> None:
    assert (
        window_effects.choose_backdrop("win32", (10, 0, 22000), native_available=True)
        is window_effects.Backdrop.MICA
    )


def test_macos_without_native_bridge_uses_color() -> None:
    assert (
        window_effects.choose_backdrop("darwin", (14, 0, 0), native_available=False)
        is window_effects.Backdrop.COLOR
    )


def test_native_application_failure_falls_back_to_color_without_exception(caplog) -> None:
    def failing_apply(_window):
        raise RuntimeError("native token 12345 secret")

    caplog.set_level(logging.WARNING)

    applied = window_effects.apply_backdrop_policy(
        object(),
        platform="win32",
        version=(10, 0, 22000),
        native_available=True,
        native_apply=failing_apply,
    )

    assert applied is window_effects.Backdrop.COLOR
    assert "native backdrop unavailable" in caplog.text
    assert "12345" not in caplog.text
    assert "secret" not in caplog.text


def test_application_native_backdrop_failure_does_not_break_startup(qt_app, monkeypatch) -> None:
    def failing_apply(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.ui_qml.application.apply_backdrop_policy", failing_apply)

    engine = create_engine()

    assert engine.rootObjects()


def test_motion_enabled_can_be_disabled_with_environment_override(qt_app, monkeypatch) -> None:
    monkeypatch.setenv("AUTO_SELP_QML_MOTION_ENABLED", "0")
    engine = create_engine()
    component = QQmlComponent(engine)
    component.setData(
        b'import QtQuick\nimport "." as Ui\nQtObject { property bool motionEnabled: Ui.Theme.motionEnabled }',
        QUrl.fromLocalFile(str(QML_DIRECTORY / "MotionEnvironmentProbe.qml")),
    )

    probe = component.create(engine.rootContext())

    assert not component.errors()
    assert probe is not None
    assert probe.property("motionEnabled") is False


def test_motion_style_hint_failure_defaults_to_enabled() -> None:
    class BrokenApplication:
        def styleHints(self):
            raise RuntimeError("platform style hints unavailable")

    assert window_effects.detect_motion_enabled(BrokenApplication(), environ={}) is True
