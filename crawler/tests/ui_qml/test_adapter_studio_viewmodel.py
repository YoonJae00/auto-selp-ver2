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
        {"supplierName": "Test Shop", "mainUrl": "https://shop.example", "detailUrl": "https://shop.example/p/1"}
    )
    instance._saved = saved
    return instance


def test_yaml_hash_uses_exact_text_including_trailing_newline() -> None:
    from app.ui_qml.viewmodels.adapter_studio import yaml_content_hash

    assert yaml_content_hash("a: 1") == hashlib.sha256(b"a: 1").hexdigest()
    assert yaml_content_hash("a: 1\n") != yaml_content_hash("a: 1")


def test_excluded_category_is_removed_from_summary_and_count(vm) -> None:
    vm._probe_summary = {
        "categoryCount": 2,
        "categories": [
            {"name": "Home", "url": "/home"},
            {"name": "주방용품", "url": "/kitchen"},
        ],
    }
    vm.setCategoryExcluded("/home", True)
    summary = vm.probeSummary
    assert [c["name"] for c in summary["categories"]] == ["주방용품"]
    assert summary["categoryCount"] == 1


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


def test_extra_images_toggle_updates_yaml(vm) -> None:
    vm.acceptGeneratedYaml(VALID_YAML)

    vm.setExtraImagesEnabled(True)
    assert "extra_image_urls:" in vm.yamlText
    assert "multiple: true" in vm.yamlText

    vm.setExtraImagesEnabled(False)
    assert "extra_image_urls:" not in vm.yamlText


def test_set_url_param_writes_yaml_and_drops_selector(vm) -> None:
    vm.acceptGeneratedYaml(VALID_YAML)

    vm.setFieldUrlParam("supplier_product_code", "goodsno")
    import yaml as _yaml
    field = _yaml.safe_load(vm.yamlText)["adapter"]["product"]["supplier_product_code"]
    assert field["url_param"] == "goodsno"
    assert field["fallback_from"] == "url"
    assert "selector" not in field

    vm.setFieldUrlParam("supplier_product_code", "")
    field = _yaml.safe_load(vm.yamlText)["adapter"]["product"]["supplier_product_code"]
    assert "url_param" not in field
    assert field["fallback_from"] == "none"


def test_url_param_options_parses_sample_url(vm) -> None:
    vm.setDetailUrl("https://shop.example/goods/view?goodsno=12345&cate=001")
    options = vm.urlParamOptions()
    names = [o["name"] for o in options]
    assert names == ["goodsno", "cate"]
    assert options[0]["value"] == "12345"
    assert options[0]["display"] == "goodsno = 12345"


def test_validation_products_pivot_raw_results_by_product(vm) -> None:
    vm.acceptGeneratedYaml(VALID_YAML)
    raw = {
        "raw_product_name": [
            {"url": "https://s/1", "value": "티셔츠", "ok": True},
            {"url": "https://s/2", "value": "바지", "ok": True},
        ],
        "supply_price": [
            {"url": "https://s/1", "value": "10,000", "ok": True},
            {"url": "https://s/2", "value": "", "ok": False},
        ],
        "supplier_product_code": [
            {"url": "https://s/1", "value": "1001", "ok": True},
            {"url": "https://s/2", "value": "https://s/2", "ok": True},  # code == url → fail
        ],
    }
    vm.acceptValidation(raw, vm.beginValidation())
    products = vm.validationProducts
    assert len(products) == 2
    assert products[0]["name"] == "티셔츠"
    assert products[0]["url"] == "https://s/1"
    price0 = next(f for f in products[0]["fields"] if f["key"] == "supply_price")
    assert price0["value"] == "10,000" and price0["ok"] is True
    price1 = next(f for f in products[1]["fields"] if f["key"] == "supply_price")
    assert price1["value"] == "" and price1["ok"] is False
    # product code equal to the url must be flagged as not ok
    code1 = next(f for f in products[1]["fields"] if f["key"] == "supplier_product_code")
    assert code1["ok"] is False


def test_validation_products_include_option_results(vm) -> None:
    vm.acceptGeneratedYaml(VALID_YAML)
    raw = {
        **successful_results(),
        "option_values": [{"url": "https://s/1", "value": "2개 · 브라운, 아이보리", "ok": True}],
        "option_prices": [{"url": "https://s/1", "value": "2개 · 0, 1000", "ok": True}],
    }

    vm.acceptValidation(raw, vm.beginValidation())

    fields = vm.validationProducts[0]["fields"]
    assert next(f for f in fields if f["key"] == "option_values")["value"] == "2개 · 브라운, 아이보리"
    assert next(f for f in fields if f["key"] == "option_prices")["value"] == "2개 · 0, 1000"


def test_validation_products_empty_without_results(vm) -> None:
    assert vm.validationProducts == []


def test_needs_more_test_urls_and_add(vm) -> None:
    # fixture provides only detailUrl and no sampleProducts → 1 test url
    assert vm.testUrls == ["https://shop.example/p/1"]
    assert vm.needsMoreTestUrls is True
    assert vm.addTestUrl("https://shop.example/p/2") is True
    assert vm.addTestUrl("not-a-url") is False  # rejected
    assert vm.addTestUrl("https://shop.example/p/3") is True
    assert vm.testUrls == [
        "https://shop.example/p/1", "https://shop.example/p/2", "https://shop.example/p/3",
    ]
    assert vm.needsMoreTestUrls is False
    vm.removeTestUrl("https://shop.example/p/2")
    assert vm.needsMoreTestUrls is True


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
    vm.setConnectionInputs({"supplierName": "Shop", "mainUrl": "https://example.com", "needsLogin": True, "detailUrl": "https://p.example/1"})
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


def _row_by_key(vm, key: str) -> dict:
    return next(row for row in vm.mappingRows._rows if row["key"] == key)


