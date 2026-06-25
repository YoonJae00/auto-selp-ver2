from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QObject, QUrl, Signal

from app.exporters.history import ExportHistoryStore
from app.ui_qml.viewmodels.app import AppViewModel
from app.ui_qml.viewmodels.export import ExportViewModel
from app.workers.export import ExportRequest, ExportWorker


def _rows(model):
    return list(model._rows)


def test_empty_supplier_scope_blocks_export_and_error_is_first(tmp_path):
    vm = ExportViewModel(
        supplier_loader=lambda: [SimpleNamespace(id="s1", name="One")],
        scope_loader=lambda supplier_id: (0, 0, []),
        exports_dir=tmp_path,
    )
    vm.setSupplierId("s1")

    assert vm.validateScope() is False
    assert _rows(vm.issues)[0]["severity"] == "error"
    assert vm.canExport is False


def test_warnings_require_acknowledgement_and_scope_change_clears_validation(tmp_path):
    warning = {"severity": "warning", "code": "missing_origin", "message": "원산지 누락", "productId": "p1", "productCode": "P1"}
    vm = ExportViewModel(
        supplier_loader=lambda: [SimpleNamespace(id="s1", name="One"), SimpleNamespace(id="s2", name="Two")],
        scope_loader=lambda supplier_id: (1, 2, [warning]),
        exports_dir=tmp_path,
    )
    vm.setSupplierId("s1")
    assert vm.validateScope() is True
    assert vm.canExport is False
    vm.acknowledgeWarnings(True)
    assert vm.canExport is True
    vm.setSupplierId("s2")
    assert _rows(vm.issues) == []
    assert vm.warningAcknowledged is False
    assert vm.canExport is False


def test_output_path_is_private_and_extension_is_enforced(tmp_path):
    vm = ExportViewModel(supplier_loader=lambda: [], exports_dir=tmp_path)
    vm.setOutputPath(str(tmp_path / "report"))
    assert not hasattr(vm, "outputPath")
    assert vm._output_path == tmp_path / "report.xlsx"


def test_dialog_selected_file_suggests_default_and_validated_export_name(tmp_path):
    vm = ExportViewModel(
        supplier_loader=lambda: [SimpleNamespace(id="s1", name="One Supplier")],
        scope_loader=lambda supplier_id: (1, 0, []),
        exports_dir=tmp_path,
    )

    assert isinstance(vm.dialogSelectedFile, QUrl)
    assert vm.dialogSelectedFile.toLocalFile() == str(tmp_path / "export.xlsx")

    vm.setSupplierId("s1")
    assert vm.validateScope() is True

    suggested = Path(vm.dialogSelectedFile.toLocalFile())
    assert suggested.parent == tmp_path
    assert suggested.name.startswith("One_Supplier_")
    assert suggested.suffix == ".xlsx"


def test_history_is_newest_first_and_corrupt_is_safe(tmp_path):
    store = ExportHistoryStore(tmp_path / "history.json")
    old = store.begin("s1", "One", tmp_path / "old.xlsx")
    store.finish(old, "success", row_count=1)
    new = store.begin("s1", "One", tmp_path / "new.xlsx")
    store.finish(new, "failed", error="broken")
    vm = ExportViewModel(supplier_loader=lambda: [], exports_dir=tmp_path, history_store=store)
    rows = _rows(vm.history)
    assert [row["fileName"] for row in rows] == ["new.xlsx", "old.xlsx"]
    assert rows[0]["outcome"] == "failed"
    assert rows[1]["rowCount"] == 1


def test_worker_uses_atomic_replace_and_typed_request(tmp_path):
    final = tmp_path / "result.xlsx"
    request = ExportRequest("s1", final)
    seen = []

    def exporter(session, supplier_id, path):
        seen.append((supplier_id, path))
        path.write_bytes(b"complete")

    worker = ExportWorker(
        request, session_factory=lambda: SimpleNamespace(close=lambda: None), exporter=exporter,
        validator=lambda session, supplier_id: SimpleNamespace(blocking_count=0),
    )
    worker.run()
    assert final.read_bytes() == b"complete"
    assert seen[0][0] == "s1"
    assert seen[0][1] != final
    assert not seen[0][1].exists()


