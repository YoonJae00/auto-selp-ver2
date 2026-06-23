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


def test_generated_yaml_requires_warning_acknowledgement_before_save(vm) -> None:
    vm.acceptGeneratedYaml(VALID_YAML)

    assert vm.yamlDirty is True
    assert vm.validationStale is True
    assert vm.canSave is False
    assert vm.save() is False
    assert vm.saveWarning["reason"] == "missing"
    vm.acknowledgeSaveWarning()
    assert vm.canSave is True
    assert vm.save() is True


def test_editing_validated_yaml_makes_validation_stale(vm) -> None:
    vm.acceptGeneratedYaml(VALID_YAML)
    tested_hash = vm.beginValidation()
    vm.acceptValidation(successful_results(), tested_hash)
    assert vm.canSave is True

    vm.setYamlText(VALID_YAML + "# user edit\n")

    assert vm.validationStale is True
    assert vm.canSave is False
    assert vm.save() is False
    assert vm.saveWarning["reason"] == "stale"
    vm.acknowledgeSaveWarning()
    assert vm.canSave is True


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
    cancelled = Signal()

    def __init__(self, *args, result=None, **kwargs) -> None:
        super().__init__()
        self.args = args
        self.kwargs = kwargs
        self.result = result
        self.cancel_requested = False

    def start(self) -> None:
        self.progress.emit("password=worker-secret")

    def requestInterruption(self) -> None:
        self.cancel_requested = True

    def isRunning(self) -> bool:
        return False


def test_probe_maps_to_shared_task_and_cancels_without_navigation_side_effect(monkeypatch) -> None:
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    app = AppViewModel()
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.save_supplier_credentials", lambda *_: None)
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
    assert made[0].cancel_requested is True
    assert app.activeTask.state == "cancelled"
    assert app.currentRoute == "suppliers"

    made[0].finished.emit(object())
    assert app.activeTask.state == "cancelled"


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
    assert made[0].args[0].fields == ("raw_product_name",)
    tested_hash = made[0].args[0].tested_yaml_hash
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


def test_qapplication_fixture_supports_qml_then_qwidget(qt_app) -> None:
    from PySide6.QtWidgets import QApplication, QWidget

    from app.ui_qml.application import create_engine

    assert isinstance(qt_app, QApplication)
    engine = create_engine()
    widget = QWidget()
    assert engine.rootObjects()
    assert widget.metaObject().className() == "QWidget"
    widget.deleteLater()


def test_worker_requests_are_typed_and_generation_carries_fallback() -> None:
    from dataclasses import is_dataclass
    from app.workers.adapter import AdapterTestRequest, GenerateRequest, PickerRequest, ProbeRequest

    for request_type in (ProbeRequest, GenerateRequest, PickerRequest, AdapterTestRequest):
        assert is_dataclass(request_type)
    request = GenerateRequest(object(), "shop", provider="openai", auto_fallback=False)
    assert request.provider == "openai"
    assert request.auto_fallback is False


def test_probe_persists_credentials_and_clears_dispatch_secret(monkeypatch) -> None:
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    saved = []
    made = []
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.save_supplier_credentials", lambda *args: saved.append(args))
    vm = AdapterStudioViewModel(app_view_model=AppViewModel(), worker_factories={"probe": lambda request: made.append(request) or FakeWorker()})
    vm.setConnectionInputs({"supplierName": "Test Shop", "mainUrl": "https://shop.example", "needsLogin": True})
    vm.setLoginInputs({"loginUrl": "https://shop.example/login", "username": "buyer", "password": "secret"})

    assert vm.probe() is True
    assert saved == [("test-shop", "buyer", "secret")]
    assert made[0].username == "buyer"
    assert made[0].password == "secret"
    assert vm._inputs["username"] == vm._inputs["password"] == ""


def test_test_and_picker_load_credentials_transiently(monkeypatch) -> None:
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    made = {"test": [], "picker": []}
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.load_supplier_credentials", lambda slug: ("stored-user", "stored-secret"))
    factories = {
        "test": lambda request: made["test"].append(request) or FakeWorker(),
        "picker": lambda request: made["picker"].append(request) or FakeWorker(),
    }
    vm = AdapterStudioViewModel(app_view_model=AppViewModel(), worker_factories=factories)
    vm.setConnectionInputs({"supplierName": "Test Shop", "mainUrl": "https://shop.example", "detailUrl": "https://shop.example/p/1", "needsLogin": True})
    vm.setLoginInputs({"loginUrl": "https://shop.example/login"})
    vm.acceptGeneratedYaml(VALID_YAML)

    assert vm.testAll() is True
    assert made["test"][0].username == "stored-user"
    assert made["test"][0].password == "stored-secret"
    vm._worker = None
    vm._busy = False
    assert vm.pickElement("adapter.product.raw_product_name") is True
    assert made["picker"][0].username == "stored-user"
    assert made["picker"][0].password == "stored-secret"


