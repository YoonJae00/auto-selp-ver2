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


def test_supplier_and_explicit_delay_precedence_and_numeric_validation(monkeypatch) -> None:
    from app.ui_qml.viewmodels.crawl import CrawlViewModel

    monkeypatch.setattr("app.ui_qml.viewmodels.crawl.load_config", lambda: SimpleNamespace(global_delay_seconds=7))
    for explicit, supplier_delay, expected in ((-1, 4, 4), (2, 4, 2)):
        made = []
        vm = CrawlViewModel(
            app_view_model=AppViewModel(), supplier_loader=lambda d=supplier_delay: [supplier(default_delay_seconds=d)],
            worker_factories={"crawl": lambda request: made.append(FakeWorker(request)) or made[-1]},
            adapter_checker=lambda _: True,
        )
        vm.selectSupplier("s1")
        vm._set_categories([SimpleNamespace(category_id="c", name="C", path="C", children=[])])
        vm.toggleCategory("c", True)
        vm.setDelaySeconds(explicit)
        assert vm.startCrawl() and made[0].request.delay_seconds == expected

    vm = CrawlViewModel(supplier_loader=lambda: [supplier()], adapter_checker=lambda _: True)
    vm.selectSupplier("s1")
    vm._set_categories([SimpleNamespace(category_id="c", name="C", path="C", children=[])])
    vm.toggleCategory("c", True)
    vm.setMaxPages(501)
    vm.setDelaySeconds(61)
    assert vm.startCrawl() is False
    assert set(vm.fieldErrors) >= {"maxPages", "delaySeconds"}


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


def test_legacy_tab_blocks_double_discovery_and_stops_workers_on_close(qt_app, monkeypatch) -> None:
    from app.ui.tabs import crawl_tab

    monkeypatch.setattr(crawl_tab.CrawlTab, "_refresh_suppliers", lambda self: None)
    tab = crawl_tab.CrawlTab()
    discovery, crawling = FakeWorker(None), FakeWorker(None)
    discovery.isRunning = lambda: True
    crawling.isRunning = lambda: True
    tab._discovery_worker = discovery
    tab._worker = None
    tab._on_discover()
    assert tab._discovery_worker is discovery

    stopped = []
    monkeypatch.setattr(crawl_tab, "stop_workers", lambda workers: stopped.extend(workers) or [])
    tab._worker = crawling
    event = SimpleNamespace(accept=lambda: stopped.append("accepted"))
    tab.closeEvent(event)
    assert discovery in stopped and crawling in stopped and "accepted" in stopped


def test_product_signal_updates_live_target() -> None:
    from app.ui_qml.viewmodels.crawl import CrawlViewModel

    app = AppViewModel()
    worker = FakeWorker(None)
    vm = CrawlViewModel(app_view_model=app, supplier_loader=lambda: [supplier()],
                        worker_factories={"crawl": lambda _: worker}, adapter_checker=lambda _: True)
    vm.selectSupplier("s1")
    vm._set_categories([SimpleNamespace(category_id="c", name="C", path="C", children=[])])
    vm.toggleCategory("c", True)
    assert vm.startCrawl()
    worker.product_found.emit("Live Product", "CODE-1", 3)
    assert vm.currentTarget == "상품 1: Live Product (CODE-1)"
    assert (vm.productCount, vm.optionCount) == (1, 3)


def test_foreign_task_and_unwinding_worker_block_start() -> None:
    from app.ui_qml.viewmodels.crawl import CrawlViewModel

    app = AppViewModel()
    app.start_task("adapter-probe", "probe")
    vm = CrawlViewModel(app_view_model=app, supplier_loader=lambda: [supplier()], adapter_checker=lambda _: True)
    assert vm.discoverCategories() is False
    assert "다른 작업" in vm.fieldErrors["form"]

    app.cancel_task()
    worker = FakeWorker(None)
    worker.isRunning = lambda: True
    vm._retired_workers.append(worker)
    assert vm.discoverCategories() is False