def test_preview_mapping_completion_updates_mapping_rows(monkeypatch) -> None:
    from app.ui_qml.viewmodels import adapter_studio

    made = []

    class PreviewWorker(QObject):
        finished = Signal(object)
        error = Signal(str)
        progress = Signal(str)
        cancelled = Signal()

        def __init__(self, request):
            super().__init__()
            self.request = request
            made.append(self)

        def start(self):
            pass

        def requestInterruption(self):
            pass

        def isRunning(self):
            return False

    monkeypatch.setattr(adapter_studio, "MappingPreviewJob", PreviewWorker)
    vm = adapter_studio.AdapterStudioViewModel(app_view_model=AppViewModel())
    vm.setConnectionInputs({
        "supplierName": "Test Shop",
        "mainUrl": "https://shop.example",
        "detailUrl": "https://shop.example/p/1",
    })
    vm.acceptGeneratedYaml(VALID_YAML)

    assert vm.previewMapping() is True
    assert made[0].request.fields[0]["key"] == "supplier_product_code"

    made[0].finished.emit({
        "found": ["raw_product_name"],
        "missing": ["supply_price"],
        "values": {"raw_product_name": "Preview Product"},
    })

    assert _row_by_key(vm, "raw_product_name")["testValue"] == "Preview Product"
    assert _row_by_key(vm, "raw_product_name")["testOk"] is True
    assert _row_by_key(vm, "supply_price")["testValue"] == ""


def test_detail_url_change_clears_then_auto_refreshes_preview(monkeypatch, qt_app) -> None:
    from PySide6.QtTest import QTest

    from app.ui_qml.viewmodels import adapter_studio

    made = []

    class PreviewWorker(QObject):
        finished = Signal(object)
        error = Signal(str)
        progress = Signal(str)
        cancelled = Signal()

        def __init__(self, request):
            super().__init__()
            self.request = request
            made.append(self)

        def start(self):
            self.finished.emit({
                "found": ["raw_product_name"],
                "missing": [],
                "values": {"raw_product_name": "New Product"},
            })

        def requestInterruption(self):
            pass

        def isRunning(self):
            return False

    monkeypatch.setattr(adapter_studio, "MappingPreviewJob", PreviewWorker)
    vm = adapter_studio.AdapterStudioViewModel(app_view_model=AppViewModel())
    vm.setConnectionInputs({
        "supplierName": "Test Shop",
        "mainUrl": "https://shop.example",
        "detailUrl": "https://shop.example/p/1",
    })
    vm.acceptGeneratedYaml(VALID_YAML)
    vm._apply_preview_result({"found": ["raw_product_name"], "values": {"raw_product_name": "Old Product"}})

    vm.setDetailUrl("https://shop.example/p/2")

    assert _row_by_key(vm, "raw_product_name")["testValue"] == ""
    QTest.qWait(550)

    assert made[-1].request.target_url == "https://shop.example/p/2"
    assert _row_by_key(vm, "raw_product_name")["testValue"] == "New Product"


def test_adapter_studio_uses_shared_worker_implementations_without_legacy_builder() -> None:
    from app.ui_qml.viewmodels import adapter_studio
    from app.workers.adapter import AdapterTestWorker, PickerJob

    assert adapter_studio.PickerJob is PickerJob
    vm = adapter_studio.AdapterStudioViewModel()
    assert vm._factories["test"] is AdapterTestWorker
    assert not (Path(__file__).parents[2] / "app" / "ui" / "tabs" / "adapter_builder_tab.py").exists()


def test_picker_jobs_reuse_one_thread_so_playwright_never_crosses_threads(qt_app) -> None:
    """Regression: previously each pick spun a fresh QThread, so the second
    pick reused a Playwright sync session bound to a dead thread and raised
    ``greenlet.error: cannot switch to a different thread``."""
    import threading

    import app.workers.adapter as adapter_mod
    from app.workers.adapter import PickerJob, PickerRequest, stop_picker_thread

    pick_thread_ids: list[int] = []

    class _FakeSession:
        def __init__(self, headless: bool = False) -> None:
            self.is_open = True
            self.is_logged_in = False

        def open(self, storage_state: dict | None = None) -> None:
            pass

        def pick(self, url, field_label="", field_hint="", timeout_ms=60_000, field_path=""):
            pick_thread_ids.append(threading.get_ident())
            return object()

        def close(self) -> None:
            pass

    original = adapter_mod.PickerSession
    adapter_mod.PickerSession = _FakeSession
    try:
        first = PickerJob(PickerRequest(field_path="adapter.product.a", target_url="https://x"))
        first.start()
        assert first.wait(5000)
        second = PickerJob(PickerRequest(field_path="adapter.product.b", target_url="https://x"))
        second.start()
        assert second.wait(5000)
    finally:
        adapter_mod.PickerSession = original
        stop_picker_thread()

    assert len(pick_thread_ids) == 2
    assert pick_thread_ids[0] == pick_thread_ids[1], "both picks must run on the same picker thread"
    assert pick_thread_ids[0] != threading.get_ident(), "picks must not run on the main thread"


def test_mapping_preview_closed_browser_discards_session(qt_app) -> None:
    from PySide6.QtTest import QSignalSpy
    from app.workers.adapter import MappingPreviewJob, MappingPreviewRequest

    class ClosedSession:
        is_open = True
        is_logged_in = True
        closed = False

        def preview_mapping(self, url, fields):
            raise RuntimeError("Target page has been closed")

        def close(self):
            self.closed = True

    class Thread:
        _session = ClosedSession()

    thread = Thread()
    job = MappingPreviewJob(MappingPreviewRequest("", "https://shop.example/p/1", []))
    cancelled = QSignalSpy(job.cancelled)

    job._execute(thread)

    assert cancelled.count() == 1
    assert thread._session is None


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
    vm.setConnectionInputs({"supplierName": "Test Shop", "mainUrl": "https://shop.example", "needsLogin": True, "detailUrl": "https://p.example/1"})
    vm.setLoginInputs({"loginUrl": "https://shop.example/login", "username": "buyer", "password": "secret"})

    assert vm.probe() is True
    assert saved == [("studio-test-shop-5658994db300e872", "buyer", "secret")]
    assert made[0].username == "buyer"
    assert made[0].password == "secret"
    assert vm._inputs["username"] == vm._inputs["password"] == ""


