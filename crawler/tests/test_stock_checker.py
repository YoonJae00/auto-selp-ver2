from __future__ import annotations

from app.monitor.stock_checker import ChangeRecord, detect_changes


def test_no_change_returns_empty() -> None:
    previous = {"supplier_status": "available", "supply_price": 10000, "option_stock_json": {"SKU-1": 5}}
    new = {"supplier_status": "available", "supply_price": 10000, "option_stock_json": {"SKU-1": 5}}
    assert detect_changes(previous, new) == []


def test_sold_out_detected() -> None:
    previous = {"supplier_status": "available", "supply_price": 10000, "option_stock_json": {}}
    new = {"supplier_status": "sold_out", "supply_price": 10000, "option_stock_json": {}}
    changes = detect_changes(previous, new)
    assert len(changes) == 1
    assert changes[0].change_type == "sold_out"
    assert changes[0].previous_value == "available"
    assert changes[0].new_value == "sold_out"


def test_restocked_detected() -> None:
    previous = {"supplier_status": "sold_out", "supply_price": 10000, "option_stock_json": {}}
    new = {"supplier_status": "available", "supply_price": 10000, "option_stock_json": {}}
    changes = detect_changes(previous, new)
    assert len(changes) == 1
    assert changes[0].change_type == "restocked"


def test_price_changed_detected() -> None:
    previous = {"supplier_status": "available", "supply_price": 10000, "option_stock_json": {}}
    new = {"supplier_status": "available", "supply_price": 12000, "option_stock_json": {}}
    changes = detect_changes(previous, new)
    assert len(changes) == 1
    assert changes[0].change_type == "price_changed"
    assert changes[0].previous_value == "10000"
    assert changes[0].new_value == "12000"


def test_stock_changed_detected() -> None:
    previous = {"supplier_status": "available", "supply_price": 10000, "option_stock_json": {"SKU-1": 5, "SKU-2": 3}}
    new = {"supplier_status": "available", "supply_price": 10000, "option_stock_json": {"SKU-1": 0, "SKU-2": 3}}
    changes = detect_changes(previous, new)
    assert len(changes) == 1
    assert changes[0].change_type == "stock_changed"
    assert changes[0].option_sku == "SKU-1"
    assert changes[0].previous_value == "5"
    assert changes[0].new_value == "0"


def test_first_snapshot_returns_empty() -> None:
    new = {"supplier_status": "available", "supply_price": 10000, "option_stock_json": {}}
    assert detect_changes(None, new) == []


def test_multiple_changes() -> None:
    previous = {"supplier_status": "available", "supply_price": 10000, "option_stock_json": {"SKU-1": 5}}
    new = {"supplier_status": "sold_out", "supply_price": 12000, "option_stock_json": {"SKU-1": 0}}
    changes = detect_changes(previous, new)
    types = [c.change_type for c in changes]
    assert "sold_out" in types
    assert "price_changed" in types
    assert "stock_changed" in types
