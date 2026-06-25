from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Product, Supplier
from app.exporters.history import ExportHistoryStore
from app.exporters.validation import validate_export_scope
from app.ui_qml.viewmodels.app import AppViewModel
from app.ui_qml.viewmodels.export import ExportViewModel
from app.workers.export import ExportRequest, ExportWorker


def _session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'scope.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    supplier = Supplier(id="s1", name="Supplier", base_url="https://example.test")
    session.add(supplier)
    session.commit()
    return session, factory


def _product(index: int, **overrides):
    values = dict(
        id=f"p{index:03}", supplier_id="s1", supplier_name="Supplier",
        supplier_product_code=f"P{index:03}", supplier_status="available",
        raw_product_name=f"Product {index}", origin="KR", supply_price=1000,
        main_image_url="https://img.test/a.jpg",
    )
    values.update(overrides)
    return Product(**values)


def test_authoritative_validation_finds_blocking_issue_beyond_display_limit(tmp_path):
    session, _ = _session(tmp_path)
    session.add_all([_product(i, origin=None) for i in range(50)])
    session.add(_product(50, raw_product_name=""))
    session.commit()

    result = validate_export_scope(session, "s1")

    assert result.blocking_count == 1
    assert result.warning_count == 50
    assert len([issue for issue in result.issues if issue["productId"]]) <= 50
    assert any(issue["code"] == "more_issues" for issue in result.issues)


def test_worker_revalidates_mutated_database_before_writing(tmp_path):
    session, factory = _session(tmp_path)
    product = _product(1)
    session.add(product)
    session.commit()
    initial = validate_export_scope(session, "s1")
    assert initial.blocking_count == 0
    product.raw_product_name = ""
    session.commit()
    session.close()
    called = []
    worker = ExportWorker(
        ExportRequest("s1", tmp_path / "out.xlsx"),
        session_factory=factory,
        exporter=lambda *args: called.append(args),
    )
    errors = []
    worker.error.connect(errors.append)

    worker.run()

    assert called == []
    assert errors
    assert not (tmp_path / "out.xlsx").exists()


def test_view_model_rejects_scope_mutation_after_ui_validation(tmp_path):
    session, factory = _session(tmp_path)
    product = _product(1)
    session.add(product)
    session.commit()
    app = AppViewModel()
    calls = []
    vm = ExportViewModel(
        app_view_model=app,
        supplier_loader=lambda: [Supplier(id="s1", name="Supplier", base_url="https://example.test")],
        session_factory=factory,
        worker_factory=lambda request: calls.append(request),
        exports_dir=tmp_path,
        history_store=ExportHistoryStore(tmp_path / "history.json"),
    )
    vm.setSupplierId("s1")
    assert vm.validateScope() is True
    product.raw_product_name = ""
    session.commit()

    assert vm.export() is False
    assert calls == []
    assert vm.warningAcknowledged is False
    assert vm.canExport is False
    assert app.activeTask.state == "idle"


def test_validation_fingerprint_changes_when_same_field_warning_moves_product(tmp_path):
    session, _ = _session(tmp_path)
    seen_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = _product(1, origin=None, last_seen_at=seen_at)
    second = _product(2, last_seen_at=seen_at)
    session.add_all([first, second])
    session.commit()

    initial = validate_export_scope(session, "s1")
    first.origin = "KR"
    second.origin = None
    first.last_seen_at = seen_at
    second.last_seen_at = seen_at
    session.commit()
    session.execute(Product.__table__.update().where(Product.id.in_([first.id, second.id])).values(last_seen_at=seen_at))
    session.commit()
    moved = validate_export_scope(session, "s1")

    assert initial.warning_count == moved.warning_count == 1
    assert initial.product_count == moved.product_count == 2
    assert initial.fingerprint != moved.fingerprint


def test_history_store_tracks_custom_destination_and_terminal_outcomes(tmp_path):
    store = ExportHistoryStore(tmp_path / "history.json", limit=10)
    custom = tmp_path / "elsewhere" / "custom.xlsx"
    attempt = store.begin("s1", "Supplier", custom)
    store.finish(attempt, "success", row_count=7)
    failed = store.begin("s1", "Supplier", tmp_path / "failed.xlsx")
    store.finish(failed, "failed", error="password=hunter2")
    cancelled = store.begin("s1", "Supplier", tmp_path / "cancel.xlsx")
    store.finish(cancelled, "cancelled")

    rows = ExportHistoryStore(tmp_path / "history.json", limit=10).latest()

    assert [row["outcome"] for row in rows] == ["cancelled", "failed", "success"]
    assert rows[-1]["path"] == str(custom)
    assert rows[-1]["rowCount"] == 7
    assert "hunter2" not in rows[1]["error"]


def test_history_store_recovers_from_corrupt_file_and_bounds_latest(tmp_path):
    path = tmp_path / "history.json"
    path.write_text("not-json", encoding="utf-8")
    store = ExportHistoryStore(path, limit=10)
    assert store.latest() == []
    for index in range(12):
        attempt = store.begin("s1", "Supplier", tmp_path / f"{index}.xlsx")
        store.finish(attempt, "success", row_count=index)
    rows = store.latest()
    assert len(rows) == 10
    assert rows[0]["rowCount"] == 11
    assert rows[-1]["rowCount"] == 2