def test_shutdown_invalidates_late_worker_signals() -> None:
    from app.ui_qml.viewmodels.crawl import CrawlViewModel

    app = AppViewModel()
    worker = FakeWorker(None)
    vm = CrawlViewModel(app_view_model=app, supplier_loader=lambda: [supplier()],
                        worker_factories={"discovery": lambda _: worker}, adapter_checker=lambda _: True)
    vm.selectSupplier("s1")
    assert vm.discoverCategories()
    vm.shutdown()
    state = app.activeTask.state
    worker.error.emit("late secret=oops")
    worker.categories_found.emit([])
    assert app.activeTask.state == state
    assert "form" not in vm.fieldErrors


def test_shutdown_uses_last_resort_for_worker_that_ignores_cancellation() -> None:
    from app.workers.lifecycle import stop_workers

    class Stuck:
        running = True
        interrupted = terminated = False
        def requestInterruption(self): self.interrupted = True
        def isRunning(self): return self.running
        def wait(self, _timeout): return not self.running
        def terminate(self): self.terminated = True; self.running = False

    worker = Stuck()
    assert stop_workers([worker], timeout_ms=1) == []
    assert worker.interrupted and worker.terminated and not worker.running


def test_crawl_screen_scrolls_and_swaps_start_cancel_controls() -> None:
    qml = (Path(__file__).parents[2] / "app" / "ui_qml" / "qml" / "screens" / "CrawlScreen.qml").read_text(encoding="utf-8")
    assert 'objectName: "crawlScrollView"' in qml
    assert 'objectName: "crawlStartButton"' in qml
    assert 'objectName: "crawlCancelButton"' in qml
    assert "visible: !root.viewModel.busy" in qml
    assert "visible: root.viewModel.busy" in qml
    assert "implicitHeight: root.compact ? 760" in qml


class FakeSession:
    def __init__(self):
        self.run = None
    def add(self, value):
        if value.__class__.__name__ == "CrawlRun": self.run = value
    def commit(self): pass
    def rollback(self): pass
    def close(self): pass


def test_worker_closes_session_when_initial_run_commit_fails() -> None:
    from app.workers.crawl import CrawlRequest, CrawlWorker

    class BrokenSession(FakeSession):
        closed = False
        def commit(self): raise RuntimeError("database unavailable")
        def close(self): self.closed = True

    session = BrokenSession()
    worker = CrawlWorker(
        CrawlRequest("s", "shop", "adapter", [], 1, 0),
        session_factory=lambda: session,
    )
    worker.run()
    assert session.closed


def test_worker_persists_failed_run_before_adapter_check() -> None:
    from app.workers.crawl import CrawlRequest, CrawlWorker

    session = FakeSession()
    request = CrawlRequest("s", "shop", "missing", [("c", "C")], 1, 0)
    worker = CrawlWorker(request, session_factory=lambda: session, adapter_checker=lambda _: False)
    worker.run()
    assert session.run.status == "failed"
    assert session.run.finished_at is not None
    assert "어댑터" in session.run.error


def test_worker_marks_start_and_close_failures_failed() -> None:
    from app.workers.crawl import CrawlRequest, CrawlWorker

    model = SimpleNamespace(adapter=SimpleNamespace(
        browser=SimpleNamespace(channel="chromium"), login=SimpleNamespace(required=False)))

    class Engine:
        def __init__(self, fail_start=False, fail_close=False):
            self.fail_start, self.fail_close = fail_start, fail_close
        async def start(self):
            if self.fail_start: raise RuntimeError("Authorization: Bearer start-secret")
        async def close(self):
            if self.fail_close: raise RuntimeError('{"access_token":"close-secret"}')

    class Adapter:
        async def crawl_category(self, *_):
            if False: yield None

    request = CrawlRequest("s", "shop", "adapter", [("c", "C")], 1, 0)
    for engine in (Engine(fail_start=True), Engine(fail_close=True)):
        session = FakeSession()
        worker = CrawlWorker(
            request, session_factory=lambda s=session: s, adapter_checker=lambda _: True,
            adapter_loader=lambda _: model, engine_factory=lambda **_: engine,
            adapter_factory=lambda **_: Adapter(),
        )
        worker.run()
        assert session.run.status == "failed"
        assert "secret" not in session.run.error
        assert "[REDACTED]" in session.run.error


