import math
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
