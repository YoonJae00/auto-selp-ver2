from __future__ import annotations

from contextlib import contextmanager

from PySide6.QtCore import QMetaObject, QObject, QPoint, Qt, QUrl, qInstallMessageHandler
from PySide6.QtGui import QColor
from PySide6.QtQml import QQmlComponent
from PySide6.QtTest import QTest

from app.ui_qml.application import QML_DIRECTORY, create_engine


@contextmanager
def capture_qt_messages():
    messages: list[str] = []

    def handler(_message_type, _context, message) -> None:
        messages.append(message)

    previous = qInstallMessageHandler(handler)
    try:
        yield messages
    finally:
        qInstallMessageHandler(previous)


def contrast_ratio(foreground: QColor, background: QColor) -> float:
    def luminance(color: QColor) -> float:
        channels = (color.redF(), color.greenF(), color.blueF())
        linear = [
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_qml_engine_loads_one_root_object(qt_app) -> None:
    with capture_qt_messages() as messages:
        engine = create_engine()

    root_objects = engine.rootObjects()
    assert len(root_objects) == 1
    assert root_objects[0].objectName() == "appWindow"
    qml_messages = [
        message
        for message in messages
        if "qml" in message.lower()
        or "binding loop" in message.lower()
        or "failed to load" in message.lower()
    ]
    assert not qml_messages


def test_qml_shell_exposes_persistent_layout_regions(qt_app) -> None:
    engine = create_engine()
    root = engine.rootObjects()[0]

    assert root.findChild(QObject, "sidebar") is not None
    assert root.findChild(QObject, "contentStack") is not None
    assert root.findChild(QObject, "taskPanel") is not None


def test_app_view_model_is_retained_and_readable_from_qml(qt_app) -> None:
    engine = create_engine()
    component = QQmlComponent(engine)
    component.setData(
        b'import QtQml\nQtObject { property string route: AppVM.currentRoute }',
        QUrl(),
    )

    bound_object = component.create(engine.rootContext())

    assert b"appViewModel" in engine.dynamicPropertyNames()
    assert not component.errors()
    assert bound_object is not None
    assert bound_object.property("route") == "suppliers"


def test_theme_and_shared_control_can_be_instantiated(qt_app) -> None:
    engine = create_engine()
    component = QQmlComponent(engine)
    qml_url = QUrl.fromLocalFile(str(QML_DIRECTORY / "ThemeControlProbe.qml"))
    component.setData(
        b'''import QtQuick\nimport "." as Ui\nimport "components" as Components\n'''
        b'''Item { property color canvasToken: Ui.Theme.canvas\n'''
        b'''Components.AppButton { objectName: "probeButton"; text: "Probe" }\n'''
        b'''Components.DataTable { objectName: "probeTable"; accessibleName: "Probe table" } }''',
        qml_url,
    )

    with capture_qt_messages() as messages:
        probe = component.create(engine.rootContext())

    assert not component.errors()
    assert not messages
    assert probe is not None
    assert probe.findChild(QObject, "probeButton") is not None
    assert probe.findChild(QObject, "probeTable") is not None


def test_shell_animations_follow_disabled_motion_theme(qt_app) -> None:
    engine = create_engine()
    component = QQmlComponent(engine)
    component.setData(
        b'''import QtQuick\nimport "." as Ui\n'''
        b'''Item { Component.onCompleted: Ui.Theme.motionEnabled = false }''',
        QUrl.fromLocalFile(str(QML_DIRECTORY / "MotionProbe.qml")),
    )

    probe = component.create(engine.rootContext())
    qt_app.processEvents()
    root = engine.rootObjects()[0]
    sidebar = root.findChild(QObject, "sidebar")
    task_panel = root.findChild(QObject, "taskPanel")

    assert not component.errors()
    assert probe is not None
    assert sidebar.property("animationDuration") == 0
    assert task_panel.property("animationDuration") == 0


def test_semantic_foregrounds_meet_wcag_contrast_in_both_themes(qt_app) -> None:
    engine = create_engine()
    component = QQmlComponent(engine)
    component.setData(
        b'''import QtQuick\nimport "." as Ui\nQtObject {\n'''
        b'''property color darkSurface: "#242424"\nproperty color lightSurface: "#FDFDFC"\n'''
        b'''property color successDark: Ui.Theme.successForegroundDark\n'''
        b'''property color warningDark: Ui.Theme.warningForegroundDark\n'''
        b'''property color dangerDark: Ui.Theme.dangerForegroundDark\n'''
        b'''property color successLight: Ui.Theme.successForegroundLight\n'''
        b'''property color warningLight: Ui.Theme.warningForegroundLight\n'''
        b'''property color dangerLight: Ui.Theme.dangerForegroundLight }''',
        QUrl.fromLocalFile(str(QML_DIRECTORY / "ContrastProbe.qml")),
    )
    with capture_qt_messages() as messages:
        probe = component.create(engine.rootContext())

    assert not component.errors()
    assert not messages
    assert probe is not None
    for token in ("successDark", "warningDark", "dangerDark"):
        assert contrast_ratio(probe.property(token), probe.property("darkSurface")) >= 4.5
    for token in ("successLight", "warningLight", "dangerLight"):
        assert contrast_ratio(probe.property(token), probe.property("lightSurface")) >= 4.5


def test_detail_drawer_switches_between_wide_pane_and_overlay(qt_app) -> None:
    engine = create_engine()
    root = engine.rootObjects()[0]
    view_model = engine.property("appViewModel")
    wide_drawer = root.findChild(QObject, "detailDrawerWide")
    overlay_drawer = root.findChild(QObject, "detailDrawerOverlay")
    scrim = root.findChild(QObject, "detailScrim")
    central_content = root.findChild(QObject, "centralContent")

    view_model.set_detail_panel_open(True)
    qt_app.processEvents()

    assert wide_drawer.property("visible") is True
    assert wide_drawer.property("modal") is False
    assert overlay_drawer.property("visible") is False
    assert scrim.property("visible") is False
    assert wide_drawer.property("width") == 320
    assert central_content.property("width") < 700

    root.setWidth(900)
    qt_app.processEvents()

    assert wide_drawer.property("visible") is False
    assert overlay_drawer.property("visible") is True
    assert overlay_drawer.property("modal") is True
    assert scrim.property("visible") is True
    assert overlay_drawer.property("x") >= 900 - overlay_drawer.property("width")
    assert central_content.property("width") > 600


def test_overlay_detail_drawer_takes_focus_and_escape_closes_it(qt_app) -> None:
    engine = create_engine()
    root = engine.rootObjects()[0]
    root.setWidth(900)
    view_model = engine.property("appViewModel")
    overlay_drawer = root.findChild(QObject, "detailDrawerOverlay")
    content_stack = root.findChild(QObject, "contentStack")
    content_stack.setProperty("focus", True)
    qt_app.processEvents()

    view_model.set_detail_panel_open(True)
    qt_app.processEvents()

    assert overlay_drawer.property("activeFocus") is True

    QTest.keyClick(root, Qt.Key_Escape)
    qt_app.processEvents()

    assert view_model.property("detailPanelOpen") is False
    assert content_stack.property("activeFocus") is True


def test_overlay_detail_drawer_close_button_closes_it(qt_app) -> None:
    engine = create_engine()
    root = engine.rootObjects()[0]
    root.setWidth(900)
    view_model = engine.property("appViewModel")
    overlay_drawer = root.findChild(QObject, "detailDrawerOverlay")
    close_button = overlay_drawer.findChild(QObject, "drawerCloseButton")

    view_model.set_detail_panel_open(True)
    qt_app.processEvents()

    assert close_button is not None
    assert QMetaObject.invokeMethod(close_button, "click") is True
    qt_app.processEvents()

    assert view_model.property("detailPanelOpen") is False


def test_data_table_fallback_rows_are_pointer_selectable(qt_app) -> None:
    engine = create_engine()
    component = QQmlComponent(engine)
    component.setData(
        b'''import QtQuick\nimport QtQuick.Controls.Basic\n'''
        b'''import "components" as Components\n'''
        b'''ApplicationWindow { width: 300; height: 150; visible: true\n'''
        b'''Components.DataTable { anchors.fill: parent; model: ["first", "second"] } }''',
        QUrl.fromLocalFile(str(QML_DIRECTORY / "DataTableProbe.qml")),
    )
    window = component.create(engine.rootContext())
    view = window.findChild(QObject, "dataTableView") if window else None

    assert not component.errors()
    assert window is not None
    assert view is not None
    QTest.qWaitForWindowExposed(window)
    window.requestActivate()
    QTest.qWaitForWindowActive(window)
    QTest.qWait(50)
    qt_app.processEvents()

    QTest.mouseClick(window, Qt.LeftButton, pos=QPoint(60, 54))
    qt_app.processEvents()

    assert view.property("currentIndex") == 1


def test_task_panel_log_view_tracks_newest_entry(qt_app) -> None:
    engine = create_engine()
    root = engine.rootObjects()[0]
    view_model = engine.property("appViewModel")
    view_model.start_task("probe", "Probe")
    view_model.update_task("running", 0.5, "first")
    view_model.update_task("running", 0.6, "second")
    qt_app.processEvents()
    log_view = root.findChild(QObject, "taskLogView")

    assert log_view is not None
    assert log_view.property("cursorPosition") == len(log_view.property("text"))


def test_navigation_updates_content_stack_index(qt_app) -> None:
    engine = create_engine()
    root = engine.rootObjects()[0]
    content_stack = root.findChild(QObject, "contentStack")
    view_model = engine.property("appViewModel")

    assert content_stack is not None
    assert content_stack.property("currentIndex") == 0

    view_model.navigate("monitor")
    qt_app.processEvents()

    assert content_stack.property("currentIndex") == 3
