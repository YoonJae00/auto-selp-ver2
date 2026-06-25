from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
import re
from typing import Any

from PySide6.QtCore import Property, QTimer, QUrl, Signal, Slot
from PySide6.QtWidgets import QFileDialog
from sqlalchemy import select

from app.db.models import Product, Supplier
from app.db.session import get_session
from app.exporters.history import ExportHistoryStore
from app.exporters.validation import ExportScopeValidation, validate_export_scope
from app.paths import exports_dir as default_exports_dir
from app.ui_qml.models.list_model import ListModel
from app.ui_qml.viewmodels.base import BaseViewModel, sanitize_diagnostic
from app.workers.export import ExportRequest, ExportWorker
from app.workers.lifecycle import stop_workers


ISSUE_ROLES = ("severity", "code", "message", "productId", "productCode")


def _load_suppliers() -> list[Supplier]:
    session = get_session()
    try:
        return list(session.scalars(select(Supplier).order_by(Supplier.name)))
    finally:
        session.close()


class ExportViewModel(BaseViewModel):
    stateChanged = Signal()

    def __init__(self, parent=None, *, app_view_model=None,
                 supplier_loader: Callable[[], list[Any]] = _load_suppliers,
                 scope_loader: Callable[[str], Any] | None = None,
                 exports_dir: Path | None = None, picker: Callable[[str], Any] | None = None,
                 worker_factory: Callable[[ExportRequest], Any] | None = None,
                 session_factory: Callable[[], Any] = get_session,
                 history_store: ExportHistoryStore | None = None) -> None:
        super().__init__(parent)
        self._app = app_view_model
        self._scope_loader = scope_loader
        self._exports_dir = Path(exports_dir) if exports_dir is not None else default_exports_dir()
        self._picker = picker
        self._worker_factory = worker_factory
        self._session_factory = session_factory
        self._history_store = history_store or ExportHistoryStore(self._exports_dir / ".export_history.json")
        self._supplier_ids: set[str] = set()
        self._supplier_names: dict[str, str] = {}
        self._supplier_id = ""
        self._product_count = self._option_count = 0
        self._blocking_count = self._warning_count = 0
        self._validation_fingerprint = ""
        self._issues = ListModel(ISSUE_ROLES, parent=self)
        self._history = ListModel(("fileName", "path", "exportedAt", "rowCount", "outcome"), parent=self)
        self._suppliers = ListModel(("id", "name"), parent=self)
        self._warning_acknowledged = False
        self._selected_issue_detail: dict[str, Any] = {}
        self._validated = False
        self._output_path: Path | None = None
        self._busy = False
        self._worker = None
        self._retired_workers: list[Any] = []
        self._operation_id = 0
        self._task_owner: object | None = None
        self._attempt_id = ""
        self._shutting_down = False
        suppliers = supplier_loader()
        rows = [{"id": "", "name": "도매처 선택"}, *[{"id": str(item.id), "name": item.name} for item in suppliers]]
        self._supplier_ids = {row["id"] for row in rows if row["id"]}
        self._supplier_names = {row["id"]: row["name"] for row in rows if row["id"]}
        self._suppliers.resetRows(rows)
        self.refreshHistory()

    suppliers = Property(object, lambda self: self._suppliers, constant=True)
    issues = Property(object, lambda self: self._issues, constant=True)
    history = Property(object, lambda self: self._history, constant=True)
    selectedSupplierId = Property(str, lambda self: self._supplier_id, notify=stateChanged)
    selectedSupplierIndex = Property(int, lambda self: next((index for index, row in enumerate(self._suppliers._rows) if row["id"] == self._supplier_id), 0), notify=stateChanged)
    productCount = Property(int, lambda self: self._product_count, notify=stateChanged)
    optionCount = Property(int, lambda self: self._option_count, notify=stateChanged)
    warningAcknowledged = Property(bool, lambda self: self._warning_acknowledged, notify=stateChanged)
    busy = Property(bool, lambda self: self._busy, notify=stateChanged)
    destinationName = Property(str, lambda self: self._output_path.name if self._output_path else "", notify=stateChanged)
    selectedIssueDetail = Property("QVariantMap", lambda self: dict(self._selected_issue_detail), notify=stateChanged)

    @Property(bool, notify=stateChanged)
    def canExport(self) -> bool:
        retired_running = any(getattr(worker, "isRunning", lambda: False)() for worker in self._retired_workers)
        return bool(self._validated and self._supplier_id and self._output_path and not self._busy and not retired_running and not self._blocking_count and (not self._warning_count or self._warning_acknowledged))

    def _emit(self) -> None:
        self.stateChanged.emit()
        self.changed.emit()

    @Slot(str)
    def setSupplierId(self, supplier_id: str) -> None:
        value = supplier_id if supplier_id in self._supplier_ids else ""
        if value == self._supplier_id or self._busy:
            return
        self._supplier_id = value
        self._product_count = self._option_count = 0
        self._blocking_count = self._warning_count = 0
        self._validation_fingerprint = ""
        self._issues.resetRows([])
        self._warning_acknowledged = self._validated = False
        if self._selected_issue_detail and self._app:
            self._app.set_detail_panel_open(False)
        self._selected_issue_detail = {}
        self._output_path = None
        self._emit()

    @Slot(result=bool)
    def validateScope(self) -> bool:
        if not self._supplier_id:
            result = ExportScopeValidation(0, 0, 1, 0, "", [{"severity": "error", "code": "supplier_required", "message": "도매처를 선택하세요.", "productId": "", "productCode": ""}])
        else:
            try:
                result = self._load_validation()
            except Exception as exc:
                result = ExportScopeValidation(0, 0, 1, 0, "", [{"severity": "error", "code": "validation_failed", "message": sanitize_diagnostic(exc), "productId": "", "productCode": ""}])
            if result.product_count == 0 and not result.blocking_count and not any(issue["code"] == "validation_failed" for issue in result.issues):
                result.issues.insert(0, {"severity": "error", "code": "empty_scope", "message": "내보낼 상품이 없습니다.", "productId": "", "productCode": ""})
                result = ExportScopeValidation(result.product_count, result.option_count, result.blocking_count + 1, result.warning_count, result.fingerprint, result.issues)
        self._product_count, self._option_count = result.product_count, result.option_count
        self._blocking_count, self._warning_count = result.blocking_count, result.warning_count
        self._validation_fingerprint = result.fingerprint
        issues = result.issues
        issues.sort(key=lambda row: row.get("severity") != "error")
        self._issues.resetRows(issues)
        self._warning_acknowledged = False
        self._validated = True
        if self._supplier_id and self._output_path is None:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            supplier_name = re.sub(r"[^\w.-]+", "_", self._supplier_names.get(self._supplier_id, self._supplier_id)).strip("._") or "supplier"
            self._output_path = self._exports_dir / f"{supplier_name}_{stamp}.xlsx"
        self._emit()
        return not self._blocking_count

    def _load_validation(self) -> ExportScopeValidation:
        if self._scope_loader is not None:
            loaded = self._scope_loader(self._supplier_id)
            if isinstance(loaded, ExportScopeValidation):
                return loaded
            product_count, option_count, issues = loaded
            blocking = sum(row.get("severity") == "error" for row in issues)
            warnings = sum(row.get("severity") == "warning" for row in issues)
            fingerprint = repr((product_count, option_count, [(row.get("severity"), row.get("code"), row.get("productId")) for row in issues]))
            return ExportScopeValidation(product_count, option_count, blocking, warnings, fingerprint, list(issues))
        session = self._session_factory()
        try:
            return validate_export_scope(session, self._supplier_id)
        finally:
            session.close()

    @Slot(bool)
    def acknowledgeWarnings(self, acknowledged: bool = True) -> None:
        self._warning_acknowledged = bool(acknowledged)
        self._emit()

    @Slot(str)
    def setOutputPath(self, path: str) -> None:
        candidate = Path(path).expanduser()
        if candidate.suffix.lower() != ".xlsx":
            candidate = candidate.with_suffix(".xlsx")
        self._output_path = candidate
        self._emit()

    @Slot()
    def chooseOutputFile(self) -> None:
        initial = str(self._output_path or self._exports_dir / "export.xlsx")
        if self._picker:
            try:
                selected = self._picker(initial)
            except TypeError:
                selected = self._picker()
        else:
            selected = QFileDialog.getSaveFileUrl(None, "Excel 내보내기", QUrl.fromLocalFile(initial), "Excel (*.xlsx)")[0]
        if isinstance(selected, tuple):
            selected = selected[0]
        path = selected.toLocalFile() if isinstance(selected, QUrl) else str(selected or "")
        if path:
            self.setOutputPath(path)

    @Slot(result=bool)
    def export(self) -> bool:
        if not self.canExport or self._shutting_down or self._worker is not None:
            return False
        previous_fingerprint = self._validation_fingerprint
        acknowledged = self._warning_acknowledged
        try:
            fresh = self._load_validation()
        except Exception as exc:
            self.set_field_errors({"form": sanitize_diagnostic(exc)})
            return False
        if fresh.fingerprint != previous_fingerprint:
            self._product_count, self._option_count = fresh.product_count, fresh.option_count
            self._blocking_count, self._warning_count = fresh.blocking_count, fresh.warning_count
            self._issues.resetRows(fresh.issues)
            self._validation_fingerprint = fresh.fingerprint
            self._warning_acknowledged = False
            self.set_field_errors({"form": "내보내기 범위가 변경되었습니다. 다시 검토해 주세요."})
            self._emit()
            return False
        self._warning_acknowledged = acknowledged
        request = ExportRequest(self._supplier_id, self._output_path)
        self._attempt_id = self._history_store.begin(
            self._supplier_id, self._supplier_names.get(self._supplier_id, self._supplier_id), self._output_path
        )
        try:
            worker = self._worker_factory(request) if self._worker_factory else ExportWorker(request, session_factory=self._session_factory)
        except Exception as exc:
            safe = sanitize_diagnostic(exc)
            self._history_store.finish(self._attempt_id, "failed", error=safe)
            self.set_field_errors({"form": safe})
            self._emit()
            return False
        owner = object()
        if self._app and not self._app.acquire_task("export", "Excel 내보내기", owner):
            self._history_store.finish(self._attempt_id, "failed", error="다른 작업이 실행 중입니다.")
            self.set_field_errors({"form": "다른 작업이 종료될 때까지 기다려 주세요."})
            return False
        self._operation_id += 1
        operation = self._operation_id
        self._task_owner = owner
        self._worker = worker
        self._busy = True
        try:
            worker.complete.connect(lambda path: self._on_complete(operation, path))
            worker.error.connect(lambda message: self._on_error(operation, message))
            worker.cancelled.connect(lambda: self._on_cancelled(operation))
            self._emit()
            worker.start()
        except Exception as exc:
            safe = sanitize_diagnostic(exc)
            failed_owner = self._task_owner
            self._busy = False
            self._worker = None
            self._retired_workers.extend(stop_workers([worker], timeout_ms=100))
            if self._app and failed_owner is not None:
                self._app.fail_owned_task(failed_owner, safe)
            self._history_store.finish(self._attempt_id, "failed", error=safe)
            self._task_owner = None
            self.set_field_errors({"form": safe})
            self._emit()
            return False
        return True

    def _current(self, operation: int) -> bool:
        return operation == self._operation_id and not self._shutting_down

    def _retire(self) -> None:
        if self._worker is not None:
            self._retired_workers.append(self._worker)
            self._worker = None
        self._retired_workers = [w for w in self._retired_workers if getattr(w, "isRunning", lambda: False)()]
        if self._retired_workers:
            QTimer.singleShot(25, self._cleanup_retired)

    def _cleanup_retired(self) -> None:
        self._retired_workers = [w for w in self._retired_workers if getattr(w, "isRunning", lambda: False)()]
        if self._retired_workers:
            QTimer.singleShot(25, self._cleanup_retired)
        self._emit()

    def _on_complete(self, operation: int, _path: str) -> None:
        if not self._current(operation): return
        self._busy = False
        self._retire()
        if self._app and self._task_owner is not None: self._app.complete_owned_task(self._task_owner)
        self._history_store.finish(self._attempt_id, "success", row_count=self._product_count)
        self._task_owner = None
        self.refreshHistory()
        self.validateScope()

    def _on_error(self, operation: int, message: str) -> None:
        if not self._current(operation): return
        self._busy = False
        self._retire()
        safe = sanitize_diagnostic(message)
        self._history_store.finish(self._attempt_id, "failed", error=safe)
        self.set_field_errors({"form": safe})
        if self._app and self._task_owner is not None: self._app.fail_owned_task(self._task_owner, safe)
        self._task_owner = None
        self._emit()

    def _on_cancelled(self, operation: int) -> None:
        if not self._current(operation): return
        self._busy = False
        self._retire()
        self._history_store.finish(self._attempt_id, "cancelled")
        if self._app and self._task_owner is not None: self._app.cancel_owned_task(self._task_owner)
        self._task_owner = None
        self._emit()

    @Slot()
    def refreshHistory(self) -> None:
        rows = self._history_store.latest()
        self._history.resetRows(rows)
        self._emit()

    @Slot(int)
    @Slot(str)
    @Slot(str, str)
    def selectIssue(self, issue_id: int | str, product_code: str = "") -> None:
        issue = None
        if isinstance(issue_id, int):
            if 0 <= issue_id < len(self._issues._rows):
                issue = self._issues._rows[issue_id]
        else:
            issue = next((row for row in self._issues._rows if row.get("productId") == issue_id and (not product_code or row.get("productCode") == product_code)), None)
        product_id = str(issue.get("productId", "")) if issue else ""
        if not product_id:
            return
        session = self._session_factory()
        try:
            product = session.get(Product, product_id)
        finally:
            session.close()
        if product is None:
            return
        self._selected_issue_detail = {
            "productId": str(product.id),
            "code": product.supplier_product_code or "",
            "name": product.raw_product_name or "",
            "supplier": product.supplier_name or "",
            "status": product.supplier_status or "",
            "price": product.supply_price if product.supply_price is not None else 0,
            "message": issue.get("message", ""),
            "severity": issue.get("severity", ""),
        }
        if self._app:
            self._app.set_detail_panel_open(True)
        self._emit()

    @Slot()
    def shutdown(self) -> None:
        if self._shutting_down: return
        self._shutting_down = True
        self._operation_id += 1
        if self._app and self._task_owner is not None:
            self._app.cancel_owned_task(self._task_owner, "내보내기 종료됨")
        workers = list(self._retired_workers)
        if self._worker is not None:
            workers.append(self._worker)
            self._worker = None
        self._retired_workers = stop_workers(workers)
        self._busy = False
        self._task_owner = None
        self._emit()
