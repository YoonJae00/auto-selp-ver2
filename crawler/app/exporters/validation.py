from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Product, ProductOption


@dataclass(frozen=True)
class ExportScopeValidation:
    product_count: int
    option_count: int
    blocking_count: int
    warning_count: int
    fingerprint: str
    issues: list[dict[str, str]]


def validate_export_scope(session: Session, supplier_id: str, *, issue_limit: int = 50) -> ExportScopeValidation:
    scope = Product.supplier_id == supplier_id
    error_fields = (
        or_(Product.raw_product_name.is_(None), Product.raw_product_name == ""),
        or_(Product.supplier_product_code.is_(None), Product.supplier_product_code == ""),
        or_(Product.supplier_status.is_(None), Product.supplier_status == ""),
    )
    warning_fields = (
        or_(Product.origin.is_(None), Product.origin == ""),
        Product.supply_price.is_(None),
        or_(Product.main_image_url.is_(None), Product.main_image_url == ""),
    )
    aggregates = session.execute(select(
        func.count(Product.id),
        *[func.coalesce(func.sum(case((condition, 1), else_=0)), 0) for condition in (*error_fields, *warning_fields)],
        func.max(Product.last_seen_at),
    ).where(scope)).one()
    product_count = int(aggregates[0] or 0)
    field_counts = [int(value or 0) for value in aggregates[1:7]]
    blocking_count = sum(field_counts[:3])
    warning_count = sum(field_counts[3:])
    option_count = int(session.scalar(select(func.count(ProductOption.id)).join(Product).where(scope)) or 0)
    fingerprint_source = (supplier_id, product_count, option_count, *field_counts, str(aggregates[7] or ""))
    fingerprint = sha256(repr(fingerprint_source).encode("utf-8")).hexdigest()

    if product_count == 0:
        return ExportScopeValidation(0, option_count, 1, 0, fingerprint, [{
            "severity": "error", "code": "empty_scope", "message": "내보낼 상품이 없습니다.",
            "productId": "", "productCode": "",
        }])

    candidates = list(session.scalars(select(Product).where(
        scope, or_(*error_fields, *warning_fields),
    ).order_by(Product.supplier_product_code, Product.id).limit(issue_limit + 1)))
    issues: list[dict[str, str]] = []
    for product in candidates:
        common = {"productId": product.id, "productCode": product.supplier_product_code or ""}
        for field, value, severity, label in (
            ("raw_product_name", product.raw_product_name, "error", "상품명"),
            ("supplier_product_code", product.supplier_product_code, "error", "상품 코드"),
            ("supplier_status", product.supplier_status, "error", "상품 상태"),
            ("origin", product.origin, "warning", "원산지"),
            ("supply_price", product.supply_price, "warning", "공급가"),
            ("main_image_url", product.main_image_url, "warning", "대표 이미지"),
        ):
            if value is None or value == "":
                issues.append({**common, "severity": severity, "code": f"missing_{field}", "message": f"{label}이(가) 없습니다."})
    issues.sort(key=lambda row: (row["severity"] != "error", row["productCode"], row["code"]))
    displayed = issues[:issue_limit]
    if blocking_count + warning_count > len(displayed):
        hidden_errors = blocking_count > sum(row["severity"] == "error" for row in displayed)
        displayed.append({
            "severity": "error" if hidden_errors else "warning", "code": "more_issues",
            "message": f"추가 검증 항목 {blocking_count + warning_count - len(displayed)}건이 있습니다.",
            "productId": "", "productCode": "",
        })
    return ExportScopeValidation(product_count, option_count, blocking_count, warning_count, fingerprint, displayed)
