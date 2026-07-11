from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Property, QElapsedTimer, QTimer, Signal, Slot

from app.config import load_config
from app.crawlers.registry import adapter_exists
from app.db.models import Supplier
from app.db.session import get_session
from app.ui_qml.models.list_model import ListModel
from app.ui_qml.viewmodels.base import BaseViewModel, sanitize_diagnostic
from app.workers.crawl import (
    CategoryDiscoveryRequest,
    CategoryDiscoveryWorker,
    CrawlRequest,
    CrawlWorker,
    StockCheckWorker,
)
from app.workers.lifecycle import stop_workers


def _load_suppliers() -> list[Supplier]:
    session = get_session()
    try:
        return list(session.query(Supplier).order_by(Supplier.name).all())
    finally:
        session.close()


class CrawlViewModel(BaseViewModel):
    stateChanged = Signal()

    def __init__(
        self,
        parent=None,
        *,
        app_view_model=None,
        supplier_loader: Callable[[], list[Any]] = _load_suppliers,
        worker_factories: dict[str, Callable[[Any], Any]] | None = None,
        adapter_checker: Callable[[str], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self._app = app_view_model
        self._supplier_loader = supplier_loader
        self._adapter_checker = adapter_checker or adapter_exists
        self._factories = {
            "crawl": CrawlWorker,
            "discovery": CategoryDiscoveryWorker,
            "stock": StockCheckWorker,
            **(worker_factories or {}),
        }
        self._supplier_objects: dict[str, Any] = {}
        self._supplier_rows: list[dict[str, Any]] = []
        self._suppliers = ListModel(("id", "name", "adapterFile", "adapterReady"), parent=self)
        self._categories = ListModel(("id", "name", "path", "parentId", "depth", "selected", "hasChildren", "url"), parent=self)
        self._results = ListModel(("name", "code", "optionCount"), parent=self)
        self._category_rows: list[dict[str, Any]] = []
        self._descendants: dict[str, set[str]] = {}
        self._selected: set[str] = set()
        self._supplier_id = ""
        self._max_pages = 50
        self._delay_seconds = -1
        self._product_count = 0
        self._option_count = 0
        self._current_target = ""
        self._busy = False
        self._discovering = False
        self._pending_full_crawl = False
        self._worker = None
        self._retired_workers: list[Any] = []
        self._operation_id = 0
        self._task_owner: object | None = None
        self._cancelled_operations: set[int] = set()
        self._shutting_down = False
        self._elapsed = QElapsedTimer()
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._emit)
        self.refreshSuppliers()

    suppliers = Property(object, lambda self: self._suppliers, constant=True)
    # ComboBox는 QAbstractListModel의 in-place 리셋(beginResetModel)을 안정적으로
    # 반영하지 못해 목록이 안 바뀐다. 정체성이 바뀌면 통째로 재구성되는
    # QVariantList로 콤보를 구동한다.
    supplierList = Property("QVariantList", lambda self: list(self._supplier_rows), notify=stateChanged)
    categories = Property(object, lambda self: self._categories, constant=True)
    results = Property(object, lambda self: self._results, constant=True)
    selectedSupplierId = Property(str, lambda self: self._supplier_id, notify=stateChanged)
    selectedCategoryIds = Property("QStringList", lambda self: sorted(self._selected), notify=stateChanged)
    maxPages = Property(int, lambda self: self._max_pages, notify=stateChanged)
    delaySeconds = Property(int, lambda self: self._delay_seconds, notify=stateChanged)
    productCount = Property(int, lambda self: self._product_count, notify=stateChanged)
    optionCount = Property(int, lambda self: self._option_count, notify=stateChanged)
    currentTarget = Property(str, lambda self: self._current_target, notify=stateChanged)
    elapsedSeconds = Property(int, lambda self: self._elapsed.elapsed() // 1000 if self._elapsed.isValid() else 0, notify=stateChanged)
    busy = Property(bool, lambda self: self._busy, notify=stateChanged)
    discovering = Property(bool, lambda self: self._discovering, notify=stateChanged)

    def _emit(self) -> None:
        self.stateChanged.emit()
        self.changed.emit()

    @Slot()
    def refreshSuppliers(self) -> None:
        suppliers = self._supplier_loader()
        self._supplier_objects = {str(item.id): item for item in suppliers}
        self._supplier_rows = [
            {
                "id": str(item.id), "name": item.name,
                "adapterFile": item.adapter_file or "",
                "adapterReady": bool(item.adapter_file and self._adapter_checker(item.adapter_file)),
            }
            for item in suppliers
        ]
        self._suppliers.resetRows(self._supplier_rows)
        if self._supplier_id not in self._supplier_objects:
            self._supplier_id = ""
        # 도매처가 하나라도 있으면 첫 번째를 자동 선택 — 콤보에 보이는 도매처가
        # 곧 선택된 도매처가 되도록 (전체 수집 90% 경로에서 클릭 한 번 절약).
        if not self._supplier_id and suppliers:
            self._supplier_id = str(suppliers[0].id)
        self._emit()

    @Slot(str)
    def selectSupplier(self, supplier_id: str) -> None:
        if self._busy or supplier_id == self._supplier_id:
            return
        self._supplier_id = supplier_id if supplier_id in self._supplier_objects else ""
        self._set_categories([])
        self.set_field_errors({})
        self._emit()

    @Slot(int)
    def setMaxPages(self, value: int) -> None:
        if not self._busy:
            self._max_pages = int(value)
            self._emit()

    @Slot(int)
    def setDelaySeconds(self, value: int) -> None:
        if not self._busy:
            self._delay_seconds = int(value)
            self._emit()

    def _selected_supplier(self):
        return self._supplier_objects.get(self._supplier_id)

    def _validate_supplier(self) -> dict[str, str]:
        supplier = self._selected_supplier()
        if supplier is None:
            return {"supplier": "도매처를 선택하세요."}
        if not supplier.adapter_file or not self._adapter_checker(supplier.adapter_file):
            return {"supplier": "사용 가능한 어댑터가 필요합니다."}
        return {}

    @Slot(result=bool)
    def discoverCategories(self) -> bool:
        if not self._can_start("crawl-discovery"):
            self.set_field_errors({"form": "다른 작업이 종료될 때까지 기다려 주세요."})
            return False
        errors = self._validate_supplier()
        if errors:
            self.set_field_errors(errors)
            return False
        supplier = self._selected_supplier()
        request = CategoryDiscoveryRequest(
            supplier.name, supplier.adapter_file, supplier.credential_key,
        )
        worker = self._factories["discovery"](request)
        return self._start_worker(worker, "discovery")

    def _set_categories(self, categories: list[Any]) -> None:
        rows: list[dict[str, Any]] = []
        descendants: dict[str, set[str]] = {}

        def visit(node, parent_id: str, depth: int) -> set[str]:
            node_id = str(node.category_id)
            child_ids: set[str] = set()
            children = list(getattr(node, "children", []) or [])
            rows.append({
                "id": node_id, "name": node.name, "path": node.path,
                "parentId": parent_id, "depth": depth, "selected": False,
                "hasChildren": bool(children),
                "url": getattr(node, "url", "") or "",
            })
            for child in children:
                child_ids |= visit(child, node_id, depth + 1)
            descendants[node_id] = child_ids
            return {node_id, *child_ids}

        for category in categories:
            visit(category, "", 0)
        self._category_rows = rows
        self._descendants = descendants
        self._selected.clear()
        self._categories.resetRows(rows)
        self._emit()

    @Slot(str, bool)
    def toggleCategory(self, category_id: str, checked: bool) -> None:
        affected = {category_id, *self._descendants.get(category_id, set())}
        if checked:
            self._selected.update(affected)
        else:
            self._selected.difference_update(affected)
        valid = {row["id"] for row in self._category_rows}
        self._selected.intersection_update(valid)
        self._refresh_category_rows()

    def _refresh_category_rows(self) -> None:
        rows = [{**row, "selected": row["id"] in self._selected} for row in self._category_rows]
        self._category_rows = rows
        self._categories.resetRows(rows)
        self._emit()

    @Slot()
    def selectAll(self) -> None:
        self._selected = {row["id"] for row in self._category_rows}
        self._refresh_category_rows()

    @Slot()
    def clearSelection(self) -> None:
        self._selected.clear()
        self._refresh_category_rows()

    @Slot()
    def clear(self) -> None:
        self.clearSelection()

    @Slot(result=bool)
    def startFullCrawl(self) -> bool:
        """전체 수집 (기본 경로) — 도매처의 모든 카테고리를 수집한다. 카테고리를
        아직 안 불러왔으면 먼저 탐색한 뒤 자동으로 전체 선택하고 수집을 시작한다."""
        if not self._can_start("crawl-crawl"):
            self.set_field_errors({"form": "다른 작업이 종료될 때까지 기다려 주세요."})
            return False
        errors = self._validate_supplier()
        if errors:
            self.set_field_errors(errors)
            return False
        self.set_field_errors({})
        if self._category_rows:
            self.selectAll()
            return self.startCrawl()
        # 카테고리 미탐색 → 탐색 후 _on_discovered에서 전체 수집으로 이어감
        self._pending_full_crawl = True
        if not self.discoverCategories():
            self._pending_full_crawl = False
            return False
        return True

    def _start_pending_full_crawl(self) -> None:
        if not self._category_rows:
            self.set_field_errors(
                {"supplier": "이 도매처에서 수집할 카테고리를 찾지 못했습니다. 도매처 화면에서 다시 분석하세요."}
            )
            return
        if not self._can_start("crawl-crawl"):
            QTimer.singleShot(50, self._start_pending_full_crawl)
            return
        self.selectAll()
        self.startCrawl()

    @Slot(result=bool)
    def startCrawl(self) -> bool:
        if not self._can_start("crawl-crawl"):
            self.set_field_errors({"form": "다른 작업이 종료될 때까지 기다려 주세요."})
            return False
        errors = self._validate_supplier()
        if not self._selected:
            errors["categories"] = "수집할 카테고리를 선택하세요."
        if not 1 <= self._max_pages <= 500:
            errors["maxPages"] = "최대 페이지는 1~500 사이여야 합니다."
        if not -1 <= self._delay_seconds <= 60:
            errors["delaySeconds"] = "대기 시간은 0~60초 사이여야 합니다."
        if errors:
            self.set_field_errors(errors)
            return False
        self._reset_progress()
        self.set_field_errors({})
        return self._start_worker(self._factories["crawl"](self._build_request()), "crawl")

    @Slot(result=bool)
    def startRecrawl(self) -> bool:
        if not self._can_start("crawl-stock"):
            self.set_field_errors({"form": "다른 작업이 종료될 때까지 기다려 주세요."})
            return False
        errors = self._validate_supplier()
        if not self._selected:
            errors["categories"] = "재수집할 카테고리를 선택하세요."
        if errors:
            self.set_field_errors(errors)
            return False
        self._reset_progress()
        self.set_field_errors({})
        return self._start_worker(self._factories["stock"](self._build_request()), "stock")

    def _build_request(self) -> CrawlRequest:
        supplier = self._selected_supplier()
        config = load_config()
        delay = self._delay_seconds
        if delay < 0:
            delay = supplier.default_delay_seconds
        if delay is None or delay < 0:
            delay = config.global_delay_seconds
        by_id = {row["id"]: row for row in self._category_rows}
        return CrawlRequest(
            str(supplier.id), supplier.name, supplier.adapter_file,
            [
                (cid, by_id[cid]["path"], by_id[cid].get("url", "") or "")
                for cid in sorted(self._selected)
            ],
            self._max_pages, int(delay), supplier.credential_key,
        )

    def _reset_progress(self) -> None:
        self._product_count = self._option_count = 0
        self._results.resetRows([])
        self._elapsed.start()
        self._elapsed_timer.start()

    def _can_start(self, key: str | None = None) -> bool:
        self._cleanup_retired_workers(schedule=False)
        return (
            not self._shutting_down and not self._busy and self._worker is None
            and not any(getattr(worker, "isRunning", lambda: False)() for worker in self._retired_workers)
            and (not self._app or key is None or self._app.can_acquire_task(key, object()))
        )

    def _start_worker(self, worker, kind: str) -> bool:
        key = f"crawl-{kind}"
        if not self._can_start(key):
            return False
        self._operation_id += 1
        operation_id = self._operation_id
        owner = object()
        self._task_owner = owner
        self._worker = worker
        self._busy = True
        self._discovering = kind == "discovery"
        worker.progress.connect(lambda message: self._on_progress(operation_id, message))
        worker.error.connect(lambda message: self._on_error(operation_id, message))
        if kind == "discovery":
            result_signal = getattr(worker, "categories_found", None) or worker.finished
            result_signal.connect(lambda nodes: self._on_discovered(operation_id, nodes))
            worker.cancelled.connect(lambda: self._on_cancelled(operation_id, 0, 0))
        elif kind == "stock":
            worker.change_found.connect(lambda name, label, detail: self._on_change(operation_id, name, label, detail))
            worker.finished.connect(lambda checked, changes: self._on_finished(operation_id, checked, changes))
            worker.cancelled.connect(lambda checked, changes: self._on_cancelled(operation_id, checked, changes))
        else:
            worker.product_found.connect(lambda name, code, count: self._on_product(operation_id, name, code, count))
            worker.finished.connect(lambda products, options: self._on_finished(operation_id, products, options))
            worker.cancelled.connect(lambda products, options: self._on_cancelled(operation_id, products, options))
        if self._app:
            label = {"discovery": "카테고리 탐색", "stock": "상품 재수집"}.get(kind, "상품 수집")
            if not self._app.acquire_task(key, label, owner):
                self._worker = None
                self._busy = self._discovering = False
                self._task_owner = None
                return False
            self._app.update_owned_task(owner, label)
        self._emit()
        worker.start()
        return True

    def _current(self, operation_id: int) -> bool:
        return operation_id == self._operation_id and operation_id not in self._cancelled_operations

    def _on_progress(self, operation_id: int, message: str) -> None:
        if not self._current(operation_id):
            return
        self._current_target = sanitize_diagnostic(message)
        if self._app and self._task_owner is not None:
            self._app.update_owned_task(self._task_owner, self._current_target)
        self._emit()

    def _on_discovered(self, operation_id: int, nodes) -> None:
        if not self._current(operation_id):
            return
        self._set_categories(list(nodes))
        self._complete()
        if self._pending_full_crawl:
            self._pending_full_crawl = False
            QTimer.singleShot(0, self._start_pending_full_crawl)

    def _on_product(self, operation_id: int, name: str, code: str, option_count: int) -> None:
        if not self._current(operation_id):
            return
        self._product_count += 1
        self._option_count += option_count
        self._current_target = f"상품 {self._product_count}: {name} ({code})"
        rows = list(self._results._rows)
        rows.append({"name": name, "code": code, "optionCount": option_count})
        self._results.resetRows(rows)
        if self._app and self._task_owner is not None:
            self._app.update_owned_task(self._task_owner, self._current_target)
        self._emit()

    def _on_change(self, operation_id: int, name: str, label: str, detail: str) -> None:
        if not self._current(operation_id):
            return
        self._option_count += 1  # 재수집 진행 중 변경 건수 카운터로 재사용
        self._current_target = f"{label}: {name} ({detail})"
        rows = list(self._results._rows)
        rows.append({"name": name, "code": label, "optionCount": 0})
        self._results.resetRows(rows)
        if self._app and self._task_owner is not None:
            self._app.update_owned_task(self._task_owner, self._current_target)
        self._emit()

    def _on_finished(self, operation_id: int, products: int, options: int) -> None:
        if not self._current(operation_id):
            return
        self._product_count, self._option_count = products, options
        self._complete()

    def _complete(self) -> None:
        self._busy = self._discovering = False
        self._elapsed_timer.stop()
        self._retire_worker()
        if self._app and self._task_owner is not None:
            self._app.complete_owned_task(self._task_owner)
        self._task_owner = None
        self._emit()

    def _on_error(self, operation_id: int, message: str) -> None:
        if not self._current(operation_id):
            return
        self._pending_full_crawl = False
        self._busy = self._discovering = False
        self._elapsed_timer.stop()
        self._retire_worker()
        safe = sanitize_diagnostic(message)
        self.set_field_errors({"form": safe})
        if self._app and self._task_owner is not None:
            self._app.fail_owned_task(self._task_owner, safe)
        self._task_owner = None
        self._emit()

    def _on_cancelled(self, operation_id: int, products: int, options: int) -> None:
        if not self._current(operation_id):
            return
        self._product_count, self._option_count = products, options
        self._cancel_operation(operation_id)

    @Slot()
    def cancelCrawl(self) -> None:
        self._cancel_operation(self._operation_id)

    def _cancel_operation(self, operation_id: int) -> None:
        self._pending_full_crawl = False
        self._cancelled_operations.add(operation_id)
        worker = self._worker
        if worker is not None:
            worker.requestInterruption()
        self._busy = self._discovering = False
        self._elapsed_timer.stop()
        self._retire_worker()
        if self._app and self._task_owner is not None:
            self._app.cancel_owned_task(self._task_owner, "수집 취소됨")
        self._task_owner = None
        self._emit()

    def _retire_worker(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            self._retired_workers.append(worker)
            self._cleanup_retired_workers()

    def _cleanup_retired_workers(self, schedule: bool = True) -> None:
        self._retired_workers = [w for w in self._retired_workers if not hasattr(w, "isRunning") or w.isRunning()]
        if schedule and self._retired_workers:
            QTimer.singleShot(25, self._cleanup_retired_workers)

    @Slot()
    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self._operation_id += 1
        self._cancelled_operations.add(self._operation_id - 1)
        self._task_owner = None
        if self._worker is not None:
            self._retired_workers.append(self._worker)
            self._worker = None
        self._retired_workers = stop_workers(self._retired_workers)
        self._busy = self._discovering = False
        self._elapsed_timer.stop()
        self._emit()
