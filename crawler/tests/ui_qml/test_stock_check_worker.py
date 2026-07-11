from __future__ import annotations

from app.crawlers.base import StockSnapshotData
from app.db.models import Product, StockChange, StockSnapshot, Supplier
from app.db.session import get_session, init_db
from app.workers.crawl import CrawlRequest, StockCheckWorker


def _seed(engine):
    session = get_session(engine)
    supplier = Supplier(id="s1", name="Shop", base_url="https://x")
    product = Product(
        id="p1", supplier_id="s1", supplier_name="Shop",
        supplier_product_code="CODE-1", supplier_status="available",
        raw_product_name="상품 하나", supply_price=10000,
    )
    session.add_all([supplier, product])
    session.add(StockSnapshot(product_id="p1", supplier_status="available", supply_price=10000))
    session.commit()
    session.close()


def _worker(engine) -> StockCheckWorker:
    request = CrawlRequest("s1", "Shop", "shop-adapter", [], 1, 0, None)
    return StockCheckWorker(request, session_factory=lambda: get_session(engine))


def test_persist_snapshot_updates_product_and_records_changes(qt_app, tmp_path):
    engine = init_db(tmp_path / "t.db")
    _seed(engine)
    worker = _worker(engine)
    session = get_session(engine)

    changed = worker._persist_snapshot(
        session, crawl_run_id=None,
        snapshot=StockSnapshotData("CODE-1", supplier_status="sold_out", supply_price=12000),
    )
    session.commit()

    assert changed == 2  # 품절 + 가격 변경
    product = session.get(Product, "p1")
    assert product.supplier_status == "sold_out"
    assert product.supply_price == 12000
    assert session.query(StockSnapshot).filter_by(product_id="p1").count() == 2
    types = {c.change_type for c in session.query(StockChange).filter_by(product_id="p1")}
    assert types == {"sold_out", "price_changed"}
    session.close()


def test_persist_snapshot_no_change_records_nothing(qt_app, tmp_path):
    engine = init_db(tmp_path / "t.db")
    _seed(engine)
    worker = _worker(engine)
    session = get_session(engine)

    changed = worker._persist_snapshot(
        session, crawl_run_id=None,
        snapshot=StockSnapshotData("CODE-1", supplier_status="available", supply_price=10000),
    )
    session.commit()

    assert changed == 0
    assert session.query(StockChange).count() == 0
    assert session.query(StockSnapshot).filter_by(product_id="p1").count() == 2  # baseline + this run
    session.close()


def test_persist_snapshot_skips_unknown_product(qt_app, tmp_path):
    engine = init_db(tmp_path / "t.db")
    _seed(engine)
    worker = _worker(engine)
    session = get_session(engine)

    changed = worker._persist_snapshot(
        session, crawl_run_id=None,
        snapshot=StockSnapshotData("UNKNOWN", supplier_status="sold_out", supply_price=1),
    )
    session.commit()

    assert changed == 0
    assert session.query(StockChange).count() == 0
    session.close()
