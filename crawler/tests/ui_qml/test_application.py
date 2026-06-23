from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlComponent

from app.ui_qml.application import create_engine


def test_qml_engine_loads_one_root_object(qt_app) -> None:
    engine = create_engine()

    root_objects = engine.rootObjects()
    assert len(root_objects) == 1
    assert root_objects[0].objectName() == "appWindow"


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
