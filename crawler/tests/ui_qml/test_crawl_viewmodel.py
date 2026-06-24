from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QObject, Signal

from app.ui_qml.viewmodels.app import AppViewModel


class FakeWorker(QObject):
    progress = Signal(str)
    product_found = Signal(str, str, int)
    finished = Signal(int, int)
    cancelled = Signal(int, int)
    error = Signal(str)
    categories_found = Signal(object)

    def __init__(self, request) -> None:
        super().__init__()
        self.request = request
        self.started = False
        self.cancel_requested = False

    def start(self) -> None:
        self.started = True

    def requestInterruption(self) -> None:
        self.cancel_requested = True

    def isRunning(self) -> bool:
        return False


def supplier(**overrides):
    values = dict(
        id="s1", name="Korean Shop", adapter_file="shop-adapter",
        credential_key="runtime-credential-key", default_delay_seconds=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_start_requires_supplier_and_categories() -> None:
    from app.ui_qml.viewmodels.crawl import CrawlViewModel

    vm = CrawlViewModel(app_view_model=AppViewModel(), supplier_loader=lambda: [])
    assert vm.startCrawl() is False
    assert vm.fieldErrors["supplier"] == "도매처를 선택하세요."
    assert vm.fieldErrors["categories"] == "수집할 카테고리를 선택하세요."


def test_request_uses_credential_key_and_delay_precedence(monkeypatch) -> None:
    from app.ui_qml.viewmodels.crawl import CrawlViewModel

    monkeypatch.setattr("app.ui_qml.viewmodels.crawl.adapter_exists", lambda _: True)
    monkeypatch.setattr(
        "app.ui_qml.viewmodels.crawl.load_config",
        lambda: SimpleNamespace(global_delay_seconds=7),
    )
    made = []
    vm = CrawlViewModel(
        app_view_model=AppViewModel(), supplier_loader=lambda: [supplier()],
        worker_factories={"crawl": lambda request: made.append(FakeWorker(request)) or made[-1]},
    )
    vm.selectSupplier("s1")
    vm._set_categories([SimpleNamespace(category_id="c1", name="One", path="Root / One", children=[])])
    vm.toggleCategory("c1", True)
    assert vm.startCrawl() is True
    assert made[0].request.credential_key == "runtime-credential-key"
    assert made[0].request.delay_seconds == 7


def test_discovery_builds_nested_observable_rows_and_toggle_parent() -> None:
    from app.ui_qml.viewmodels.crawl import CrawlViewModel

    made = []
    vm = CrawlViewModel(
        app_view_model=AppViewModel(), supplier_loader=lambda: [supplier()],
        worker_factories={"discovery": lambda request: made.append(FakeWorker(request)) or made[-1]},
        adapter_checker=lambda _: True,
    )
    vm.selectSupplier("s1")
    assert vm.discoverCategories() is True
    child = SimpleNamespace(category_id="child", name="Child", path="Root / Child", children=[])
    root = SimpleNamespace(category_id="root", name="Root", path="Root", children=[child])
    made[0].categories_found.emit([root])
    vm.toggleCategory("root", True)
    assert set(vm.selectedCategoryIds) == {"root", "child"}


def test_product_completion_cancel_and_late_signal_map_to_shared_task(monkeypatch) -> None:
    from app.ui_qml.viewmodels.crawl import CrawlViewModel

    monkeypatch.setattr("app.ui_qml.viewmodels.crawl.adapter_exists", lambda _: True)
    workers = []
    app = AppViewModel()
    vm = CrawlViewModel(
        app_view_model=app, supplier_loader=lambda: [supplier()],
        worker_factories={"crawl": lambda request: workers.append(FakeWorker(request)) or workers[-1]},
    )
    vm.selectSupplier("s1")
    vm._set_categories([SimpleNamespace(category_id="c1", name="One", path="One", children=[])])
    vm.toggleCategory("c1", True)
    assert vm.startCrawl() is True
    workers[0].product_found.emit("Product", "P1", 2)
    assert vm.productCount == 1 and vm.optionCount == 2
    vm.cancelCrawl()
    assert app.activeTask.state == "cancelled"
    workers[0].finished.emit(99, 99)
    assert vm.productCount == 1


def test_legacy_tab_only_imports_ui_independent_shared_workers() -> None:
    from app.ui.tabs import crawl_tab as legacy
    from app.workers.crawl import CrawlWorker

    app_root = Path(__file__).parents[2] / "app"
    legacy_source = (app_root / "ui" / "tabs" / "crawl_tab.py").read_text(encoding="utf-8")
    worker_source = (app_root / "workers" / "crawl.py").read_text(encoding="utf-8")

    assert legacy.CrawlWorker is CrawlWorker
    assert "class CrawlWorker" not in legacy_source
    assert "class DiscoverSignals" not in legacy_source
    assert "threading.Thread" not in legacy_source
    assert "QtWidgets" not in worker_source
