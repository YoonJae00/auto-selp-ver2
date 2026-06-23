from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from PySide6.QtCore import QObject

from app.db.models import Base, CrawlRun, Supplier


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def vm(session_factory, monkeypatch):
    import app.ui_qml.viewmodels.suppliers as suppliers_module

    monkeypatch.setattr(suppliers_module, "list_adapters", lambda: ["ready-adapter"])
    monkeypatch.setattr(
        suppliers_module,
        "adapter_exists",
        lambda slug: slug == "ready-adapter",
    )
    return suppliers_module.SuppliersViewModel(session_factory=session_factory)


def model_rows(model) -> list[dict]:
    roles = {
        role: bytes(name).decode("utf-8") for role, name in model.roleNames().items()
    }
    return [
        {
            name: model.data(model.index(row, 0), role)
            for role, name in roles.items()
        }
        for row in range(model.rowCount())
    ]


def test_missing_name_has_exact_korean_error(vm) -> None:
    vm.beginCreate()
    vm.setDraft({"name": "  ", "baseUrl": "https://example.com"})

    assert vm.saveDraft() is False
    assert vm.fieldErrors["name"] == "도매처명을 입력하세요."


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("", "URL을 입력하세요."),
        ("ftp://example.com", "URL은 http:// 또는 https://로 시작해야 합니다."),
    ],
)
def test_url_is_required_and_http_or_https(vm, url, message) -> None:
    vm.beginCreate()
    vm.setDraft({"name": "도매처", "baseUrl": url})

    assert vm.saveDraft() is False
    assert vm.fieldErrors["baseUrl"] == message


def test_create_login_supplier_saves_credentials_without_exposing_secret(
    vm, session_factory, monkeypatch
) -> None:
    saved: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        "app.ui_qml.viewmodels.suppliers.save_supplier_credentials",
        lambda key, username, password: saved.append((key, username, password)),
    )
    vm.beginCreate()
    vm.setDraft(
        {
            "name": "My Shop",
            "baseUrl": "https://shop.example",
            "needsLogin": True,
            "username": "buyer",
            "password": "super-secret",
            "monitorIntervalHours": 12,
        }
    )

    assert vm.saveDraft() is True
    assert saved == [("my-shop", "buyer", "super-secret")]
    assert "super-secret" not in repr(vm.draft)
    assert "super-secret" not in repr(vm.fieldErrors)
    assert "super-secret" not in repr(model_rows(vm.model))

    with session_factory() as session:
        supplier = session.query(Supplier).one()
        assert supplier.credential_key == "my-shop"

    vm.selectSupplier(vm.selectedId)
    assert vm.selectedSupplier["credentialsConfigured"] is True
    assert "password" not in vm.selectedSupplier


def test_edit_with_existing_credentials_and_blank_password_preserves_secret(
    session_factory, monkeypatch
) -> None:
    with session_factory() as session:
        supplier = Supplier(
            name="Existing",
            base_url="https://existing.example",
            needs_login=True,
            credential_key="existing",
        )
        session.add(supplier)
        session.commit()
        supplier_id = supplier.id

    import app.ui_qml.viewmodels.suppliers as suppliers_module

    saved = []
    monkeypatch.setattr(suppliers_module, "list_adapters", lambda: [])
    monkeypatch.setattr(suppliers_module, "adapter_exists", lambda _slug: False)
    monkeypatch.setattr(
        suppliers_module,
        "load_supplier_credentials",
        lambda key: ("stored-user", "stored-secret") if key == "existing" else None,
    )
    monkeypatch.setattr(
        suppliers_module,
        "save_supplier_credentials",
        lambda *args: saved.append(args),
    )
    vm = suppliers_module.SuppliersViewModel(session_factory=session_factory)
    vm.selectSupplier(supplier_id)
    vm.beginEdit()

    assert vm.draft["username"] == "stored-user"
    assert vm.draft["password"] == ""
    vm.setDraft({"name": "Existing renamed", "password": ""})

    assert vm.saveDraft() is True
    assert saved == []
    with session_factory() as session:
        assert session.get(Supplier, supplier_id).credential_key == "existing"