def test_generation_uses_configured_provider_and_fallback(monkeypatch) -> None:
    from app.analyzer.site_probe import ProbeResult
    from app.config import AppConfig
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    made = []
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.load_config", lambda: AppConfig(llm_provider="openai", auto_fallback_enabled=False))
    vm = AdapterStudioViewModel(app_view_model=AppViewModel(), worker_factories={"generate": lambda request: made.append(request) or FakeWorker()})
    vm._probe_result = ProbeResult("https://x", "https://x", "utf-8", False, "", "", "")
    vm.setConnectionInputs({"supplierName": "Shop", "mainUrl": "https://x"})

    assert vm.generate() is True
    assert made[0].provider == "openai"
    assert made[0].auto_fallback is False


def test_failed_validation_warning_can_be_acknowledged(vm) -> None:
    vm.acceptGeneratedYaml(VALID_YAML)
    tested_hash = vm.beginValidation()
    failed = successful_results()
    failed["raw_product_name"] = [{"url": "https://x", "value": "", "ok": False}]
    vm.acceptValidation(failed, tested_hash)

    assert vm.save() is False
    assert vm.saveWarning["reason"] == "failed"
    vm.acknowledgeSaveWarning()
    assert vm.canSave is True


def test_real_probe_worker_cancels_async_task_and_clears_secret(monkeypatch, qt_app) -> None:
    import asyncio
    from PySide6.QtTest import QSignalSpy
    from app.workers import adapter as module

    started = __import__("threading").Event()
    async def blocked_probe(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(module, "probe_site", blocked_probe)
    request = module.ProbeRequest("https://x", username="u", password="secret")
    worker = module.ProbeWorker(request)
    cancelled = QSignalSpy(worker.cancelled)
    worker.start()
    assert started.wait(2)
    worker.requestInterruption()
    assert worker.wait(2000)
    assert cancelled.count() == 1
    assert worker.request.password is None


def test_cancel_retains_running_worker_and_ignores_late_completion(monkeypatch) -> None:
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.save_supplier_credentials", lambda *_: None)
    worker = FakeWorker()
    worker.running = True
    worker.isRunning = lambda: worker.running
    app = AppViewModel()
    vm = AdapterStudioViewModel(app_view_model=app, worker_factories={"probe": lambda _request: worker})
    vm.setConnectionInputs({"supplierName": "Shop", "mainUrl": "https://x"})
    assert vm.probe() is True

    vm.cancelProbe()
    assert worker in vm._retired_workers
    worker.finished.emit(object())
    assert app.activeTask.state == "cancelled"
    assert vm.probeSummary == {}
    worker.running = False
    vm._cleanup_retired_workers()
    assert worker not in vm._retired_workers


def test_qml_exposes_validation_warning_accessibility_and_responsive_mapping() -> None:
    qml_root = Path(__file__).parents[2] / "app" / "ui_qml" / "qml"
    screen = (qml_root / "screens" / "AdapterStudioScreen.qml").read_text(encoding="utf-8")
    mapping = (qml_root / "components" / "MappingTable.qml").read_text(encoding="utf-8")

    assert 'Accessible.name: "로그인 URL"' in screen
    assert 'Accessible.name: "로그인 아이디"' in screen
    assert 'Accessible.name: "로그인 비밀번호"' in screen
    assert "root.viewModel.testAll()" in screen
    assert "root.viewModel.acknowledgeSaveWarning()" in screen
    assert "width < 720" in mapping
    assert "root.compact" in mapping


def test_generate_worker_forwards_provider_and_fallback(monkeypatch) -> None:
    from types import SimpleNamespace
    from app.workers import adapter as module

    received = {}
    async def generate(*args, **kwargs):
        received.update(kwargs)
        return SimpleNamespace(yaml_text="adapter: {}", provider_used="openai", retries=0)
    monkeypatch.setattr(module, "generate_adapter_yaml", generate)
    worker = module.GenerateWorker(module.GenerateRequest(object(), "shop", "openai", False))
    worker.start()
    assert worker.wait(2000)
    assert received["llm_provider"] == "openai"
    assert received["auto_fallback"] is False
