from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.db.models import CrawlRun, Product, StockChange, Supplier
from app.db.session import get_session
from app.ui_qml.models.list_model import ListModel as RoleListModel
from app.ui_qml.viewmodels.base import BaseViewModel


EVENT_ROLES = (
    "id", "detectedAt", "supplierId", "supplierName", "productId",
    "productCode", "productName", "changeType", "changeLabel",
    "previousValue", "newValue", "acknowledged",
)
SUPPLIER_ROLES = ("id", "name")
CHANGE_TYPES = {"", "sold_out", "restocked", "price_changed", "stock_changed"}
CHANGE_LABELS = {
    "sold_out": "품절", "restocked": "재입고", "price_changed": "가격 변경",
    "stock_changed": "재고 변경",
}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str:
    aware = _aware(value)
    return aware.isoformat() if aware else ""


class MonitorViewModel(BaseViewModel):
    stateChanged = Signal()

    def __init__(
        self,
        parent: QObject | None = None,
        session_factory: Callable[[], Session] = get_session,
        schedule_loader: Callable[[str], Mapping[str, Any] | None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._session_factory = session_factory
        self._schedule_loader = schedule_loader
        self._events = RoleListModel(EVENT_ROLES, parent=self)
        self._suppliers = RoleListModel(SUPPLIER_ROLES, parent=self)
        self._supplier_filter = ""
        self._change_type = ""
        self._selected_change_id = ""
        self._selected_supplier_id = ""
        self._metrics = self._empty_metrics()
        self._selected_supplier_schedule: dict[str, Any] = {}
        self.refresh()

    events = Property(QObject, lambda self: self._events, constant=True)
    rows = Property(QObject, lambda self: self._events, constant=True)
    suppliers = Property(QObject, lambda self: self._suppliers, constant=True)
    supplierFilter = Property(str, lambda self: self._supplier_filter, notify=stateChanged)
    changeType = Property(str, lambda self: self._change_type, notify=stateChanged)
    selectedChangeId = Property(str, lambda self: self._selected_change_id, notify=stateChanged)
    metrics = Property("QVariantMap", lambda self: dict(self._metrics), notify=stateChanged)
    selectedSupplierSchedule = Property(
        "QVariantMap", lambda self: dict(self._selected_supplier_schedule), notify=stateChanged
    )

    @staticmethod
    def _empty_metrics() -> dict[str, int]:
        return {"unread": 0, "soldOut": 0, "restocked": 0, "priceChanged": 0, "failedSchedules": 0}

    def _event_statement(self):
        statement = (
            select(StockChange, Product, Supplier)
            .join(Product, StockChange.product_id == Product.id)
            .join(Supplier, Product.supplier_id == Supplier.id)
            .order_by(StockChange.detected_at.desc(), StockChange.id)
        )
        if self._supplier_filter:
            statement = statement.where(Supplier.id == self._supplier_filter)
        if self._change_type:
            statement = statement.where(StockChange.change_type == self._change_type)
        return statement

    @staticmethod
    def _row(change: StockChange, product: Product, supplier: Supplier) -> dict[str, Any]:
        return {
            "id": change.id, "detectedAt": _iso(change.detected_at),
            "supplierId": supplier.id, "supplierName": supplier.name,
            "productId": product.id, "productCode": product.supplier_product_code,
            "productName": product.raw_product_name, "changeType": change.change_type,
            "changeLabel": CHANGE_LABELS.get(change.change_type, change.change_type),
            "previousValue": change.previous_value or "", "newValue": change.new_value or "",
            "acknowledged": bool(change.acknowledged),
        }

    @staticmethod
    def _metrics_for(rows: list[dict[str, Any]]) -> dict[str, int]:
        metrics = MonitorViewModel._empty_metrics()
        metric_for_type = {
            "sold_out": "soldOut", "restocked": "restocked",
            "price_changed": "priceChanged",
        }
        for row in rows:
            if not row["acknowledged"]:
                metrics["unread"] += 1
            key = metric_for_type.get(row["changeType"])
            if key:
                metrics[key] += 1
        return metrics

    def _schedule(self, session: Session, supplier_id: str) -> dict[str, Any]:
        if not supplier_id:
            return {}
        supplier = session.get(Supplier, supplier_id)
        if supplier is None:
            return {}
        latest = session.execute(
            select(CrawlRun).where(
                CrawlRun.supplier_id == supplier_id, CrawlRun.run_type == "stock_check"
            ).order_by(CrawlRun.started_at.desc(), CrawlRun.id.desc()).limit(1)
        ).scalar_one_or_none()
        failure = session.execute(
            select(CrawlRun).where(
                CrawlRun.supplier_id == supplier_id,
                CrawlRun.run_type == "stock_check",
                or_(CrawlRun.status == "failed", CrawlRun.error.is_not(None)),
            ).order_by(CrawlRun.started_at.desc(), CrawlRun.id.desc()).limit(1)
        ).scalar_one_or_none()
        last_at = (latest.finished_at or latest.started_at) if latest else None
        estimated_next = (_aware(last_at) + timedelta(hours=supplier.monitor_interval_hours)) if supplier.monitor_enabled and last_at else None
        scheduler_state = self._schedule_loader(supplier_id) if self._schedule_loader else None
        real_next = scheduler_state.get("next_run") if scheduler_state else None
        next_at = real_next or estimated_next
        return {
            "supplierId": supplier.id, "supplierName": supplier.name,
            "monitorEnabled": bool(supplier.monitor_enabled),
            "intervalHours": supplier.monitor_interval_hours,
            "lastCheckAt": _iso(last_at),
            "nextCheckAt": _iso(next_at) if isinstance(next_at, datetime) else str(next_at or ""),
            "nextCheckEstimated": bool(estimated_next and not real_next),
            "latestFailure": failure.error or "" if failure else "",
        }

    @Slot()
    def refresh(self) -> None:
        with self._session_factory() as session:
            suppliers = session.execute(select(Supplier).order_by(Supplier.name)).scalars().all()
            results = session.execute(self._event_statement()).all()
            rows = [self._row(change, product, supplier) for change, product, supplier in results]
            failed_statement = select(func.count()).select_from(CrawlRun).where(
                CrawlRun.run_type == "stock_check", CrawlRun.status == "failed"
            )
            if self._supplier_filter:
                failed_statement = failed_statement.where(
                    CrawlRun.supplier_id == self._supplier_filter
                )
            failed_schedules = session.scalar(failed_statement) or 0
            known_ids = {row["id"] for row in rows}
            if self._selected_change_id not in known_ids:
                self._selected_change_id = ""
                if not self._supplier_filter:
                    self._selected_supplier_id = ""
            if self._supplier_filter:
                self._selected_supplier_id = self._supplier_filter
            elif self._selected_change_id:
                self._selected_supplier_id = next(row["supplierId"] for row in rows if row["id"] == self._selected_change_id)
            self._selected_supplier_schedule = self._schedule(session, self._selected_supplier_id)
        self._suppliers.resetRows([{"id": "", "name": "전체 도매처"}] + [{"id": s.id, "name": s.name} for s in suppliers])
        self._events.resetRows(rows)
        self._metrics = self._metrics_for(rows)
        self._metrics["failedSchedules"] = failed_schedules
        self.stateChanged.emit()

    @Slot(str)
    def setSupplierFilter(self, supplier_id: str) -> None:
        valid = {row["id"] for row in self._suppliers._rows}
        if supplier_id not in valid:
            return
        self._supplier_filter = supplier_id
        self._selected_supplier_id = supplier_id
        self.refresh()

    @Slot(str)
    def setChangeType(self, change_type: str) -> None:
        if change_type not in CHANGE_TYPES:
            return
        self._change_type = change_type
        self.refresh()

    @Slot(str)
    def selectChange(self, change_id: str) -> None:
        self._selected_change_id = change_id if any(row["id"] == change_id for row in self._events._rows) else ""
        self.refresh()

    @Slot(int)
    def selectEventAt(self, index: int) -> None:
        if not 0 <= index < len(self._events._rows):
            self.selectChange("")
            return
        self.selectChange(str(self._events._rows[index]["id"]))

    def _acknowledge(self, selected_only: bool) -> None:
        try:
            with self._session_factory() as session:
                if selected_only:
                    change = session.get(StockChange, self._selected_change_id) if self._selected_change_id else None
                    if change is not None:
                        change.acknowledged = True
                        change.acknowledged_at = datetime.now(timezone.utc)
                else:
                    ids = [row["id"] for row in self._events._rows if not row["acknowledged"]]
                    if ids:
                        session.execute(update(StockChange).where(StockChange.id.in_(ids)).values(acknowledged=True, acknowledged_at=datetime.now(timezone.utc)))
                session.commit()
            self.set_field_errors({})
            self.refresh()
        except Exception:
            try:
                session.rollback()
            except Exception:
                pass
            self.set_field_errors({"form": "변경 사항을 읽음 처리하지 못했습니다."})

    @Slot()
    def acknowledgeSelected(self) -> None:
        self._acknowledge(True)

    @Slot()
    def acknowledgeAll(self) -> None:
        self._acknowledge(False)