def test_probe_continues_when_keyring_save_fails(monkeypatch) -> None:
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    made = []
    monkeypatch.setattr(
        "app.ui_qml.viewmodels.adapter_studio.save_supplier_credentials",
        lambda *args: (_ for _ in ()).throw(RuntimeError("keyring unavailable")),
    )
    vm = AdapterStudioViewModel(
        app_view_model=AppViewModel(),
        worker_factories={"probe": lambda request: made.append(request) or FakeWorker()},
    )
    vm.setConnectionInputs({"supplierName": "Test Shop", "mainUrl": "https://shop.example", "needsLogin": True, "detailUrl": "https://p.example/1"})
    vm.setLoginInputs({"loginUrl": "https://shop.example/login", "username": "buyer", "password": "secret"})

    assert vm.probe() is True
    assert vm.fieldErrors.get("form", "") == ""
    assert made[0].username == "buyer"
    assert made[0].password == "secret"
    assert vm._load_transient_credentials() == ("buyer", "secret")
    assert vm._mapping_credentials_available() is True


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
    vm._active_credential_key = vm._credential_key()
    vm._active_credential_identity = vm._credential_identity()
    vm._active_credential_is_studio = True
    vm.acceptGeneratedYaml(VALID_YAML)

    assert vm.testAll() is True
    assert made["test"][0].username == "stored-user"
    assert made["test"][0].password == "stored-secret"
    vm._worker = None
    vm._busy = False
    vm._app.complete_owned_task(vm._task_owner)
    vm._task_owner = None
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
    vm._category_analysis_ready = True
    vm.setConnectionInputs({"supplierName": "Shop", "mainUrl": "https://x", "detailUrl": "https://p.example/1"})

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
    vm.setConnectionInputs({"supplierName": "Shop", "mainUrl": "https://x", "detailUrl": "https://p.example/1"})
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
    assert "root.viewModel.categoryAnalysisReady" in screen
    assert 'objectName: "pickedHintConfirmDialog"' in screen
    assert "visible: root.viewModel.hasPendingHint" in screen
    assert "root.viewModel.reselectPickedHint()" in screen
    assert "root.viewModel.acceptPickedHint()" in screen
    assert "root.viewModel.canAcceptPickedHint" in screen
    assert 'size: "compact"' in mapping
    assert "Layout.preferredWidth: 88" in mapping


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


def test_overlapping_start_is_rejected_and_first_worker_remains_cancellable(monkeypatch) -> None:
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.save_supplier_credentials", lambda *_: None)
    made = []
    vm = AdapterStudioViewModel(
        app_view_model=AppViewModel(),
        worker_factories={"probe": lambda request: made.append(FakeWorker(request)) or made[-1]},
    )
    vm.setConnectionInputs({"supplierName": "Shop", "mainUrl": "https://x", "detailUrl": "https://p.example/1"})

    assert vm.probe() is True
    first = vm._worker
    assert vm.probe() is False
    assert len(made) == 1
    assert vm._worker is first
    vm.cancelProbe()
    assert first.cancel_requested is True
    first.finished.emit(object())
    assert vm._probe_result is None


def test_studio_credential_key_is_nonempty_deterministic_and_collision_safe() -> None:
    from app.ui_qml.viewmodels.adapter_studio import studio_credential_key

    first = studio_credential_key("한글도매", "https://one.example")
    assert first.startswith("studio-supplier-")
    assert first == studio_credential_key(" 한글도매 ", "https://one.example")
    assert first != studio_credential_key("한글도매", "https://two.example")
    assert first != studio_credential_key("다른도매", "https://one.example")


def test_credential_keys_do_not_cross_load_between_same_name_different_urls(monkeypatch) -> None:
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    store = {}
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.save_supplier_credentials", lambda key, user, password: store.__setitem__(key, (user, password)))
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.load_supplier_credentials", lambda key: store.get(key))
    requests = []

    def make_vm(url, password):
        vm = AdapterStudioViewModel(
            app_view_model=AppViewModel(),
            worker_factories={
                "probe": lambda request: FakeWorker(request),
                "test": lambda request: requests.append(request) or FakeWorker(request),
            },
        )
        vm.setConnectionInputs({"supplierName": "한글도매", "mainUrl": url, "detailUrl": url + "/p/1", "needsLogin": True})
        vm.setLoginInputs({"loginUrl": url + "/login", "username": "user", "password": password})
        assert vm.probe() is True
        vm.cancelProbe()
        vm.acceptGeneratedYaml(VALID_YAML)
        assert vm.testAll() is True
        return vm

    make_vm("https://one.example", "first-secret")
    make_vm("https://two.example", "second-secret")
    assert requests[0].password == "first-secret"
    assert requests[1].password == "second-secret"


def test_shutdown_cancels_waits_and_retains_unfinished_workers() -> None:
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel
    from app.workers.adapter import ProbeRequest

    worker = FakeWorker(ProbeRequest("https://x", password="secret"))
    worker.running = True
    worker.isRunning = lambda: worker.running
    waits = []
    worker.wait = lambda timeout: waits.append(timeout) or False
    vm = AdapterStudioViewModel(app_view_model=AppViewModel())
    vm._worker = worker
    vm._busy = True

    vm.shutdown()
    vm.shutdown()

    assert worker.cancel_requested is True
    assert waits and all(0 <= value <= 1500 for value in waits)
    assert worker in vm._retired_workers
    assert worker.args[0].password is None
    assert vm.probe() is False