def test_select_issue_loads_product_and_opens_shared_detail_panel(tmp_path):
    app = AppViewModel()
    product = SimpleNamespace(
        id="p1", supplier_product_code="P-1", raw_product_name="Product",
        supplier_name="Supplier", supplier_status="available", supply_price=1200,
    )
    session = SimpleNamespace(get=lambda model, product_id: product if product_id == "p1" else None, close=lambda: None)
    issue = {"severity": "warning", "code": "missing_origin", "message": "원산지 누락", "productId": "p1", "productCode": "P-1"}
    vm = ExportViewModel(
        app_view_model=app,
        supplier_loader=lambda: [SimpleNamespace(id="s1", name="One")],
        scope_loader=lambda supplier_id: (1, 0, [issue]),
        session_factory=lambda: session,
        exports_dir=tmp_path,
    )
    vm.setSupplierId("s1")
    vm.validateScope()

    vm.selectIssue("p1", "P-1")

    assert vm.selectedIssueDetail == {
        "productId": "p1", "code": "P-1", "name": "Product", "supplier": "Supplier",
        "status": "available", "price": 1200, "message": "원산지 누락", "severity": "warning",
    }
    assert app.detailPanelOpen is True
    assert app.currentRoute == "suppliers"


def test_select_issue_rejects_unknown_and_summary_rows(tmp_path):
    app = AppViewModel()
    vm = ExportViewModel(
        app_view_model=app,
        supplier_loader=lambda: [SimpleNamespace(id="s1", name="One")],
        scope_loader=lambda supplier_id: (1, 0, [{"severity": "warning", "code": "more_issues", "message": "more", "productId": "", "productCode": ""}]),
        session_factory=lambda: (_ for _ in ()).throw(AssertionError("must not query")),
        exports_dir=tmp_path,
    )
    vm.setSupplierId("s1")
    vm.validateScope()

    vm.selectIssue("", "")
    vm.selectIssue("not-an-issue", "")

    assert vm.selectedIssueDetail == {}
    assert app.detailPanelOpen is False


class _WorkerSignals(QObject):
    complete = Signal(str)
    error = Signal(str)
    cancelled = Signal()

    def __init__(self, *, start_error=None):
        super().__init__()
        self.start_error = start_error

    def start(self):
        if self.start_error:
            raise self.start_error

    def isRunning(self):
        return False


def _ready_vm(tmp_path, app, factory):
    vm = ExportViewModel(
        app_view_model=app,
        supplier_loader=lambda: [SimpleNamespace(id="s1", name="One")],
        scope_loader=lambda supplier_id: (1, 0, []),
        worker_factory=factory,
        exports_dir=tmp_path,
    )
    vm.setSupplierId("s1")
    vm.validateScope()
    return vm


def test_worker_factory_exception_does_not_acquire_or_strand_task(tmp_path):
    app = AppViewModel()
    vm = _ready_vm(tmp_path, app, lambda request: (_ for _ in ()).throw(RuntimeError("token=secret")))

    assert vm.export() is False
    assert vm.busy is False
    assert app.activeTask.state == "idle"
    assert "secret" not in vm.fieldErrors["form"]


def test_worker_start_exception_fails_owned_task_and_allows_retry(tmp_path):
    app = AppViewModel()
    workers = [_WorkerSignals(start_error=RuntimeError("start failed password=hunter2")), _WorkerSignals()]
    vm = _ready_vm(tmp_path, app, lambda request: workers.pop(0))

    assert vm.export() is False
    assert vm.busy is False
    assert vm._worker is None
    assert vm._task_owner is None
    assert app.activeTask.state == "failed"
    assert "hunter2" not in app.activeTask.errorMessage
    assert vm.export() is True
    assert vm.busy is True


def test_worker_signal_connection_exception_rolls_back_and_allows_retry(tmp_path):
    class BrokenSignal:
        def connect(self, callback):
            raise RuntimeError("connect failed token=secret")

    broken = _WorkerSignals()
    broken.complete = BrokenSignal()
    workers = [broken, _WorkerSignals()]
    app = AppViewModel()
    vm = _ready_vm(tmp_path, app, lambda request: workers.pop(0))

    assert vm.export() is False
    assert vm.busy is False
    assert vm._worker is None and vm._task_owner is None
    assert app.activeTask.state == "failed"
    assert "secret" not in app.activeTask.errorMessage
    assert vm.export() is True


def test_view_model_persists_custom_destination_success_failure_and_cancel(tmp_path):
    app = AppViewModel()
    workers = [_WorkerSignals(), _WorkerSignals(), _WorkerSignals()]
    vm = _ready_vm(tmp_path, app, lambda request: workers.pop(0))
    custom = tmp_path / "custom" / "report.xlsx"
    vm.setOutputPath(str(custom))

    first = workers[0]
    assert vm.export() is True
    first.complete.emit(str(custom))
    assert _rows(vm.history)[0]["path"] == str(custom)
    assert _rows(vm.history)[0]["outcome"] == "success"

    second = workers[0]
    assert vm.export() is True
    second.error.emit("password=hunter2")
    vm.refreshHistory()
    assert _rows(vm.history)[0]["outcome"] == "failed"
    assert "hunter2" not in _rows(vm.history)[0]["error"]

    third = workers[0]
    assert vm.export() is True
    third.cancelled.emit()
    vm.refreshHistory()
    assert _rows(vm.history)[0]["outcome"] == "cancelled"
