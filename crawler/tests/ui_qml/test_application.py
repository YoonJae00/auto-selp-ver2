from __future__ import annotations

from app.ui_qml.application import create_engine


def test_qml_engine_loads_one_root_object(qt_app) -> None:
    engine = create_engine()

    root_objects = engine.rootObjects()
    assert len(root_objects) == 1
    assert root_objects[0].objectName() == "appWindow"