def test_mapping_rows_never_clip_at_wide_or_narrow_width(qt_app) -> None:
    from PySide6.QtCore import QObject, QUrl
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
    from PySide6.QtTest import QTest
    from app.ui_qml.application import QML_DIRECTORY

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(QML_DIRECTORY))
    component = QQmlComponent(engine)
    component.setData(
        b'''import QtQuick\nimport QtQuick.Window\nimport QtQml.Models\nimport "components" as Components\n'''
        b'''Window { visible: true; width: 900; height: 300; QtObject { id: vm; property bool busy: false; function pickElement(x) {} function testSingle(x) {} }\n'''
        b'''Components.MappingTable { objectName: "mapping"; anchors.fill: parent; viewModel: vm;\n'''
        b'''model: ListModel { ListElement { key: "raw_product_name"; label: "Product"; fieldPath: "adapter.product.raw_product_name"; selector: ".very-long-selector"; attribute: ""; transform: ""; status: "ok"; testValue: ""; testOk: false; urlPattern: ""; urlParam: ""; urlAllowed: false; testable: true; extraEnabled: true } } } }''',
        QUrl.fromLocalFile(str(QML_DIRECTORY / "MappingGeometryProbe.qml")),
    )
    probe = component.create()
    assert probe is not None, component.errors()
    for width in (900, 600):
        probe.setProperty("width", width)
        QTest.qWait(50)
        mapping = probe.findChild(QObject, "mapping")
        assert mapping.property("firstRowHeight") > 0
        assert mapping.property("firstRowHeight") >= mapping.property("firstRowContentHeight") + 16


@pytest.mark.asyncio
async def test_saved_adapter_slug_can_load_migrated_studio_credentials(tmp_path, monkeypatch) -> None:
    from app.analyzer.adapter_schema import Adapter
    from app.crawlers.yaml_adapter import YAMLAdapter
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    store = {}
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.save_supplier_credentials", lambda key, user, password: store.__setitem__(key, (user, password)))
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.load_supplier_credentials", lambda key: store.get(key))
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.delete_supplier_credentials", lambda key: store.pop(key, None))
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.save_adapter", lambda slug, text: tmp_path / f"{slug}.yaml")
    monkeypatch.setattr("app.crawlers.yaml_adapter.load_supplier_credentials", lambda key: store.get(key))
    vm = AdapterStudioViewModel(app_view_model=AppViewModel(), worker_factories={"probe": lambda request: FakeWorker(request)})
    vm.setConnectionInputs({"supplierName": "Test Shop", "mainUrl": "https://shop.example", "needsLogin": True, "detailUrl": "https://p.example/1"})
    vm.setLoginInputs({"loginUrl": "https://shop.example/login", "username": "buyer", "password": "secret"})
    assert vm.probe() is True
    studio_key = vm._active_credential_key
    vm.cancelProbe()
    vm.acceptGeneratedYaml(VALID_YAML)
    vm.acceptValidation(successful_results(), vm.beginValidation())

    assert vm.save() is True
    assert studio_key not in store
    assert store["test-shop"] == ("buyer", "secret")
    assert vm._active_credential_key == "test-shop"

    adapter = Adapter.model_validate({
        "adapter": {
            "name": "Test Shop", "base_url": "https://shop.example",
            "login": {"required": True, "login_url": "https://shop.example/login", "fields": {"id": "#id", "password": "#pw"}, "submit": "#submit"},
        }
    })

    class Element:
        async def fill(self, _value): pass
        async def click(self): pass

    class Page:
        async def goto(self, *args, **kwargs): pass
        async def wait_for_timeout(self, _value): pass
        async def query_selector(self, selector):
            return Element() if selector in {"#id", "#pw", "#submit", "a[href*='logout']"} else None

    runtime = YAMLAdapter(adapter, None, "Test Shop", supplier_slug="test-shop")
    assert await runtime._perform_login(Page()) is True


def test_credential_migration_failure_preserves_studio_key_and_dirty_state(tmp_path, monkeypatch) -> None:
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    store = {}
    deleted = []
    saved_adapters = []

    def save_credentials(key, user, password):
        if key == "test-shop":
            raise RuntimeError("password=secret migration failed")
        store[key] = (user, password)

    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.save_supplier_credentials", save_credentials)
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.load_supplier_credentials", lambda key: store.get(key))
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.delete_supplier_credentials", lambda key: deleted.append(key))
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.save_adapter", lambda slug, text: saved_adapters.append((slug, text)) or tmp_path / f"{slug}.yaml")
    vm = AdapterStudioViewModel(app_view_model=AppViewModel(), worker_factories={"probe": lambda request: FakeWorker(request)})
    vm.setConnectionInputs({"supplierName": "Test Shop", "mainUrl": "https://shop.example", "needsLogin": True, "detailUrl": "https://p.example/1"})
    vm.setLoginInputs({"loginUrl": "https://shop.example/login", "username": "buyer", "password": "secret"})
    assert vm.probe() is True
    studio_key = vm._active_credential_key
    vm.cancelProbe()
    vm.acceptGeneratedYaml(VALID_YAML)
    vm.acceptValidation(successful_results(), vm.beginValidation())

    assert vm.save() is False
    assert saved_adapters == [("test-shop", VALID_YAML)]
    assert vm.yamlDirty is True
    assert studio_key in store
    assert deleted == []
    assert vm._active_credential_key == studio_key
    assert "어댑터 파일은 저장되었지만" in vm.fieldErrors["form"]
    assert "secret" not in vm.fieldErrors["form"]


def test_changing_supplier_identity_does_not_copy_previous_studio_credentials(tmp_path, monkeypatch) -> None:
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    store = {}
    deleted = []
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.save_supplier_credentials", lambda key, user, password: store.__setitem__(key, (user, password)))
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.load_supplier_credentials", lambda key: store.get(key))
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.delete_supplier_credentials", lambda key: deleted.append(key) or store.pop(key, None))
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.save_adapter", lambda slug, text: tmp_path / f"{slug}.yaml")
    vm = AdapterStudioViewModel(app_view_model=AppViewModel(), worker_factories={"probe": lambda request: FakeWorker(request)})
    vm.setConnectionInputs({"supplierName": "A Shop", "mainUrl": "https://a.example", "needsLogin": True, "detailUrl": "https://p.example/1"})
    vm.setLoginInputs({"loginUrl": "https://a.example/login", "username": "a", "password": "a-secret"})
    assert vm.probe() is True
    a_studio_key = vm._active_credential_key
    vm.cancelProbe()

    vm.setConnectionInputs({"supplierName": "B Shop", "mainUrl": "https://b.example", "needsLogin": True, "detailUrl": "https://p.example/1"})
    vm.setLoginInputs({"loginUrl": "https://b.example/login"})
    vm.acceptGeneratedYaml(VALID_YAML)
    vm.acceptValidation(successful_results(), vm.beginValidation())

    assert vm.save() is True
    assert a_studio_key in deleted
    assert "b-shop" not in store
    assert vm._active_credential_key is None


