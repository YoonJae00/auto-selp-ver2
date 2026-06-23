from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlparse

from PySide6.QtCore import Property, QObject, Signal, Slot
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.credentials.store import (
    delete_supplier_credentials,
    load_supplier_credentials,
    save_supplier_credentials,
)
from app.crawlers.registry import adapter_exists, list_adapters
from app.db.models import CrawlRun, Supplier
from app.db.session import get_session
from app.ui_qml.models.list_model import ListModel
from app.ui_qml.viewmodels.base import BaseViewModel


_ROW_ROLES = (
    "id",
    "name",
    "baseUrl",
    "needsLogin",
    "adapterFile",
    "adapterReady",
    "monitorEnabled",
    "monitorIntervalHours",
    "lastCrawlAt",
)


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "", name.lower().replace(" ", "-"))


def _default_draft() -> dict[str, Any]:
    return {
        "name": "",
        "baseUrl": "",
        "needsLogin": False,
        "username": "",
        "password": "",
        "adapterFile": "",
        "delaySeconds": 0,
        "monitorEnabled": False,
        "monitorIntervalHours": 12,
        "credentialsConfigured": False,
    }


class SuppliersViewModel(BaseViewModel):
    stateChanged = Signal()
    deleteConfirmationChanged = Signal()

    def __init__(
        self,
        parent: QObject | None = None,
        session_factory: Callable[[], Session] = get_session,
    ) -> None:
        super().__init__(parent)
        self._session_factory = session_factory
        self._model = ListModel(_ROW_ROLES, parent=self)
        self._selected_id = ""
        self._selected_supplier: dict[str, Any] = {}
        self._draft: dict[str, Any] = {}
        self._editor_open = False
        self._is_editing = False
        self._delete_confirmation_open = False
        self._adapters: list[str] = []
        self.refresh()

    model = Property(QObject, lambda self: self._model, constant=True)
    rows = Property(QObject, lambda self: self._model, constant=True)
    selectedId = Property(str, lambda self: self._selected_id, notify=stateChanged)
    selectedSupplier = Property(
        "QVariantMap", lambda self: dict(self._selected_supplier), notify=stateChanged
    )
    draft = Property("QVariantMap", lambda self: dict(self._draft), notify=stateChanged)
    fieldErrors = Property(
        "QVariantMap", lambda self: dict(self._field_errors), notify=stateChanged
    )
    editorOpen = Property(bool, lambda self: self._editor_open, notify=stateChanged)
    isEditing = Property(bool, lambda self: self._is_editing, notify=stateChanged)
    adapters = Property("QStringList", lambda self: list(self._adapters), notify=stateChanged)
    deleteConfirmationOpen = Property(
        bool,
        lambda self: self._delete_confirmation_open,
        notify=deleteConfirmationChanged,
    )

    @staticmethod
    def _row(supplier: Supplier, last_crawl_at: object) -> dict[str, Any]:
        return {
            "id": supplier.id,
            "name": supplier.name,
            "baseUrl": supplier.base_url,
            "needsLogin": supplier.needs_login,
            "adapterFile": supplier.adapter_file or "",
            "adapterReady": bool(
                supplier.adapter_file and adapter_exists(supplier.adapter_file)
            ),
            "monitorEnabled": supplier.monitor_enabled,
            "monitorIntervalHours": supplier.monitor_interval_hours,
            "lastCrawlAt": last_crawl_at.isoformat() if last_crawl_at else "",
        }

    @staticmethod
    def _detail(
        supplier: Supplier,
        credentials_configured: bool,
        last_crawl_at: object,
    ) -> dict[str, Any]:
        return {
            "id": supplier.id,
            "name": supplier.name,
            "baseUrl": supplier.base_url,
            "needsLogin": supplier.needs_login,
            "adapterFile": supplier.adapter_file or "",
            "adapterReady": bool(
                supplier.adapter_file and adapter_exists(supplier.adapter_file)
            ),
            "delaySeconds": supplier.default_delay_seconds or 0,
            "monitorEnabled": supplier.monitor_enabled,
            "monitorIntervalHours": supplier.monitor_interval_hours,
            "credentialsConfigured": credentials_configured,
            "lastCrawlAt": last_crawl_at.isoformat() if last_crawl_at else "",
        }

    @Slot()
    def refresh(self) -> None:
        last_crawl = (
            select(
                CrawlRun.supplier_id.label("supplier_id"),
                func.max(CrawlRun.started_at).label("last_crawl_at"),
            )
            .group_by(CrawlRun.supplier_id)
            .subquery()
        )
        with self._session_factory() as session:
            results = session.execute(
                select(Supplier, last_crawl.c.last_crawl_at)
                .outerjoin(last_crawl, last_crawl.c.supplier_id == Supplier.id)
                .order_by(Supplier.name)
            ).all()
        self._adapters = list_adapters()
        self._model.resetRows(
            [self._row(supplier, timestamp) for supplier, timestamp in results]
        )
        if self._selected_id:
            self._load_selection(self._selected_id)
        self.stateChanged.emit()

    def _load_selection(self, supplier_id: str) -> bool:
        with self._session_factory() as session:
            result = session.execute(
                select(Supplier, func.max(CrawlRun.started_at))
                .outerjoin(CrawlRun, CrawlRun.supplier_id == Supplier.id)
                .where(Supplier.id == supplier_id)
                .group_by(Supplier.id)
            ).one_or_none()
            if result is None:
                self._selected_id = ""
                self._selected_supplier = {}
                return False
            supplier, last_crawl_at = result
            self._selected_id = supplier.id
            self._selected_supplier = self._detail(
                supplier, bool(supplier.credential_key), last_crawl_at
            )
            return True

    @Slot(str)
    def selectSupplier(self, supplier_id: str) -> None:
        self._load_selection(supplier_id)
        self.stateChanged.emit()

    @Slot()
    def beginCreate(self) -> None:
        self._clear_transient()
        self._draft = _default_draft()
        self._editor_open = True
        self.stateChanged.emit()

    @Slot()
    def beginEdit(self) -> None:
        if not self._selected_id:
            return
        with self._session_factory() as session:
            supplier = session.get(Supplier, self._selected_id)
            if supplier is None:
                return
            credentials = (
                load_supplier_credentials(supplier.credential_key)
                if supplier.credential_key
                else None
            )
            self._draft = {
                "name": supplier.name,
                "baseUrl": supplier.base_url,
                "needsLogin": supplier.needs_login,
                "username": credentials[0] if credentials else "",
                "password": "",
                "adapterFile": supplier.adapter_file or "",
                "delaySeconds": supplier.default_delay_seconds or 0,
                "monitorEnabled": supplier.monitor_enabled,
                "monitorIntervalHours": supplier.monitor_interval_hours,
                "credentialsConfigured": bool(credentials),
            }
        self._field_errors = {}
        self._is_editing = True
        self._editor_open = True
        self.stateChanged.emit()

    @Slot("QVariantMap")
    def setDraft(self, values: Mapping[str, Any]) -> None:
        if not self._editor_open:
            return
        self._draft.update(dict(values))
        self.stateChanged.emit()

    def set_field_errors(self, errors: Mapping[str, object]) -> None:
        previous = dict(self._field_errors)
        super().set_field_errors(errors)
        if self._field_errors != previous:
            self.stateChanged.emit()

    def _validate(self) -> dict[str, str]:
        errors: dict[str, str] = {}
        name = str(self._draft.get("name", "")).strip()
        base_url = str(self._draft.get("baseUrl", "")).strip()
        if not name:
            errors["name"] = "도매처명을 입력하세요."
        if not base_url:
            errors["baseUrl"] = "URL을 입력하세요."
        elif urlparse(base_url).scheme not in {"http", "https"}:
            errors["baseUrl"] = "URL은 http:// 또는 https://로 시작해야 합니다."

        if bool(self._draft.get("needsLogin")):
            if not str(self._draft.get("username", "")).strip():
                errors["username"] = "로그인 아이디를 입력하세요."
            has_new_password = bool(str(self._draft.get("password", "")))
            has_stored_password = bool(self._draft.get("credentialsConfigured"))
            if not has_new_password and not (self._is_editing and has_stored_password):
                errors["password"] = "로그인 비밀번호를 입력하세요."

        try:
            interval = int(self._draft.get("monitorIntervalHours", 12))
        except (TypeError, ValueError):
            interval = 0
        if not 1 <= interval <= 168:
            errors["monitorIntervalHours"] = "확인 주기는 1~168시간이어야 합니다."
        return errors

    @Slot(result=bool)
    def saveDraft(self) -> bool:
        errors = self._validate()
        self.set_field_errors(errors)
        if errors:
            return False

        name = str(self._draft["name"]).strip()
        base_url = str(self._draft["baseUrl"]).strip()
        needs_login = bool(self._draft.get("needsLogin"))
        username = str(self._draft.get("username", "")).strip()
        password = str(self._draft.get("password", ""))
        adapter_file = str(self._draft.get("adapterFile", "")).strip()
        if adapter_file not in self._adapters:
            adapter_file = ""
        delay = int(self._draft.get("delaySeconds", 0) or 0)
        interval = int(self._draft.get("monitorIntervalHours", 12))
        slug = _slugify(name)

        with self._session_factory() as session:
            supplier = (
                session.get(Supplier, self._selected_id) if self._is_editing else None
            )
            if self._is_editing and supplier is None:
                self.set_field_errors({"form": "선택한 도매처를 찾을 수 없습니다."})
                return False
            if supplier is None:
                supplier = Supplier(name=name, base_url=base_url)
                session.add(supplier)

            if needs_login and password:
                save_supplier_credentials(slug, username, password)
                credential_key = slug
            elif needs_login and self._is_editing:
                credential_key = supplier.credential_key
            elif needs_login:
                credential_key = slug
            else:
                credential_key = None

            supplier.name = name
            supplier.base_url = base_url
            supplier.needs_login = needs_login
            supplier.adapter_file = adapter_file or None
            supplier.default_delay_seconds = delay or None
            supplier.monitor_enabled = bool(self._draft.get("monitorEnabled"))
            supplier.monitor_interval_hours = interval
            supplier.credential_key = credential_key
            session.commit()
            saved_id = supplier.id

        self._selected_id = saved_id
        self._clear_transient()
        self.refresh()
        self._load_selection(saved_id)
        self.stateChanged.emit()
        return True

    def _clear_transient(self) -> None:
        self._draft = {}
        self._field_errors = {}
        self._editor_open = False
        self._is_editing = False

    @Slot()
    def cancelEdit(self) -> None:
        self._clear_transient()
        self.stateChanged.emit()

    @Slot(result=bool)
    def requestDelete(self) -> bool:
        if not self._selected_id:
            return False
        self._delete_confirmation_open = True
        self.deleteConfirmationChanged.emit()
        return True

    @Slot()
    def cancelDelete(self) -> None:
        self._delete_confirmation_open = False
        self.deleteConfirmationChanged.emit()

    @Slot(result=bool)
    def confirmDelete(self) -> bool:
        if not self._delete_confirmation_open or not self._selected_id:
            return False
        with self._session_factory() as session:
            supplier = session.get(Supplier, self._selected_id)
            if supplier is None:
                self.cancelDelete()
                return False
            if supplier.credential_key:
                delete_supplier_credentials(supplier.credential_key)
            session.delete(supplier)
            session.commit()
        self._selected_id = ""
        self._selected_supplier = {}
        self._delete_confirmation_open = False
        self._clear_transient()
        self.refresh()
        self.deleteConfirmationChanged.emit()
        self.stateChanged.emit()
        return True
