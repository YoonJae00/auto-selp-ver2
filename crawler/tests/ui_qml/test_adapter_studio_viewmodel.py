from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal

from app.ui_qml.viewmodels.app import AppViewModel


VALID_YAML = """adapter:
  name: Test Shop
  base_url: https://shop.example
  product:
    supplier_product_code:
      selector: .code
    raw_product_name:
      selector: h1
    supply_price:
      selector: .price
    main_image_url:
      selector: img.main
"""


def successful_results() -> dict[str, list[dict[str, object]]]:
    url = "https://shop.example/products/1"
    return {
        "supplier_product_code": [{"url": url, "value": "P1", "ok": True}],
        "raw_product_name": [{"url": url, "value": "Product", "ok": True}],
        "supply_price": [{"url": url, "value": "1000", "ok": True}],
        "main_image_url": [{"url": url, "value": "/p.jpg", "ok": True}],
    }


@pytest.fixture()
def vm(tmp_path, monkeypatch):
    import app.ui_qml.viewmodels.adapter_studio as module

    saved: list[tuple[str, str]] = []
    monkeypatch.setattr(
        module,
        "save_adapter",
        lambda slug, text: saved.append((slug, text)) or tmp_path / f"{slug}.yaml",
    )
    instance = module.AdapterStudioViewModel(app_view_model=AppViewModel())
    instance.setConnectionInputs(
        {"supplierName": "Test Shop", "mainUrl": "https://shop.example"}
    )
    instance._saved = saved
    return instance


def test_yaml_hash_uses_exact_text_including_trailing_newline() -> None:
    from app.ui_qml.viewmodels.adapter_studio import yaml_content_hash

    assert yaml_content_hash("a: 1") == hashlib.sha256(b"a: 1").hexdigest()
    assert yaml_content_hash("a: 1\n") != yaml_content_hash("a: 1")


def test_stage_is_bounded_to_four_stage_workflow(vm) -> None:
    vm.setCurrentStage(-10)
    assert vm.currentStage == 0
    vm.setCurrentStage(99)
    assert vm.currentStage == 3


def test_generated_yaml_requires_validation_before_save(vm) -> None:
    vm.acceptGeneratedYaml(VALID_YAML)

    assert vm.yamlDirty is True
    assert vm.validationStale is True
    assert vm.canSave is False
    assert vm.save() is False


def test_editing_validated_yaml_makes_validation_stale(vm) -> None:
    vm.acceptGeneratedYaml(VALID_YAML)
    tested_hash = vm.beginValidation()
    vm.acceptValidation(successful_results(), tested_hash)
    assert vm.canSave is True

    vm.setYamlText(VALID_YAML + "# user edit\n")

    assert vm.validationStale is True
    assert vm.canSave is False
    assert vm.save() is False


def test_invalid_yaml_never_saves_even_if_validation_result_is_supplied(vm) -> None:
    vm.acceptGeneratedYaml("adapter: [")
    tested_hash = vm.beginValidation()
    vm.acceptValidation(successful_results(), tested_hash)

    assert vm.canSave is False
    assert vm.save() is False
    assert "yamlText" in vm.fieldErrors


def test_valid_current_validation_allows_save(vm) -> None:
    vm.acceptGeneratedYaml(VALID_YAML)
    tested_hash = vm.beginValidation()
    vm.acceptValidation(successful_results(), tested_hash)

    assert vm.save() is True
    assert vm._saved == [("test-shop", VALID_YAML)]


def test_worker_module_does_not_depend_on_widgets() -> None:
    source = (
        Path(__file__).parents[2] / "app" / "workers" / "adapter.py"
    ).read_text(encoding="utf-8")
    assert "QtWidgets" not in source
    assert "QWidget" not in source
    assert "QTableWidget" not in source
    assert "QMessageBox" not in source


class FakeWorker(QObject):
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, *args, result=None, **kwargs) -> None:
        super().__init__()
        self.args = args
        self.kwargs = kwargs
        self.result = result
        self.cancelled = False

    def start(self) -> None:
        self.progress.emit("password=worker-secret")

    def requestInterruption(self) -> None:
        self.cancelled = True


def test_probe_maps_to_shared_task_and_cancels_without_navigation_side_effect() -> None:
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    app = AppViewModel()
    made = []

    def factory(*args, **kwargs):
        worker = FakeWorker(*args, **kwargs)
        made.append(worker)
        return worker

    vm = AdapterStudioViewModel(app_view_model=app, worker_factories={"probe": factory})
    vm.setConnectionInputs({"supplierName": "Shop", "mainUrl": "https://example.com", "needsLogin": True})
    vm.setLoginInputs({"loginUrl": "https://example.com/login", "username": "buyer", "password": "worker-secret"})

    assert vm.probe() is True
    assert app.activeTask.key == "adapter-probe"
    assert app.activeTask.state == "running"
    assert "worker-secret" not in repr(app.activeTask.logs)
    assert "worker-secret" not in repr(vm.connectionInputs)

    vm.cancelProbe()
    assert made[0].cancelled is True
    assert app.activeTask.state == "cancelled"
    assert app.currentRoute == "suppliers"


def test_single_field_test_dispatches_field_and_updates_mapping(vm) -> None:
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    app = AppViewModel()
    made = []

    def factory(*args, **kwargs):
        worker = FakeWorker(*args, **kwargs)
        made.append(worker)
        return worker

    vm = AdapterStudioViewModel(app_view_model=app, worker_factories={"test": factory})
    vm.setConnectionInputs({"supplierName": "Test Shop", "mainUrl": "https://shop.example", "detailUrl": "https://shop.example/p/1"})
    vm.acceptGeneratedYaml(VALID_YAML)

    assert vm.testSingle("raw_product_name") is True
    assert made[0].kwargs["fields"] == ["raw_product_name"]
    tested_hash = made[0].args[2]
    made[0].finished.emit({"__raw_results__": successful_results()})

    assert vm.validationStale is False
    assert vm.canSave is True
    assert app.activeTask.state == "completed"


def test_legacy_builder_resolves_shared_worker_implementations() -> None:
    from app.ui.tabs import adapter_builder_tab as legacy
    from app.workers.adapter import PickerWorker, TestWorker

    assert legacy.PickerWorker is PickerWorker
    assert legacy.TestWorker is TestWorker


def test_application_retains_studio_and_route_screen(qt_app) -> None:
    from PySide6.QtCore import QObject

    from app.ui_qml.application import create_engine

    engine = create_engine()
    root = engine.rootObjects()[0]
    app = engine.property("appViewModel")

    assert b"adapterStudioViewModel" in engine.dynamicPropertyNames()
    assert engine.property("adapterStudioViewModel") is not None
    assert root.findChild(QObject, "adapterStudioScreen") is not None
    app.navigate("adapter")
    qt_app.processEvents()
    assert app.currentRoute == "adapter"