def test_disabling_login_deletes_only_unsaved_studio_credentials(monkeypatch) -> None:
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    store = {}
    deleted = []
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.save_supplier_credentials", lambda key, user, password: store.__setitem__(key, (user, password)))
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.delete_supplier_credentials", lambda key: deleted.append(key) or store.pop(key, None))
    vm = AdapterStudioViewModel(app_view_model=AppViewModel(), worker_factories={"probe": lambda request: FakeWorker(request)})
    vm.setConnectionInputs({"supplierName": "A Shop", "mainUrl": "https://a.example", "needsLogin": True, "detailUrl": "https://p.example/1"})
    vm.setLoginInputs({"loginUrl": "https://a.example/login", "username": "a", "password": "secret"})
    assert vm.probe() is True
    studio_key = vm._active_credential_key
    vm.cancelProbe()

    vm.setConnectionInputs({"needsLogin": False})

    assert deleted == [studio_key]
    assert vm._active_credential_key is None
    assert vm._active_credential_identity is None


def test_login_url_change_invalidates_unsaved_studio_key(monkeypatch) -> None:
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    deleted = []
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.save_supplier_credentials", lambda *_: None)
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.delete_supplier_credentials", lambda key: deleted.append(key))
    vm = AdapterStudioViewModel(app_view_model=AppViewModel(), worker_factories={"probe": lambda request: FakeWorker(request)})
    vm.setConnectionInputs({"supplierName": "A Shop", "mainUrl": "https://a.example", "needsLogin": True, "detailUrl": "https://p.example/1"})
    vm.setLoginInputs({"loginUrl": "https://a.example/login", "username": "a", "password": "secret"})
    assert vm.probe() is True
    studio_key = vm._active_credential_key
    vm.cancelProbe()

    vm.setLoginInputs({"loginUrl": "https://a.example/new-login"})

    assert deleted == [studio_key]
    assert vm._active_credential_key is None


def test_form_reset_preserves_migrated_runtime_key_but_never_reuses_it(tmp_path, monkeypatch) -> None:
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    store = {}
    deleted = []
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.save_supplier_credentials", lambda key, user, password: store.__setitem__(key, (user, password)))
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.load_supplier_credentials", lambda key: store.get(key))
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.delete_supplier_credentials", lambda key: deleted.append(key) or store.pop(key, None))
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.save_adapter", lambda slug, text: tmp_path / f"{slug}.yaml")
    vm = AdapterStudioViewModel(app_view_model=AppViewModel(), worker_factories={"probe": lambda request: FakeWorker(request)})
    vm.setConnectionInputs({"supplierName": "A Shop", "mainUrl": "https://a.example", "needsLogin": True, "detailUrl": "https://p.example/1"})
    vm.setLoginInputs({"loginUrl": "https://a.example/login", "username": "a", "password": "secret"})
    assert vm.probe() is True
    vm.cancelProbe()
    vm.acceptGeneratedYaml(VALID_YAML)
    vm.acceptValidation(successful_results(), vm.beginValidation())
    assert vm.save() is True
    assert "a-shop" in store

    vm.setConnectionInputs({"supplierName": "B Shop", "mainUrl": "https://b.example", "needsLogin": True, "detailUrl": "https://p.example/1"})

    assert "a-shop" in store
    assert "a-shop" not in deleted
    assert vm._active_credential_key is None
    assert vm._load_transient_credentials() is None


# ---------------------------------------------------------------------------
# Picker UX improvements (allProductsAutoDetected, pickerFieldHint, field hints)
# ---------------------------------------------------------------------------


def test_all_products_auto_detected_reflects_probe_result(vm) -> None:
    from types import SimpleNamespace

    ns = SimpleNamespace(
        final_url="https://example.com", encoding="utf-8", needs_login=False,
        categories=[], sample_products=[], has_all_products=True,
    )
    vm._probe_finished(ns)
    assert vm.allProductsAutoDetected is True
    assert vm.currentStage == 1

    ns2 = SimpleNamespace(
        final_url="https://example.com", encoding="utf-8", needs_login=False,
        categories=[], sample_products=[], has_all_products=False,
    )
    vm._probe_finished(ns2)
    assert vm.allProductsAutoDetected is False


def test_category_gate_blocks_generation_until_category_probe_succeeds() -> None:
    from types import SimpleNamespace
    from app.analyzer.element_picker import PickedElement
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    generated = []
    category_checks = []
    vm = AdapterStudioViewModel(
        app_view_model=AppViewModel(),
        worker_factories={
            "generate": lambda request: generated.append(request) or FakeWorker(request),
            "category_probe": lambda request: category_checks.append(request) or FakeWorker(request),
        },
    )
    vm.setConnectionInputs({"supplierName": "Shop", "mainUrl": "https://shop.example", "detailUrl": "https://p.example/1"})
    vm._probe_finished(SimpleNamespace(
        final_url="https://shop.example", encoding="utf-8", needs_login=False,
        categories=[], sample_products=[], has_all_products=False,
    ))

    assert vm.categoryAnalysisReady is False
    assert vm.generate() is False
    assert generated == []

    vm._picked(PickedElement(
        url="https://shop.example",
        selector=".raw-menu li",
        selector_candidates=[".raw-menu li", "nav li"],
        text="상의",
        attribute_values={},
    ), "adapter.categories.navigation.menu_selector")

    assert vm.hasPendingHint is False
    assert vm.pickerValidationActive is False
    assert category_checks
    assert category_checks[-1].selector == ".raw-menu li"
    vm._category_menu_analysis_finished({"categories": [{"name": "상의", "url": "https://shop.example/c/top"}]})
    assert vm.categoryAnalysisReady is True
    assert vm._probe_result.categories == [{"name": "상의", "url": "https://shop.example/c/top"}]
    assert vm._mapping_hints[-1].chosen_selector == ".raw-menu li"
    assert vm.generate() is True
    assert generated


