from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ChangeRecord:
    change_type: str
    previous_value: str | None
    new_value: str | None
    option_sku: str | None = None


def detect_changes(
    previous: dict[str, Any] | None,
    new: dict[str, Any],
) -> list[ChangeRecord]:
    if previous is None:
        return []

    changes: list[ChangeRecord] = []

    prev_status = previous.get("supplier_status")
    new_status = new.get("supplier_status")
    if prev_status != new_status:
        if prev_status == "available" and new_status == "sold_out":
            changes.append(ChangeRecord("sold_out", prev_status, new_status))
        elif prev_status == "sold_out" and new_status == "available":
            changes.append(ChangeRecord("restocked", prev_status, new_status))
        elif prev_status and new_status:
            changes.append(ChangeRecord("status_changed", prev_status, new_status))

    prev_price = previous.get("supply_price")
    new_price = new.get("supply_price")
    if prev_price != new_price:
        changes.append(ChangeRecord("price_changed", str(prev_price) if prev_price is not None else None, str(new_price) if new_price is not None else None))

    prev_stock = previous.get("option_stock_json") or {}
    new_stock = new.get("option_stock_json") or {}
    all_skus = set(prev_stock.keys()) | set(new_stock.keys())
    for sku in all_skus:
        prev_qty = prev_stock.get(sku)
        new_qty = new_stock.get(sku)
        if prev_qty != new_qty:
            changes.append(ChangeRecord(
                "stock_changed",
                str(prev_qty) if prev_qty is not None else None,
                str(new_qty) if new_qty is not None else None,
                option_sku=sku,
            ))

    return changes
