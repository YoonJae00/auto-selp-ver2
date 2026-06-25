from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from PySide6.QtCore import QMetaObject, QObject, Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtTest import QTest

from app.db.models import Base, CrawlRun, Product, StockChange, Supplier
from app.ui_qml.application import QML_DIRECTORY
from app.ui_qml.viewmodels.app import AppViewModel
from app.ui_qml.viewmodels.monitor import MonitorViewModel


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _rows(model):
    roles = {role: name.data().decode() if hasattr(name, "data") else bytes(name).decode()
             for role, name in model.roleNames().items()}
    return [
        {name: model.data(model.index(row, 0), role) for role, name in roles.items()}
        for row in range(model.rowCount())
    ]


@pytest.fixture
def seeded(session_factory):
    with session_factory() as session:
        alpha = Supplier(id="s1", name="Alpha", base_url="https://alpha.test", monitor_enabled=True, monitor_interval_hours=6)
        beta = Supplier(id="s2", name="Beta", base_url="https://beta.test", monitor_enabled=False)
        p1 = Product(id="p1", supplier_id="s1", supplier_name="Alpha", supplier_product_code="A-1", supplier_status="판매중", raw_product_name="Alpha coat")
        p2 = Product(id="p2", supplier_id="s2", supplier_name="Beta", supplier_product_code="B-1", supplier_status="품절", raw_product_name="Beta bag")
        session.add_all([alpha, beta, p1, p2])
        session.add_all([
            StockChange(id="c1", product_id="p1", change_type="sold_out", previous_value="판매중", new_value="품절", detected_at=datetime(2026, 6, 24, 1, 2, tzinfo=timezone.utc)),
            StockChange(id="c2", product_id="p1", change_type="price_changed", previous_value="1000", new_value="1200", detected_at=datetime(2026, 6, 24, 2, 2), acknowledged=True),
            StockChange(id="c3", product_id="p2", change_type="restocked", previous_value="품절", new_value="판매중", detected_at=datetime(2026, 6, 24, 3, 2)),
            StockChange(id="c4", product_id="p2", change_type="stock_changed", previous_value="2", new_value="1", detected_at=datetime(2026, 6, 24, 4, 2)),
            CrawlRun(id="r1", supplier_id="s1", run_type="stock_check", status="success", started_at=datetime(2026, 6, 24, 4), finished_at=datetime(2026, 6, 24, 5)),
            CrawlRun(id="r2", supplier_id="s1", run_type="stock_check", status="failed", started_at=datetime(2026, 6, 24, 6), finished_at=datetime(2026, 6, 24, 7), error="network failed"),
            CrawlRun(id="r3", supplier_id="s2", run_type="stock_check", status="failed", started_at=datetime(2026, 6, 24, 8), error="timeout"),
        ])
        session.commit()
    return session_factory


def test_rows_metrics_filters_and_iso_timestamps_are_filtered(seeded) -> None:
    vm = MonitorViewModel(session_factory=seeded)
    rows = _rows(vm.events)
    assert {row["id"] for row in rows} == {"c1", "c2", "c3", "c4"}
    assert rows[0]["detectedAt"].endswith("+00:00")
    assert vm.metrics == {"unread": 3, "soldOut": 1, "restocked": 1, "priceChanged": 1, "failedSchedules": 2}
    assert [row["id"] for row in _rows(vm.suppliers)] == ["", "s1", "s2"]

    vm.setSupplierFilter("s1")
    assert {row["id"] for row in _rows(vm.events)} == {"c1", "c2"}
    assert vm.metrics == {"unread": 1, "soldOut": 1, "restocked": 0, "priceChanged": 1, "failedSchedules": 1}
    vm.setChangeType("price_changed")
    assert [row["id"] for row in _rows(vm.events)] == ["c2"]
    assert vm.metrics["unread"] == 0
    assert vm.metrics["failedSchedules"] == 1
    vm.setChangeType("invalid")
    assert vm.changeType == "price_changed"
    vm.refresh()
    assert vm.supplierFilter == "s1" and vm.changeType == "price_changed"


def test_acknowledge_selected_and_all_only_affect_filtered_rows(seeded) -> None:
    vm = MonitorViewModel(session_factory=seeded)
    vm.selectChange("c1")
    vm.acknowledgeSelected()
    assert vm.metrics["unread"] == 2
    vm.setSupplierFilter("s2")
    vm.acknowledgeAll()
    assert vm.metrics["unread"] == 0
    with seeded() as session:
        assert session.get(StockChange, "c1").acknowledged is True
        assert session.get(StockChange, "c3").acknowledged is True
        assert session.get(StockChange, "c4").acknowledged is True


def test_schedule_uses_latest_stock_check_and_calculates_next(seeded) -> None:
    vm = MonitorViewModel(session_factory=seeded)
    vm.setSupplierFilter("s1")
    schedule = vm.selectedSupplierSchedule
    assert schedule["monitorEnabled"] is True
    assert schedule["intervalHours"] == 6
    assert schedule["lastCheckAt"].endswith("+00:00")
    assert schedule["nextCheckAt"] == "2026-06-24T13:00:00+00:00"
    assert schedule["nextCheckEstimated"] is True
    assert schedule["latestFailure"] == "network failed"