def test_category_probe_failure_keeps_generation_blocked() -> None:
    from app.analyzer.element_picker import PickedElement
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    generated = []
    vm = AdapterStudioViewModel(
        app_view_model=AppViewModel(),
        worker_factories={
            "generate": lambda request: generated.append(request) or FakeWorker(request),
            "category_probe": lambda request: FakeWorker(request),
        },
    )
    vm._probe_result = type("Probe", (), {"categories": [], "has_all_products": False})()
    vm.setConnectionInputs({"supplierName": "Shop", "mainUrl": "https://shop.example", "detailUrl": "https://p.example/1"})

    vm._picked(PickedElement(
        url="https://shop.example",
        selector=".not-category",
        selector_candidates=[".not-category"],
        text="주방용품",
        attribute_values={},
    ), "adapter.categories.navigation.menu_selector")
    vm._category_menu_analysis_finished({"categories": []})

    assert vm.categoryAnalysisReady is False
    assert "다시 시도" in vm.categoryAnalysisMessage
    assert vm.generate() is False
    assert generated == []


def test_category_reselect_does_not_mark_analysis_ready() -> None:
    from app.analyzer.element_picker import PickedElement
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    made = []
    vm = AdapterStudioViewModel(
        app_view_model=AppViewModel(),
        worker_factories={"picker": lambda request: made.append(request) or FakeWorker(request)},
    )
    vm.setConnectionInputs({"supplierName": "Shop", "mainUrl": "https://shop.example", "detailUrl": "https://p.example/1"})
    vm._pending_hint = (
        PickedElement(url="https://shop.example", selector=".wrong", text="틀림"),
        "adapter.categories.navigation.menu_selector",
    )
    vm._has_pending_hint = True

    assert vm.reselectPickedHint() is True
    assert vm.categoryAnalysisReady is False
    assert made[-1].field_path == "adapter.categories.navigation.menu_selector"


def test_category_confirm_succeeds_even_when_yaml_is_not_ready(monkeypatch) -> None:
    from app.analyzer.element_picker import PickedElement
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    closed = []
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.close_picker_session", lambda: closed.append(True))
    vm = AdapterStudioViewModel(app_view_model=AppViewModel(), worker_factories={})
    vm.setYamlText("adapter: [")
    vm._pending_hint = (
        PickedElement(url="https://shop.example", selector=".category-menu li", text="상의"),
        "adapter.categories.navigation.menu_selector",
    )
    vm._has_pending_hint = True

    assert vm.acceptPickedHint() is True
    assert vm.categoryAnalysisReady is True
    assert vm.hasPendingHint is False
    assert closed == [True]


def test_picker_field_hint_set_per_field() -> None:
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    captured: dict[str, object] = {}

    def factory(request):
        captured["request"] = request
        return FakeWorker(request)

    vm = AdapterStudioViewModel(app_view_model=None, worker_factories={"picker": factory})
    vm.setConnectionInputs(
        {"supplierName": "Test Shop", "mainUrl": "https://example.com", "detailUrl": "https://example.com/p/1"}
    )

    # Trigger pick for all_products
    assert vm.pickAllProducts() is True
    req = captured["request"]
    assert req.field_path == "adapter.categories.all_products.url"
    assert req.field_label == "전체상품 링크"
    assert "전체상품" in req.field_hint

    # Reset state for second call
    vm._busy = False
    vm._worker = None
    vm._task_owner = None

    # Trigger pick for category menu
    assert vm.pickCategoryMenu() is True
    req = captured["request"]
    assert req.field_path == "adapter.categories.navigation.menu_selector"
    assert req.field_label == "카테고리 메뉴"
    assert "카테고리" in req.field_hint


def test_hint_text_for_path_mapping(vm) -> None:
    assert "전체상품" in vm._hint_text_for_path("adapter.categories.all_products.url")
    assert "카테고리" in vm._hint_text_for_path("adapter.categories.navigation.menu_selector")
    assert "상세페이지" in vm._hint_text_for_path("adapter.listing.product_link")
    assert vm._hint_text_for_path("adapter.product.unknown_field") == "수집할 요소를 클릭하세요."


def test_running_crawl_blocks_adapter_worker_creation() -> None:
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    app = AppViewModel()
    assert app.start_task("crawl-crawl", "상품 수집")
    made = []
    vm = AdapterStudioViewModel(
        app_view_model=app,
        worker_factories={
            name: (lambda request, operation=name: made.append((operation, request)) or FakeWorker(request))
            for name in ("probe", "generate", "test", "picker")
        },
    )
    vm.setConnectionInputs({"supplierName": "Shop", "mainUrl": "https://x", "detailUrl": "https://p.example/1"})
    assert vm.probe() is False
    assert vm.generate() is False
    assert vm.testAll() is False
    assert vm.pickElement("adapter.product.raw_product_name") is False
    assert made == []
    assert (app.activeTask.key, app.activeTask.label) == ("crawl-crawl", "상품 수집")
    assert "다른 작업" in vm.fieldErrors["form"]


def test_probe_requires_sample_product_url() -> None:
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    vm = AdapterStudioViewModel(app_view_model=AppViewModel(), worker_factories={"probe": lambda request: FakeWorker(request)})
    vm.setConnectionInputs({"supplierName": "Shop", "mainUrl": "https://x"})
    assert vm.probe() is False
    assert "detailUrl" in vm.fieldErrors
    # Once a sample product URL is supplied, probe proceeds.
    vm.setConnectionInputs({"detailUrl": "https://x/p/1"})
    assert vm.probe() is True