def test_delete_calls_credential_delete_and_clears_state(
    session_factory, monkeypatch
) -> None:
    with session_factory() as session:
        supplier = Supplier(
            name="Delete me",
            base_url="https://delete.example",
            needs_login=True,
            credential_key="delete-me",
        )
        session.add(supplier)
        session.commit()
        supplier_id = supplier.id

    import app.ui_qml.viewmodels.suppliers as suppliers_module

    deleted = []
    monkeypatch.setattr(suppliers_module, "list_adapters", lambda: [])
    monkeypatch.setattr(suppliers_module, "adapter_exists", lambda _slug: False)
    monkeypatch.setattr(
        suppliers_module,
        "load_supplier_credentials",
        lambda _key: ("delete-user", "stored-secret"),
    )
    monkeypatch.setattr(
        suppliers_module,
        "delete_supplier_credentials",
        lambda key: deleted.append(key),
    )
    vm = suppliers_module.SuppliersViewModel(session_factory=session_factory)
    vm.selectSupplier(supplier_id)
    vm.beginEdit()
    vm.setDraft({"password": "temporary-secret"})

    assert vm.requestDelete() is True
    assert vm.deleteConfirmationOpen is True
    assert vm.confirmDelete() is True
    assert deleted == ["delete-me"]
    assert vm.selectedId == ""
    assert vm.draft == {}
    assert vm.editorOpen is False
    with session_factory() as session:
        assert session.get(Supplier, supplier_id) is None


def test_rows_are_ordered_include_status_and_selection_detail(
    session_factory, monkeypatch
) -> None:
    with session_factory() as session:
        zulu = Supplier(
            name="Zulu",
            base_url="https://zulu.example",
            adapter_file="missing-adapter",
        )
        alpha = Supplier(
            name="Alpha",
            base_url="https://alpha.example",
            adapter_file="ready-adapter",
            monitor_enabled=True,
            monitor_interval_hours=6,
        )
        session.add_all([zulu, alpha])
        session.flush()
        session.add(
            CrawlRun(
                supplier_id=alpha.id,
                run_type="full",
                status="completed",
                started_at=datetime(2026, 6, 20, 3, 4, tzinfo=timezone.utc),
            )
        )
        session.commit()
        alpha_id = alpha.id

    import app.ui_qml.viewmodels.suppliers as suppliers_module

    monkeypatch.setattr(suppliers_module, "list_adapters", lambda: ["ready-adapter"])
    monkeypatch.setattr(
        suppliers_module,
        "adapter_exists",
        lambda slug: slug == "ready-adapter",
    )
    vm = suppliers_module.SuppliersViewModel(session_factory=session_factory)
    rows = model_rows(vm.rows)

    assert [row["name"] for row in rows] == ["Alpha", "Zulu"]
    assert rows[0]["adapterReady"] is True
    assert rows[1]["adapterReady"] is False
    assert rows[0]["lastCrawlAt"].startswith("2026-06-20")

    vm.selectSupplier(alpha_id)
    assert vm.selectedId == alpha_id
    assert vm.selectedSupplier["name"] == "Alpha"
    assert vm.selectedSupplier["monitorIntervalHours"] == 6
    assert vm.selectedSupplier["lastCrawlAt"].startswith("2026-06-20")


def test_cancel_clears_transient_secret(vm) -> None:
    vm.beginCreate()
    vm.setDraft(
        {
            "name": "Temporary",
            "baseUrl": "https://temporary.example",
            "password": "never-retain-this",
        }
    )

    vm.cancelEdit()

    assert vm.draft == {}
    assert vm.fieldErrors == {}
    assert vm.editorOpen is False
    assert "never-retain-this" not in repr(vm)


def test_application_retains_suppliers_vm_and_loads_real_supplier_screen(qt_app) -> None:
    from app.ui_qml.application import create_engine

    engine = create_engine()
    root = engine.rootObjects()[0]

    assert b"suppliersViewModel" in engine.dynamicPropertyNames()
    assert engine.property("suppliersViewModel") is not None
    assert root.findChild(QObject, "suppliersScreen") is not None
    assert root.findChild(QObject, "suppliersPlaceholder") is None


def test_supplier_editor_opens_and_shows_inline_name_error(qt_app) -> None:
    from app.ui_qml.application import create_engine

    engine = create_engine()
    root = engine.rootObjects()[0]
    suppliers_vm = engine.property("suppliersViewModel")

    suppliers_vm.beginCreate()
    suppliers_vm.setDraft({"name": "", "baseUrl": "https://example.com"})
    assert suppliers_vm.saveDraft() is False
    qt_app.processEvents()

    editor = root.findChild(QObject, "supplierEditor")
    name_error = root.findChild(QObject, "supplierNameError")
    assert editor is not None
    assert editor.property("visible") is True
    assert name_error is not None
    assert name_error.property("text") == "도매처명을 입력하세요."
