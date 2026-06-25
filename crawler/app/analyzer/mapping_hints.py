from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


ALLOWED_HINT_PATHS = {
    "adapter.product.raw_product_name",
    "adapter.product.supplier_product_code",
    "adapter.product.supplier_product_id",
    "adapter.product.supply_price",
    "adapter.product.origin",
    "adapter.product.main_image_url",
    "adapter.product.detail_content",
    "adapter.product.supplier_status",
    "adapter.listing.product_link",
    "adapter.categories.all_products.url",
}

PRODUCT_DEFAULTS: dict[str, dict[str, Any]] = {
    "supply_price": {"transform": "extract_number"},
    "main_image_url": {"attribute": "src", "fallback_attribute": "data-src"},
    "detail_content": {"html": True},
}
LISTING_PRODUCT_LINK_DEFAULTS = {"attribute": "href"}
ALL_PRODUCTS_URL_DEFAULTS = {"available": True}


@dataclass
class MappingHint:
    page_kind: str
    field_path: str
    chosen_selector: str
    url: str = ""
    selector_candidates: list[str] = field(default_factory=list)
    attribute: str | None = None
    html: bool | None = None
    multiple: bool | None = None
    transform: str | None = None
    fallback: str | None = None
    fallback_from: str | None = None
    observed_value: str = ""
    locked: bool = True

    def __post_init__(self) -> None:
        if self.field_path not in ALLOWED_HINT_PATHS:
            raise ValueError(f"Disallowed mapping hint field_path: {self.field_path}")
        if not str(self.chosen_selector).strip():
            raise ValueError("Mapping hint chosen_selector must not be empty")
        self.chosen_selector = str(self.chosen_selector).strip()


def _clean_text(value: Any, limit: int = 300) -> str:
    text = "" if value is None else str(value)
    text = text.replace("```", " ").replace("`", " ")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    text = re.sub(r"<[^>]{0,200}>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def format_mapping_hints_for_prompt(hints: list[MappingHint] | None) -> str:
    if not hints:
        return ""
    lines = ["## 사용자 수동 매핑 힌트", "아래 힌트는 사용자가 확인한 선택자입니다. 잠금 힌트는 생성 후 결정적으로 병합됩니다."]
    for idx, hint in enumerate(hints, 1):
        lines.extend([
            f"- hint {idx}:",
            f"  field_path: {_clean_text(hint.field_path, 120)}",
            f"  page_kind: {_clean_text(hint.page_kind, 40)}",
            f"  selector: {_clean_text(hint.chosen_selector, 220)}",
            f"  locked: {bool(hint.locked)}",
        ])
        if hint.attribute:
            lines.append(f"  attribute: {_clean_text(hint.attribute, 60)}")
        if hint.html is not None:
            lines.append(f"  html: {bool(hint.html)}")
        if hint.multiple is not None:
            lines.append(f"  multiple: {bool(hint.multiple)}")
        if hint.transform:
            lines.append(f"  transform: {_clean_text(hint.transform, 60)}")
        if hint.fallback_from:
            lines.append(f"  fallback_from: {_clean_text(hint.fallback_from, 60)}")
        if hint.url:
            lines.append(f"  url: {_clean_text(hint.url, 200)}")
        if hint.observed_value:
            lines.append(f"  observed_value: {_clean_text(hint.observed_value, 300)}")
    return "\n".join(lines)


def _hint_fields(hint: MappingHint) -> dict[str, Any]:
    data: dict[str, Any] = {"selector": hint.chosen_selector}
    for key in ("attribute", "html", "multiple", "transform", "fallback", "fallback_from"):
        value = getattr(hint, key)
        if value is not None and value != "":
            data[key] = value
    return data


def apply_locked_hints_to_yaml_dict(data: dict[str, Any], hints: list[MappingHint] | None) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("YAML data must be a dict")
    adapter = data.setdefault("adapter", {})
    if not isinstance(adapter, dict):
        raise ValueError("adapter must be a dict")

    for hint in hints or []:
        if hint.field_path not in ALLOWED_HINT_PATHS:
            raise ValueError(f"Disallowed mapping hint field_path: {hint.field_path}")
        if not hint.locked:
            continue
        fields = _hint_fields(hint)
        if hint.field_path.startswith("adapter.product."):
            name = hint.field_path.rsplit(".", 1)[-1]
            product = adapter.setdefault("product", {})
            if not isinstance(product, dict):
                raise ValueError("adapter.product must be a dict")
            existing_raw = product.get(name)
            existing = existing_raw if isinstance(existing_raw, dict) else {}
            product[name] = {**PRODUCT_DEFAULTS.get(name, {}), **existing, **fields}
        elif hint.field_path == "adapter.listing.product_link":
            listing = adapter.setdefault("listing", {})
            if not isinstance(listing, dict):
                raise ValueError("adapter.listing must be a dict")
            existing_raw = listing.get("product_link")
            existing = existing_raw if isinstance(existing_raw, dict) else {}
            listing["product_link"] = {**LISTING_PRODUCT_LINK_DEFAULTS, **existing, **fields}
        elif hint.field_path == "adapter.categories.all_products.url":
            categories = adapter.setdefault("categories", {})
            if not isinstance(categories, dict):
                raise ValueError("adapter.categories must be a dict")
            all_products = categories.setdefault("all_products", {})
            if not isinstance(all_products, dict):
                raise ValueError("adapter.categories.all_products must be a dict")
            existing_raw = all_products
            existing = existing_raw if isinstance(existing_raw, dict) else {}
            all_products.update({**ALL_PRODUCTS_URL_DEFAULTS, **existing, "url": hint.chosen_selector})
    return data
