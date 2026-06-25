"""
Standard product schema definitions.

Copied from services/processor/utils/standard_product_schema.py to keep the
crawler standalone. If the processor schema changes, update this file to match.
Source: services/processor/utils/standard_product_schema.py
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


REQUIRED_STANDARD_PRODUCT_FIELDS = [
    "supplier_name",
    "supplier_product_id",
    "supplier_product_code",
    "supplier_status",
    "raw_product_name",
    "origin",
    "supply_price",
    "main_image_url",
    "detail_content",
]

OPTION_TYPES = {"single", "combination", "custom", "standard"}


def clean_standard_text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)) and math.isnan(value):
            return None
    except TypeError:
        pass
    text = str(value).strip()
    return text or None


def build_option_display_name(option: dict[str, Any]) -> str:
    values = [
        clean_standard_text(option.get("option_value_1")),
        clean_standard_text(option.get("option_value_2")),
        clean_standard_text(option.get("option_value_3")),
    ]
    visible_values = [value for value in values if value]
    return " / ".join(visible_values)


def derive_option_price_delta(
    option_supply_price: int | None,
    base_supply_price: int | None,
) -> int | None:
    if option_supply_price is None or base_supply_price is None:
        return None
    return option_supply_price - base_supply_price


@dataclass
class StandardProduct:
    supplier_name: str
    supplier_product_id: str | None
    supplier_product_code: str
    supplier_status: str
    raw_product_name: str
    origin: str | None
    supply_price: int | None
    main_image_url: str | None
    detail_content: str | None
    supplier_category: str | None = None
    extra_image_urls: list[str] = field(default_factory=list)
    brand_name: str | None = None
    manufacturer: str | None = None
    model_name: str | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StandardOption:
    supplier_product_code: str
    option_sku: str | None
    option_type: str
    option_group_1: str | None
    option_value_1: str | None
    option_group_2: str | None
    option_value_2: str | None
    option_group_3: str | None
    option_value_3: str | None
    option_display_name: str
    option_supply_price: int | None
    option_sale_price: int | None
    option_price_delta: int | None
    option_stock_quantity: int | None
    option_status: str | None
    option_usable: bool
    option_main_image_url: str | None
    option_extra_image_urls: list[str]
    option_position: int
    raw_option_text: str | None
    raw_option_metadata: dict[str, Any]
