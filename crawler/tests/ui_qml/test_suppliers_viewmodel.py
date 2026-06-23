from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from PySide6.QtCore import QObject, QUrl
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuick import QQuickItem

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


def test_edit_with_existing_credentials_never_loads_secret_and_blank_replacement_preserves_key(
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
        lambda _key: pytest.fail("stored credentials must never be loaded"),
        raising=False,
    )
    monkeypatch.setattr(
        suppliers_module,
        "save_supplier_credentials",
        lambda *args: saved.append(args),
    )
    vm = suppliers_module.SuppliersViewModel(session_factory=session_factory)
    vm.selectSupplier(supplier_id)
    vm.beginEdit()

    assert vm.draft["username"] == ""
    assert vm.draft["password"] == ""
    vm.setDraft({"name": "Existing renamed", "password": ""})

    assert vm.saveDraft() is True
    assert saved == []
    with session_factory() as session:
        assert session.get(Supplier, supplier_id).credential_key == "existing"


@pytest.mark.parametrize(
    ("username", "password", "error_field"),
    [("replacement-user", "", "password"), ("", "replacement-secret", "username")],
)
def test_partial_credential_replacement_requires_both_fields(
    session_factory, monkeypatch, username, password, error_field
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

    monkeypatch.setattr(suppliers_module, "list_adapters", lambda: [])
    vm = suppliers_module.SuppliersViewModel(session_factory=session_factory)
    vm.selectSupplier(supplier_id)
    vm.beginEdit()
    vm.setDraft({"username": username, "password": password})

    assert vm.saveDraft() is False
    assert error_field in vm.fieldErrors


def test_replacement_saves_new_key_then_deletes_old_key(session_factory, monkeypatch) -> None:
    with session_factory() as session:
        supplier = Supplier(
            name="Old Shop",
            base_url="https://old.example",
            needs_login=True,
            credential_key="old-shop",
        )
        session.add(supplier)
        session.commit()
        supplier_id = supplier.id
    import app.ui_qml.viewmodels.suppliers as suppliers_module

    events = []
    monkeypatch.setattr(suppliers_module, "list_adapters", lambda: [])
    monkeypatch.setattr(
        suppliers_module,
        "save_supplier_credentials",
        lambda key, user, password: events.append(("save", key, user, password)),
    )
    monkeypatch.setattr(
        suppliers_module,
        "delete_supplier_credentials",
        lambda key: events.append(("delete", key)),
    )
    vm = suppliers_module.SuppliersViewModel(session_factory=session_factory)
    vm.selectSupplier(supplier_id)
    vm.beginEdit()
    vm.setDraft(
        {
            "name": "New Shop",
            "username": "new-user",
            "password": "new-secret",
        }
    )

    assert vm.saveDraft() is True
    assert events == [
        ("save", "new-shop", "new-user", "new-secret"),
        ("delete", "old-shop"),
    ]
    with session_factory() as session:
        assert session.get(Supplier, supplier_id).credential_key == "new-shop"


def test_disabling_login_deletes_old_credentials(session_factory, monkeypatch) -> None:
    with session_factory() as session:
        supplier = Supplier(
            name="Login Shop",
            base_url="https://login.example",
            needs_login=True,
            credential_key="login-shop",
        )
        session.add(supplier)
        session.commit()
        supplier_id = supplier.id
    import app.ui_qml.viewmodels.suppliers as suppliers_module

    deleted = []
    monkeypatch.setattr(suppliers_module, "list_adapters", lambda: [])
    monkeypatch.setattr(suppliers_module, "delete_supplier_credentials", deleted.append)
    vm = suppliers_module.SuppliersViewModel(session_factory=session_factory)
    vm.selectSupplier(supplier_id)
    vm.beginEdit()
    vm.setDraft({"needsLogin": False})

    assert vm.saveDraft() is True
    assert deleted == ["login-shop"]
    with session_factory() as session:
        assert session.get(Supplier, supplier_id).credential_key is None


def test_failed_replacement_save_preserves_existing_credentials(
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

    deleted = []
    monkeypatch.setattr(suppliers_module, "list_adapters", lambda: [])
    monkeypatch.setattr(
        suppliers_module,
        "save_supplier_credentials",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("keyring unavailable")),
    )
    monkeypatch.setattr(suppliers_module, "delete_supplier_credentials", deleted.append)
    vm = suppliers_module.SuppliersViewModel(session_factory=session_factory)
    vm.selectSupplier(supplier_id)
    vm.beginEdit()
    vm.setDraft({"username": "new-user", "password": "new-secret"})

    assert vm.saveDraft() is False
    assert deleted == []
    assert "new-secret" not in repr(vm.fieldErrors)
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
    assert rows[0]["credentialsConfigured"] is False
    assert rows[1]["adapterReady"] is False
    assert rows[0]["lastCrawlAt"].startswith("2026-06-20")

    vm.selectSupplier(alpha_id)
    assert vm.selectedId == alpha_id
    assert vm.selectedSupplier["name"] == "Alpha"
    assert vm.selectedSupplier["monitorIntervalHours"] == 6
    assert vm.selectedSupplier["lastCrawlAt"].startswith("2026-06-20")


@pytest.mark.parametrize(
    "url", ["http:", "https:///path", "http://", "https://", "https://@"]
)
def test_url_requires_http_scheme_and_host(vm, url) -> None:
    vm.beginCreate()
    vm.setDraft({"name": "도매처", "baseUrl": url})

    assert vm.saveDraft() is False
    assert vm.fieldErrors["baseUrl"] == "올바른 http 또는 https URL을 입력하세요."


@pytest.mark.parametrize("delay", [-1, 61, 1.5, "not-a-number", None])
def test_delay_must_be_integer_between_zero_and_sixty(vm, delay) -> None:
    vm.beginCreate()
    vm.setDraft(
        {
            "name": "도매처",
            "baseUrl": "https://example.com",
            "delaySeconds": delay,
        }
    )

    assert vm.saveDraft() is False
    assert vm.fieldErrors["delaySeconds"] == "수집 대기 시간은 0~60초 정수여야 합니다."


def test_zero_delay_persists_as_none(vm, session_factory) -> None:
    vm.beginCreate()
    vm.setDraft(
        {
            "name": "Zero Delay",
            "baseUrl": "https://example.com",
            "delaySeconds": 0,
        }
    )

    assert vm.saveDraft() is True
    with session_factory() as session:
        assert session.query(Supplier).one().default_delay_seconds is None


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


def test_editor_visibility_clears_password_but_not_url(qt_app) -> None:
    from app.ui_qml.application import create_engine

    engine = create_engine()
    root = engine.rootObjects()[0]
    suppliers_vm = engine.property("suppliersViewModel")
    suppliers_vm.beginCreate()
    suppliers_vm.setDraft(
        {
            "baseUrl": "https://keep.example",
            "needsLogin": True,
        }
    )
    qt_app.processEvents()
    editor = root.findChild(QObject, "supplierEditor")
    url_field = root.findChild(QObject, "supplierUrlField")
    username_field = root.findChild(QObject, "supplierUsernameField")
    password_field = root.findChild(QObject, "supplierPasswordField")

    assert editor is not None
    assert url_field is not None
    assert username_field is not None
    assert password_field is not None
    username_field.setProperty("text", "keep-user")
    password_field.setProperty("text", "clear-me")
    editor.setProperty("visible", False)
    qt_app.processEvents()

    assert url_field.property("text") == "https://keep.example"
    assert username_field.property("text") == "keep-user"
    assert password_field.property("text") == ""


def test_supplier_list_delegate_exposes_text_statuses(
    qt_app, session_factory, monkeypatch
) -> None:
    with session_factory() as session:
        session.add(
            Supplier(
                name="Status Shop",
                base_url="https://status.example",
                needs_login=True,
                credential_key="status-shop",
                adapter_file="ready-adapter",
                monitor_enabled=True,
            )
        )
        session.commit()
    import app.ui_qml.viewmodels.suppliers as suppliers_module
    from app.ui_qml.application import QML_DIRECTORY

    monkeypatch.setattr(suppliers_module, "list_adapters", lambda: ["ready-adapter"])
    monkeypatch.setattr(suppliers_module, "adapter_exists", lambda _slug: True)
    injected_vm = suppliers_module.SuppliersViewModel(session_factory=session_factory)
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(QML_DIRECTORY))
    engine.rootContext().setContextProperty("InjectedSuppliersVM", injected_vm)
    component = QQmlComponent(engine)
    component.setData(
        b'import QtQuick\nimport QtQuick.Controls.Basic\nimport "screens" as Screens\n'
        b'ApplicationWindow { visible: true; width: 1100; height: 700; Screens.SuppliersScreen {'
        b' anchors.fill: parent; viewModel: InjectedSuppliersVM } }',
        QUrl.fromLocalFile(str(QML_DIRECTORY / "SupplierStatusProbe.qml")),
    )
    probe = component.create(engine.rootContext())
    qt_app.processEvents()
    from PySide6.QtTest import QTest

    QTest.qWait(50)
    qt_app.processEvents()

    assert not component.errors()
    assert probe is not None
    supplier_list = probe.findChild(QQuickItem, "supplierList")

    def visual_item(object_name):
        pending = list(supplier_list.childItems())
        while pending:
            item = pending.pop()
            if item.objectName() == object_name:
                return item
            pending.extend(item.childItems())
        return None
    for object_name in (
        "supplierLoginStatus",
        "supplierAdapterStatus",
        "supplierMonitorStatus",
        "supplierLastCrawlStatus",
    ):
        status = visual_item(object_name)
        assert status is not None
        assert status.property("text")
