from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlparse

from PySide6.QtCore import Property, QObject, Signal, Slot
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.credentials.store import (
    delete_supplier_credentials,
    load_supplier_credentials,
    save_supplier_credentials,
)
from app.crawlers.registry import adapter_exists, list_adapters
from app.db.models import (
    CrawlRun,
    Product,
    ProductOption,
    StockChange,
    StockSnapshot,
    Supplier,
)
from app.db.session import get_session
from app.ui_qml.models.list_model import ListModel
from app.ui_qml.viewmodels.base import BaseViewModel


_ROW_ROLES = (
    "id",
    "name",
    "baseUrl",
    "needsLogin",
    "credentialsConfigured",
    "adapterFile",
    "adapterReady",
    "monitorEnabled",
    "monitorIntervalHours",
    "lastCrawlAt",
)


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "", name.lower().replace(" ", "-"))


def _credential_key(supplier_id: str) -> str:
    return f"supplier:{supplier_id}:{uuid.uuid4().hex}"


def _best_effort_delete_credentials(credential_key: str | None) -> None:
    if not credential_key:
        return
    try:
        delete_supplier_credentials(credential_key)
    except Exception:
        pass


def _bulk_delete_supplier(session: Session, supplier_id: str) -> None:
    product_ids = select(Product.id).where(Product.supplier_id == supplier_id)
    session.execute(delete(StockChange).where(StockChange.product_id.in_(product_ids)))
    session.execute(
        delete(StockSnapshot).where(StockSnapshot.product_id.in_(product_ids))
    )
    session.execute(
        delete(ProductOption).where(ProductOption.product_id.in_(product_ids))
    )
    session.execute(delete(Product).where(Product.supplier_id == supplier_id))
    session.execute(delete(CrawlRun).where(CrawlRun.supplier_id == supplier_id))
    session.execute(delete(Supplier).where(Supplier.id == supplier_id))


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
            "credentialsConfigured": bool(supplier.credential_key),
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

    @Slot(str, str, str, bool)
    def upsertFromAdapter(
        self, slug: str, name: str, base_url: str, needs_login: bool
    ) -> None:
        """어댑터 마법사 저장 완료 시 호출 — 어댑터(slug)에 대응하는 도매처를
        자동으로 만들거나 갱신한다. 자격증명은 마법사가 이미 slug 키로 저장했으므로
        credential_key = slug 로 연결한다. 사용자는 별도 도매처 등록 폼을 거치지 않는다."""
        slug = str(slug).strip()
        if not slug:
            return
        with self._session_factory() as session:
            supplier = session.execute(
                select(Supplier).where(Supplier.adapter_file == slug)
            ).scalar_one_or_none()
            created = supplier is None
            if created:
                supplier = Supplier(id=str(uuid.uuid4()), name=name, base_url=base_url)
                session.add(supplier)
            supplier.name = name or supplier.name
            supplier.base_url = base_url or supplier.base_url
            supplier.adapter_file = slug
            supplier.needs_login = bool(needs_login)
            if not needs_login:
                supplier.credential_key = None
            elif load_supplier_credentials(slug):
                # 마법사가 slug 키로 자격증명을 이관해 둔 경우
                supplier.credential_key = slug
            elif supplier.credential_key and load_supplier_credentials(supplier.credential_key):
                # 기존에 동작하던 자격증명 키가 있으면 유지 (덮어써서 로그인 깨지 않도록)
                pass
            else:
                supplier.credential_key = slug
            session.commit()
            saved_id = supplier.id
        self.refresh()
        self._selected_id = saved_id
        self._load_selection(saved_id)
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
            self._draft = {
                "name": supplier.name,
                "baseUrl": supplier.base_url,
                "needsLogin": supplier.needs_login,
                "username": "",
                "password": "",
                "adapterFile": supplier.adapter_file or "",
                "delaySeconds": supplier.default_delay_seconds or 0,
                "monitorEnabled": supplier.monitor_enabled,
                "monitorIntervalHours": supplier.monitor_interval_hours,
                "credentialsConfigured": bool(supplier.credential_key),
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
        else:
            parsed_url = urlparse(base_url)
            if parsed_url.scheme not in {"http", "https"}:
                errors["baseUrl"] = "URL은 http:// 또는 https://로 시작해야 합니다."
            elif not parsed_url.hostname:
                errors["baseUrl"] = "올바른 http 또는 https URL을 입력하세요."

        if bool(self._draft.get("needsLogin")):
            has_username = bool(str(self._draft.get("username", "")).strip())
            has_password = bool(str(self._draft.get("password", "")))
            has_stored_credentials = bool(self._draft.get("credentialsConfigured"))
            replacement_started = has_username or has_password
            if replacement_started or not (self._is_editing and has_stored_credentials):
                if not has_username:
                    errors["username"] = "로그인 아이디를 입력하세요."
                if not has_password:
                    errors["password"] = "로그인 비밀번호를 입력하세요."

        delay_raw = self._draft.get("delaySeconds", 0)
        try:
            if not isinstance(delay_raw, int) or isinstance(delay_raw, bool):
                raise ValueError
            delay = delay_raw
        except (TypeError, ValueError):
            delay = -1
        if not 0 <= delay <= 60:
            errors["delaySeconds"] = "수집 대기 시간은 0~60초 정수여야 합니다."

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
        new_credential_saved = False
        old_credential_key: str | None = None

        with self._session_factory() as session:
            supplier = (
                session.get(Supplier, self._selected_id) if self._is_editing else None
            )
            if self._is_editing and supplier is None:
                self.set_field_errors({"form": "선택한 도매처를 찾을 수 없습니다."})
                return False
            if supplier is None:
                supplier = Supplier(id=str(uuid.uuid4()), name=name, base_url=base_url)
                session.add(supplier)
            old_credential_key = supplier.credential_key

            if needs_login and password:
                new_credential_key = _credential_key(supplier.id)
                try:
                    save_supplier_credentials(new_credential_key, username, password)
                except Exception:
                    _best_effort_delete_credentials(new_credential_key)
                    self.set_field_errors(
                        {"form": "로그인 정보를 안전하게 저장하지 못했습니다."}
                    )
                    return False
                new_credential_saved = True
                credential_key = new_credential_key
            elif needs_login and self._is_editing:
                # A rename without replacement keeps the opaque key. Migrating it
                # would require reading and exposing the stored password.
                credential_key = supplier.credential_key
            elif needs_login:
                credential_key = supplier.credential_key
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
            try:
                session.commit()
            except Exception:
                session.rollback()
                if new_credential_saved:
                    _best_effort_delete_credentials(credential_key)
                self.set_field_errors({"form": "도매처 정보를 저장하지 못했습니다."})
                return False
            saved_id = supplier.id

        if old_credential_key and (
            not needs_login
            or (new_credential_saved and old_credential_key != credential_key)
        ):
            _best_effort_delete_credentials(old_credential_key)

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
        supplier_id = self._selected_id
        with self._session_factory() as session:
            credential_key = session.scalar(
                select(Supplier.credential_key).where(Supplier.id == supplier_id)
            )
            supplier_exists = session.scalar(
                select(Supplier.id).where(Supplier.id == supplier_id)
            )
            if supplier_exists is None:
                self.cancelDelete()
                return False
            try:
                _bulk_delete_supplier(session, supplier_id)
                session.commit()
            except Exception:
                session.rollback()
                self.set_field_errors({"form": "도매처를 삭제하지 못했습니다."})
                return False
        _best_effort_delete_credentials(credential_key)
        self._selected_id = ""
        self._selected_supplier = {}
        self._delete_confirmation_open = False
        self._clear_transient()
        self.refresh()
        self.deleteConfirmationChanged.emit()
        self.stateChanged.emit()
        return True