def test_worker_persists_completed_and_cancelled_statuses() -> None:
    import asyncio
    from app.workers.crawl import CrawlRequest, CrawlWorker

    model = SimpleNamespace(adapter=SimpleNamespace(
        browser=SimpleNamespace(channel="chromium"), login=SimpleNamespace(required=False)))
    class Engine:
        async def start(self): pass
        async def close(self): pass
    class Adapter:
        def __init__(self, cancel=False): self.cancel = cancel
        async def crawl_category(self, *_):
            if self.cancel: raise asyncio.CancelledError
            if False: yield None
    request = CrawlRequest("s", "shop", "adapter", [("c", "C")], 1, 0)
    for cancel, expected in ((False, "completed"), (True, "cancelled")):
        session = FakeSession()
        worker = CrawlWorker(
            request, session_factory=lambda s=session: s, adapter_checker=lambda _: True,
            adapter_loader=lambda _: model, engine_factory=lambda **_: Engine(),
            adapter_factory=lambda **_: Adapter(cancel),
        )
        worker.run()
        assert session.run.status == expected


def test_workers_close_partially_started_engine_before_terminal_signal() -> None:
    from app.workers.crawl import CategoryDiscoveryRequest, CategoryDiscoveryWorker, CrawlRequest, CrawlWorker

    model = SimpleNamespace(adapter=SimpleNamespace(
        browser=SimpleNamespace(channel="chromium"), login=SimpleNamespace(required=False)))
    class Engine:
        def __init__(self): self.closed = False
        async def start(self): raise RuntimeError("partial start")
        async def close(self): self.closed = True

    discovery_engine = Engine()
    discovery = CategoryDiscoveryWorker(
        CategoryDiscoveryRequest("shop", "adapter"), adapter_checker=lambda _: True,
        adapter_loader=lambda _: model, engine_factory=lambda **_: discovery_engine,
    )
    found = []
    discovery.categories_found.connect(found.append)
    discovery.run()
    assert discovery_engine.closed and found == []

    crawl_engine = Engine()
    session = FakeSession()
    crawl = CrawlWorker(
        CrawlRequest("s", "shop", "adapter", [("c", "C")], 1, 0),
        session_factory=lambda: session, adapter_checker=lambda _: True,
        adapter_loader=lambda _: model, engine_factory=lambda **_: crawl_engine,
    )
    crawl.run()
    assert crawl_engine.closed and session.run.status == "failed"


def test_workers_close_engine_when_start_is_cancelled() -> None:
    import asyncio
    from app.workers.crawl import CategoryDiscoveryRequest, CategoryDiscoveryWorker, CrawlRequest, CrawlWorker

    model = SimpleNamespace(adapter=SimpleNamespace(
        browser=SimpleNamespace(channel="chromium"), login=SimpleNamespace(required=False)))
    class Engine:
        closed = False
        async def start(self): raise asyncio.CancelledError
        async def close(self): self.closed = True

    discovery_engine = Engine()
    CategoryDiscoveryWorker(
        CategoryDiscoveryRequest("shop", "adapter"), adapter_checker=lambda _: True,
        adapter_loader=lambda _: model, engine_factory=lambda **_: discovery_engine,
    ).run()
    assert discovery_engine.closed

    crawl_engine, session = Engine(), FakeSession()
    CrawlWorker(
        CrawlRequest("s", "shop", "adapter", [("c", "C")], 1, 0),
        session_factory=lambda: session, adapter_checker=lambda _: True,
        adapter_loader=lambda _: model, engine_factory=lambda **_: crawl_engine,
    ).run()
    assert crawl_engine.closed and session.run.status == "cancelled"


def test_discovery_emits_only_after_engine_close() -> None:
    from app.workers.crawl import CategoryDiscoveryRequest, CategoryDiscoveryWorker

    model = SimpleNamespace(adapter=SimpleNamespace(browser=SimpleNamespace(channel="chromium")))
    class Engine:
        closed = False
        async def start(self): pass
        async def close(self): self.closed = True
    class Adapter:
        async def discover_categories(self): return ["category"]
    engine = Engine()
    worker = CategoryDiscoveryWorker(
        CategoryDiscoveryRequest("shop", "adapter"), adapter_checker=lambda _: True,
        adapter_loader=lambda _: model, engine_factory=lambda **_: engine,
        adapter_factory=lambda **_: Adapter(),
    )
    close_state = []
    worker.categories_found.connect(lambda _: close_state.append(engine.closed))
    worker.run()
    assert close_state == [True]
