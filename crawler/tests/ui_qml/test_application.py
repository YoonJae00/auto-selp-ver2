from __future__ import annotations

from PySide6.QtCore import QObject, QUrl
from PySide6.QtQml import QQmlComponent

from app.ui_qml.application import QML_DIRECTORY, create_engine


def test_qml_engine_loads_one_root_object(qt_app) -> None:
    engine = create_engine()

    root_objects = engine.rootObjects()
    assert len(root_objects) == 1
    assert root_objects[0].objectName() == "appWindow"


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
        b'''Components.AppButton { objectName: "probeButton"; text: "Probe" } }''',
        qml_url,
    )

    probe = component.create(engine.rootContext())

    assert not component.errors()
    assert probe is not None
    assert probe.findChild(QObject, "probeButton") is not None


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
