from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Product, ProductOption


PRODUCT_COLUMNS = [
    "supplier_name",
    "supplier_product_id",
    "supplier_product_code",
    "supplier_status",
    "supplier_category",
    "raw_product_name",
    "origin",
    "supply_price",
    "main_image_url",
    "extra_image_urls",
    "detail_content",
    "option_values",
    "option_prices",
    "brand_name",
    "manufacturer",
    "model_name",
]

OPTION_COLUMNS = [
    "supplier_product_code",
    "option_sku",
    "option_type",
    "option_group_1",
    "option_value_1",
    "option_group_2",
    "option_value_2",
    "option_group_3",
    "option_value_3",
    "option_display_name",
    "option_supply_price",
    "option_sale_price",
    "option_price_delta",
    "option_stock_quantity",
    "option_status",
    "option_usable",
    "option_main_image_url",
    "option_extra_image_urls",
    "option_position",
]


def _stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ",".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value)


def _option_csv(options: list[ProductOption]) -> tuple[str, str]:
    values: list[str] = []
    prices: list[str] = []
    for opt in options:
        value = opt.option_display_name or opt.option_value_1 or ""
        if value:
            values.append(str(value))
            prices.append("" if opt.option_supply_price is None else str(opt.option_supply_price))
    return ",".join(values), ",".join(prices)


def export_to_excel(
    session: Session,
    supplier_id: str | None,
    output_path: Path,
) -> Path:
    wb = Workbook()

    products_sheet = wb.active
    products_sheet.title = "products"
    products_sheet.append(PRODUCT_COLUMNS)

    options_sheet = wb.create_sheet("product_options")
    options_sheet.append(OPTION_COLUMNS)

    query = select(Product)
    if supplier_id:
        query = query.where(Product.supplier_id == supplier_id)
    query = query.order_by(Product.supplier_product_code)

    products = session.execute(query).scalars().all()
    option_count = 0

    for product in products:
        options = session.execute(
            select(ProductOption).where(ProductOption.product_id == product.id).order_by(ProductOption.option_position)
        ).scalars().all()
        option_values, option_prices = _option_csv(options)

        products_sheet.append([
            _stringify(product.supplier_name),
            _stringify(product.supplier_product_id),
            _stringify(product.supplier_product_code),
            _stringify(product.supplier_status),
            _stringify(product.supplier_category),
            _stringify(product.raw_product_name),
            _stringify(product.origin),
            _stringify(product.supply_price),
            _stringify(product.main_image_url),
            _stringify(product.extra_image_urls),
            _stringify(product.detail_content),
            option_values,
            option_prices,
            _stringify(product.brand_name),
            _stringify(product.manufacturer),
            _stringify(product.model_name),
        ])

        for opt in options:
            options_sheet.append([
                _stringify(opt.supplier_product_code) if hasattr(opt, "supplier_product_code") else _stringify(product.supplier_product_code),
                _stringify(opt.option_sku),
                _stringify(opt.option_type),
                _stringify(opt.option_group_1),
                _stringify(opt.option_value_1),
                _stringify(opt.option_group_2),
                _stringify(opt.option_value_2),
                _stringify(opt.option_group_3),
                _stringify(opt.option_value_3),
                _stringify(opt.option_display_name),
                _stringify(opt.option_supply_price),
                _stringify(opt.option_sale_price),
                _stringify(opt.option_price_delta),
                _stringify(opt.option_stock_quantity),
                _stringify(opt.option_status),
                _stringify(opt.option_usable),
                _stringify(opt.option_main_image_url),
                _stringify(opt.option_extra_image_urls),
                _stringify(opt.option_position),
            ])
            option_count += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return output_path
