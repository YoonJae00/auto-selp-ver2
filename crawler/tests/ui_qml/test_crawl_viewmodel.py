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


def test_qml_crawl_view_model_uses_ui_independent_shared_workers() -> None:
    from app.ui_qml.viewmodels import crawl
    from app.workers.crawl import CrawlWorker

    app_root = Path(__file__).parents[2] / "app"
    view_model_source = (app_root / "ui_qml" / "viewmodels" / "crawl.py").read_text(encoding="utf-8")
    worker_source = (app_root / "workers" / "crawl.py").read_text(encoding="utf-8")

    assert crawl.CrawlWorker is CrawlWorker
    assert "class CrawlWorker" not in view_model_source
    assert "class DiscoverSignals" not in view_model_source
    assert "threading.Thread" not in view_model_source
    assert "QtWidgets" not in worker_source
    assert not (app_root / "ui" / "tabs" / "crawl_tab.py").exists()


def test_crawl_view_model_blocks_double_discovery_and_stops_workers_on_shutdown(monkeypatch) -> None:
    from app.ui_qml.viewmodels.crawl import CrawlViewModel

    monkeypatch.setattr("app.ui_qml.viewmodels.crawl.adapter_exists", lambda _: True)
    workers = []
    vm = CrawlViewModel(supplier_loader=lambda: [supplier()],
                        worker_factories={"discovery": lambda request: workers.append(FakeWorker(request)) or workers[-1]})
    vm.selectSupplier("s1")
    assert vm.discoverCategories() is True
    assert vm.discoverCategories() is False

    stopped = []
    monkeypatch.setattr("app.ui_qml.viewmodels.crawl.stop_workers", lambda workers: stopped.extend(workers) or [])
    vm.shutdown()
    assert workers[0] in stopped


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


def test_process_registry_retains_survivor_after_viewmodel_deletion(qt_app) -> None:
    import gc
    import weakref
    from PySide6.QtCore import QObject, Signal
    from app.ui_qml.viewmodels.crawl import CrawlViewModel
    from app.workers.lifecycle import surviving_workers

    class Survivor(QObject):
        finished = Signal()
        running = True
        def requestInterruption(self): pass
        def isRunning(self): return self.running
        def wait(self, _timeout): return False
        def terminate(self): pass

    worker = Survivor()
    vm = CrawlViewModel(supplier_loader=lambda: [])
    vm._retired_workers = [worker]
    vm.shutdown()
    vm_ref = weakref.ref(vm)
    del vm
    gc.collect()

    assert worker in surviving_workers()
    assert vm_ref() is None
    worker.finished.emit()
    assert worker in surviving_workers()
    worker.running = False
    from PySide6.QtTest import QTest
    QTest.qWait(100)
    assert worker not in surviving_workers()


def test_legacy_main_window_has_been_removed() -> None:
    assert not (Path(__file__).parents[2] / "app" / "ui" / "main_window.py").exists()


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


def test_full_crawl_selects_all_categories_and_starts(monkeypatch) -> None:
    from app.ui_qml.viewmodels.crawl import CrawlViewModel

    monkeypatch.setattr("app.ui_qml.viewmodels.crawl.adapter_exists", lambda _: True)
    monkeypatch.setattr(
        "app.ui_qml.viewmodels.crawl.load_config",
        lambda: SimpleNamespace(global_delay_seconds=3),
    )
    made: list = []
    vm = CrawlViewModel(
        app_view_model=AppViewModel(), supplier_loader=lambda: [supplier()],
        worker_factories={"crawl": lambda request: made.append(FakeWorker(request)) or made[-1]},
    )
    vm.selectSupplier("s1")
    vm._set_categories([
        SimpleNamespace(category_id="c1", name="One", path="Root / One", children=[]),
        SimpleNamespace(category_id="c2", name="Two", path="Root / Two", children=[]),
    ])
    # 전체 수집: 카테고리 선택 없이도 전부 선택되어 수집이 시작된다
    assert vm.startFullCrawl() is True
    assert len(made) == 1
    assert {c[0] for c in made[0].request.categories} == {"c1", "c2"}


def test_full_crawl_requires_supplier() -> None:
    from app.ui_qml.viewmodels.crawl import CrawlViewModel

    vm = CrawlViewModel(app_view_model=AppViewModel(), supplier_loader=lambda: [])
    assert vm.startFullCrawl() is False
    assert vm.fieldErrors["supplier"] == "도매처를 선택하세요."


def test_refresh_auto_selects_first_supplier() -> None:
    from app.ui_qml.viewmodels.crawl import CrawlViewModel

    # 도매처가 있으면 첫 번째가 자동 선택되어 콤보에 보이는 것이 곧 선택된 것
    vm = CrawlViewModel(app_view_model=AppViewModel(), supplier_loader=lambda: [supplier()])
    assert vm.selectedSupplierId == "s1"

    # 빈 목록이면 선택 없음
    empty = CrawlViewModel(app_view_model=AppViewModel(), supplier_loader=lambda: [])
    assert empty.selectedSupplierId == ""


def test_crawl_combo_shows_supplier_added_after_screen_load(qt_app) -> None:
    """앱을 빈 상태로 켠 뒤 도매처를 추가하면, 수집 콤보에 즉시 나타나고 선택된다.
    (사용자 신고: 도매처를 등록했는데 수집에서 아무 도매처도 안 뜸)"""
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent

    from app.ui_qml.viewmodels.crawl import CrawlViewModel

    qml_dir = Path(__file__).parents[2] / "app" / "ui_qml" / "qml"
    box = {"items": []}  # 처음엔 도매처 없음
    vm = CrawlViewModel(
        app_view_model=AppViewModel(),
        supplier_loader=lambda: list(box["items"]),
    )

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(qml_dir))
    engine.rootContext().setContextProperty("TestCrawlVM", vm)
    component = QQmlComponent(engine)
    component.setData(
        b'import QtQuick\nimport QtQuick.Controls.Basic\nimport "screens" as Screens\n'
        b'ApplicationWindow { width: 900; height: 620; visible: true; '
        b'Screens.CrawlScreen { anchors.fill: parent; viewModel: TestCrawlVM } }',
        QUrl.fromLocalFile(str(qml_dir / "CrawlProbe.qml")),
    )
    window = component.create(engine.rootContext())
    assert not component.errors(), component.errorString()
    combo = window.findChild(QObject, "crawlSupplierCombo")
    assert combo is not None
    assert combo.property("count") == 0

    # 도매처 등록 후 새로고침(마법사 저장/화면 진입 시 일어나는 것과 동일)
    box["items"] = [supplier()]
    vm.refreshSuppliers()
    qt_app.processEvents()

    assert combo.property("count") == 1
    assert combo.property("currentIndex") == 0
    assert combo.property("currentText") == "Korean Shop"
    assert vm.selectedSupplierId == "s1"