def test_injected_scheduler_state_overrides_estimate_after_restart(seeded) -> None:
    actual_next_run = datetime(2026, 6, 24, 9, 30, tzinfo=timezone.utc)
    vm = MonitorViewModel(
        session_factory=seeded,
        schedule_loader=lambda supplier_id: {
            "supplier_id": supplier_id,
            "next_run": actual_next_run,
        },
    )
    vm.setSupplierFilter("s1")

    assert vm.selectedSupplierSchedule["nextCheckAt"] == actual_next_run.isoformat()
    assert vm.selectedSupplierSchedule["nextCheckEstimated"] is False
    assert vm.selectedSupplierSchedule["nextCheckAt"] != "2026-06-24T13:00:00+00:00"


def test_filtering_out_selection_clears_stale_schedule(seeded) -> None:
    vm = MonitorViewModel(session_factory=seeded)
    vm.selectChange("c1")
    assert vm.selectedSupplierSchedule["supplierId"] == "s1"

    vm.setChangeType("restocked")

    assert vm.selectedChangeId == ""
    assert vm.selectedSupplierSchedule == {}


def test_schedule_detail_queries_only_latest_rows(seeded) -> None:
    statements: list[str] = []

    class TrackingSession:
        def __init__(self): self.inner = seeded()
        def __enter__(self): return self
        def __exit__(self, *_): self.inner.close()
        def execute(self, statement, *args):
            statements.append(str(statement))
            return self.inner.execute(statement, *args)
        def scalar(self, *args): return self.inner.scalar(*args)
        def get(self, *args): return self.inner.get(*args)

    vm = MonitorViewModel(session_factory=TrackingSession)
    statements.clear()
    vm.setSupplierFilter("s1")
    history_queries = [
        sql for sql in statements
        if "FROM crawl_runs" in sql and "count(" not in sql.lower()
    ]
    assert len(history_queries) == 2
    assert all("LIMIT" in sql for sql in history_queries)


def test_monitor_table_enter_and_space_select_and_open_detail(qt_app, seeded) -> None:
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(QML_DIRECTORY))
    vm = MonitorViewModel(session_factory=seeded)
    app_vm = AppViewModel()
    engine.rootContext().setContextProperty("TestMonitorVM", vm)
    engine.rootContext().setContextProperty("TestAppVM", app_vm)
    component = QQmlComponent(engine)
    component.setData(
        b'import QtQuick\nimport QtQuick.Controls.Basic\nimport "screens" as Screens\n'
        b'ApplicationWindow { width: 900; height: 620; visible: true; '
        b'Screens.MonitorScreen { anchors.fill: parent; viewModel: TestMonitorVM; appViewModel: TestAppVM } }',
        QUrl.fromLocalFile(str(QML_DIRECTORY / "MonitorKeyboardProbe.qml")),
    )
    window = component.create(engine.rootContext())
    view = window.findChild(QObject, "dataTableView") if window else None

    assert not component.errors()
    assert window is not None and view is not None
    QTest.qWaitForWindowExposed(window)
    window.requestActivate()
    QTest.qWaitForWindowActive(window)
    view.setProperty("currentIndex", 0)
    view.setProperty("focus", True)
    assert QMetaObject.invokeMethod(view, "forceActiveFocus") is True
    QTest.keyClick(window, Qt.Key_Return)
    qt_app.processEvents()
    assert vm.selectedChangeId == _rows(vm.events)[0]["id"]
    assert app_vm.detailPanelOpen is True

    vm.setChangeType("sold_out")
    qt_app.processEvents()
    assert vm.selectedChangeId == ""
    assert app_vm.detailPanelOpen is False

    vm.setChangeType("")
    view.setProperty("currentIndex", 1)
    QTest.keyClick(window, Qt.Key_Space)
    qt_app.processEvents()
    assert vm.selectedChangeId == _rows(vm.events)[1]["id"]
    assert app_vm.detailPanelOpen is True


def test_acknowledge_rolls_back_and_sanitizes_form_error(seeded) -> None:
    class BrokenSession:
        def __init__(self):
            self.inner = seeded()
            self.rolled_back = False
        def __enter__(self): return self
        def __exit__(self, *_): self.inner.close()
        def execute(self, *args): return self.inner.execute(*args)
        def scalar(self, *args): return self.inner.scalar(*args)
        def get(self, *args): return self.inner.get(*args)
        def commit(self): raise RuntimeError("db-secret-token")
        def rollback(self): self.rolled_back = True; self.inner.rollback()

    broken = BrokenSession()
    vm = MonitorViewModel(session_factory=lambda: broken)
    vm.selectChange("c1")
    vm.acknowledgeSelected()
    assert broken.rolled_back is True
    assert vm.fieldErrors["form"] == "변경 사항을 읽음 처리하지 못했습니다."
    assert "secret" not in repr(vm.fieldErrors)