def test_probe_errors_when_needs_login_but_credentials_missing(monkeypatch) -> None:
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    vm = AdapterStudioViewModel(app_view_model=AppViewModel(), worker_factories={"probe": lambda request: FakeWorker(request)})
    vm.setConnectionInputs({"supplierName": "Shop", "mainUrl": "https://x", "needsLogin": True, "detailUrl": "https://p.example/1"})
    vm.setLoginInputs({"loginUrl": "", "username": "", "password": ""})

    assert vm.probe() is False
    assert "loginUrl" in vm.fieldErrors or "username" in vm.fieldErrors or "password" in vm.fieldErrors


def test_pick_element_shows_mapping_login_when_credentials_missing(monkeypatch) -> None:
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.load_supplier_credentials", lambda key: None)
    vm = AdapterStudioViewModel(app_view_model=AppViewModel(), worker_factories={"picker": lambda request: FakeWorker(request)})
    vm.setConnectionInputs({"supplierName": "Shop", "mainUrl": "https://x", "detailUrl": "https://x/p/1", "needsLogin": True})
    vm.setLoginInputs({"loginUrl": "https://x/login"})

    assert vm.pickElement("adapter.product.raw_product_name") is False
    assert vm.needsMappingLogin is True
    assert vm.pickerFieldPath == "adapter.product.raw_product_name"


def test_submit_mapping_login_stores_credentials_and_resumes_pick(monkeypatch) -> None:
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    store = {}
    made = []
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.save_supplier_credentials", lambda key, user, password: store.__setitem__(key, (user, password)))
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.load_supplier_credentials", lambda key: store.get(key))
    vm = AdapterStudioViewModel(
        app_view_model=AppViewModel(),
        worker_factories={"picker": lambda request: made.append(request) or FakeWorker(request)},
    )
    vm.setConnectionInputs({"supplierName": "Shop", "mainUrl": "https://x", "detailUrl": "https://x/p/1", "needsLogin": True})
    vm.setLoginInputs({"loginUrl": "https://x/login"})

    assert vm.pickElement("adapter.product.raw_product_name") is False
    assert vm.needsMappingLogin is True

    assert vm.submitMappingLogin({"loginUrl": "https://x/login", "username": "buyer", "password": "secret"}) is True
    assert vm.needsMappingLogin is False
    assert made and made[0].username == "buyer"
    assert made[0].password == "secret"


def test_pick_element_surfaces_manual_login_when_auto_login_fails(monkeypatch) -> None:
    from PySide6.QtCore import QObject, Signal, Slot
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    class ManualLoginWorker(QObject):
        finished = Signal(object, str)
        error = Signal(str)
        progress = Signal(str)
        cancelled = Signal()
        login_required = Signal()
        def __init__(self, request):
            super().__init__()
            self.request = request
            self._confirmed = False
            self._cancelled = False
        def start(self):
            self.progress.emit("로그인 중...")
            self.login_required.emit()
        @Slot()
        def confirmManualLogin(self):
            self._confirmed = True
        @Slot()
        def cancelManualLogin(self):
            self._cancelled = True
        def requestInterruption(self):
            pass
        def isRunning(self):
            return False

    store = {}
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.save_supplier_credentials", lambda key, user, password: store.__setitem__(key, (user, password)))
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.load_supplier_credentials", lambda key: store.get(key))
    vm = AdapterStudioViewModel(
        app_view_model=AppViewModel(),
        worker_factories={"picker": lambda request: ManualLoginWorker(request)},
    )
    vm.setConnectionInputs({"supplierName": "Shop", "mainUrl": "https://x", "detailUrl": "https://x/p/1", "needsLogin": True})
    vm.setLoginInputs({"loginUrl": "https://x/login", "username": "buyer", "password": "secret"})
    # Simulate probe having stored credentials so pickElement proceeds to the worker
    vm._active_credential_key = vm._credential_key()
    vm._active_credential_identity = vm._credential_identity()
    vm._active_credential_is_studio = True
    store[vm._active_credential_key] = ("buyer", "secret")

    assert vm.pickElement("adapter.product.raw_product_name") is True
    assert vm.manualLoginPending is True

    vm.confirmManualLogin()
    assert vm.manualLoginPending is False


def test_cancel_manual_login_resets_state(monkeypatch) -> None:
    from PySide6.QtCore import QObject, Signal, Slot
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    class ManualLoginWorker(QObject):
        finished = Signal(object, str)
        error = Signal(str)
        progress = Signal(str)
        cancelled = Signal()
        login_required = Signal()
        def __init__(self, request):
            super().__init__()
            self.request = request
        def start(self):
            self.login_required.emit()
        @Slot()
        def confirmManualLogin(self):
            pass
        @Slot()
        def cancelManualLogin(self):
            pass
        def requestInterruption(self):
            pass
        def isRunning(self):
            return False

    store = {}
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.save_supplier_credentials", lambda key, user, password: store.__setitem__(key, (user, password)))
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.load_supplier_credentials", lambda key: store.get(key))
    vm = AdapterStudioViewModel(
        app_view_model=AppViewModel(),
        worker_factories={"picker": lambda request: ManualLoginWorker(request)},
    )
    vm.setConnectionInputs({"supplierName": "Shop", "mainUrl": "https://x", "detailUrl": "https://x/p/1", "needsLogin": True})
    vm.setLoginInputs({"loginUrl": "https://x/login", "username": "buyer", "password": "secret"})
    vm._active_credential_key = vm._credential_key()
    vm._active_credential_identity = vm._credential_identity()
    vm._active_credential_is_studio = True
    store[vm._active_credential_key] = ("buyer", "secret")

    assert vm.pickElement("adapter.product.raw_product_name") is True
    assert vm.manualLoginPending is True

    vm.cancelManualLogin()
    assert vm.manualLoginPending is False


def test_accept_picked_hint_with_empty_selector_falls_back_to_candidate() -> None:
    """When the chosen selector is empty but candidates exist, use the first candidate."""
    from app.analyzer.element_picker import PickedElement
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    vm = AdapterStudioViewModel(app_view_model=AppViewModel(), worker_factories={})
    vm.acceptGeneratedYaml(VALID_YAML)
    picked = PickedElement(
        url="https://shop.example/p/1",
        selector="",
        selector_candidates=[".product-name", "h1.title"],
        text="상품",
        attribute_values={},
    )
    vm._pending_hint = (picked, "adapter.product.raw_product_name")
    vm._has_pending_hint = True

    assert vm.acceptPickedHint() is True
    assert vm._mapping_hints[-1].chosen_selector == ".product-name"
    # No form error should be set on success.
    assert vm.fieldErrors.get("form", "") == ""


def test_browser_confirmed_pick_applies_without_app_modal(monkeypatch) -> None:
    """Browser-side Yes (이 요소가 맞나요?) is the confirmation — apply immediately,
    close the browser session, and never raise a second app-side modal."""
    from app.analyzer.element_picker import PickedElement
    from app.ui_qml.viewmodels import adapter_studio
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    closed = []
    monkeypatch.setattr(adapter_studio, "close_picker_session", lambda: closed.append(True))
    vm = AdapterStudioViewModel(app_view_model=AppViewModel(), worker_factories={})
    vm.acceptGeneratedYaml(VALID_YAML)
    picked = PickedElement(
        url="https://shop.example/p/1",
        selector=".picked-name",
        selector_candidates=[".picked-name"],
        match_counts={".picked-name": 1},
        text="상품",
        attribute_values={},
    )

    vm._picked(picked, "adapter.product.raw_product_name")

    # Applied straight away, no pending app modal, browser session closed.
    assert vm.hasPendingHint is False
    assert vm._mapping_hints[-1].chosen_selector == ".picked-name"
    assert "selector: .picked-name" in vm.yamlText
    assert closed == [True]


def test_picker_cancel_resets_state_and_allows_next_pick(monkeypatch) -> None:
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    closed = []
    made = []
    monkeypatch.setattr("app.ui_qml.viewmodels.adapter_studio.close_picker_session", lambda: closed.append(True))
    vm = AdapterStudioViewModel(
        app_view_model=AppViewModel(),
        worker_factories={"picker": lambda request: made.append(FakeWorker(request)) or made[-1]},
    )
    vm.setConnectionInputs({
        "supplierName": "Test Shop",
        "mainUrl": "https://shop.example",
        "detailUrl": "https://shop.example/p/1",
    })

    assert vm.pickElement("adapter.product.raw_product_name") is True
    assert vm.busy is True
    assert vm.pickerActive is True

    made[0].cancelled.emit()

    assert vm.busy is False
    assert vm.pickerActive is False
    assert vm.hasPendingHint is False
    assert closed == [True]
    assert vm.pickElement("adapter.product.supply_price") is True
    assert len(made) == 2
    assert made[1].args[0].field_path == "adapter.product.supply_price"


def test_preview_cancel_resets_preview_state(monkeypatch) -> None:
    from app.ui_qml.viewmodels import adapter_studio

    class PreviewCancelledWorker(QObject):
        finished = Signal(object)
        error = Signal(str)
        progress = Signal(str)
        cancelled = Signal()

        def __init__(self, request):
            super().__init__()
            self.request = request

        def start(self):
            self.cancelled.emit()

        def requestInterruption(self):
            pass

        def isRunning(self):
            return False

    closed = []
    monkeypatch.setattr(adapter_studio, "MappingPreviewJob", PreviewCancelledWorker)
    monkeypatch.setattr(adapter_studio, "close_picker_session", lambda: closed.append(True))
    vm = adapter_studio.AdapterStudioViewModel(app_view_model=AppViewModel())
    vm.setConnectionInputs({
        "supplierName": "Test Shop",
        "mainUrl": "https://shop.example",
        "detailUrl": "https://shop.example/p/1",
    })
    vm.acceptGeneratedYaml(VALID_YAML)

    assert vm.previewMapping() is True
    assert vm.previewActive is False
    assert vm.busy is False
    assert closed == [True]


def test_reselect_picked_hint_restarts_same_field_without_closing_session() -> None:
    from app.analyzer.element_picker import PickedElement
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    made = []
    vm = AdapterStudioViewModel(
        app_view_model=AppViewModel(),
        worker_factories={"picker": lambda request: made.append(request) or FakeWorker(request)},
    )
    vm.setConnectionInputs({
        "supplierName": "Test Shop",
        "mainUrl": "https://shop.example",
        "detailUrl": "https://shop.example/p/1",
    })
    vm._pending_hint = (
        PickedElement(url="https://shop.example/p/1", selector=".wrong", text="틀림"),
        "adapter.product.raw_product_name",
    )
    vm._has_pending_hint = True
    vm._pending_hint_preview = "틀림"

    assert vm.reselectPickedHint() is True
    assert vm.hasPendingHint is False
    assert made[-1].field_path == "adapter.product.raw_product_name"


def test_accept_picked_hint_with_empty_selector_and_no_candidates_is_safe() -> None:
    """Empty selector with no candidates must not crash — it shows a friendly error."""
    from app.analyzer.element_picker import PickedElement
    from app.ui_qml.viewmodels.adapter_studio import AdapterStudioViewModel

    vm = AdapterStudioViewModel(app_view_model=AppViewModel(), worker_factories={})
    vm.acceptGeneratedYaml(VALID_YAML)
    picked = PickedElement(
        url="https://shop.example/p/1",
        selector="",
        selector_candidates=[],
        text="",
        attribute_values={},
    )
    vm._pending_hint = (picked, "adapter.product.raw_product_name")
    vm._has_pending_hint = True

    # Must not raise ValueError.
    assert vm.acceptPickedHint() is False
    assert "선택자" in vm.fieldErrors.get("form", "")
    # Pending hint is preserved so the user can re-pick.
    assert vm._pending_hint is not None
