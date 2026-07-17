import math
import re
from datetime import datetime
from typing import Any

import pandas as pd
from utils.standard_product_schema import build_option_display_name, derive_option_price_delta


REQUIRED_WHOLESALE_FIELDS = [
    "wholesale_status",
    "wholesale_product_id",
    "product_code",
    "original_name",
    "price_wholesale_raw",
    "origin",
    "image_list_1",
    "image_detail",
]

MAPPABLE_WHOLESALE_FIELDS = [
    *REQUIRED_WHOLESALE_FIELDS,
    "option_values_raw",
    "option_price_deltas_raw",
    "option_skus_raw",
    "option_image_urls_raw",
    "price_retail",
    "price_min_selling",
    "image_list_2",
    "image_list_3",
    "image_list_4",
    "image_list_5",
    "wholesale_registered_at",
    "price_wholesale",
    "options",
    "images_list",
]

MAX_REGEX_LENGTH = 300
MAX_REGEX_INPUT_LENGTH = 5_000

IMAGE_FIELD_KEYS = [
    "image_list_1",
    "image_list_2",
    "image_list_3",
    "image_list_4",
    "image_list_5",
]

FIELD_FALLBACKS = {
    "wholesale_status": ["상태", "품절상태", "품절여부", "판매상태"],
    "wholesale_product_id": ["제품번호", "제품ID", "상품ID"],
    "product_code": ["상품코드", "도매코드", "자체상품코드", "코드"],
    "original_name": ["상품명", "원본상품명", "제품명"],
    "option_values_raw": ["옵션값", "옵션", "선택사항", "옵션명"],
    "option_image_urls_raw": ["옵션이미지", "옵션 이미지", "옵션별이미지", "옵션별 이미지"],
    "price_wholesale_raw": ["가격", "공급가", "도매가", "공급가격", "도매가격"],
    "price_retail": ["소비자가", "소매가", "소매가격"],
    "price_min_selling": ["판매준수가", "최소판매가", "최저가"],
    "origin": ["원산지", "제조국", "제조국가"],
    "image_list_1": ["목록이미지1", "대표이미지", "이미지", "상품이미지"],
    "image_list_2": ["목록이미지2"],
    "image_list_3": ["목록이미지3"],
    "image_list_4": ["목록이미지4"],
    "image_list_5": ["목록이미지5"],
    "image_detail": ["상세이미지", "상세설명이미지"],
    "wholesale_registered_at": ["등록일", "상품등록일"],
}

LEGACY_FIELD_ALIASES = {
    "price_wholesale_raw": ["price_wholesale"],
    "option_values_raw": ["options"],
    "image_list_1": ["images_list"],
}


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() == ""


def clean_text(value: Any) -> str | None:
    if is_blank(value):
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    return str(value).strip()


def resolve_field_header(field_name: str, mapping: dict[str, Any], columns: list[str]) -> str | None:
    candidate_headers: list[str] = []

    mapped_value = mapping.get(field_name)
    mapped_header = mapped_value.get("source") if isinstance(mapped_value, dict) else mapped_value
    if isinstance(mapped_header, str) and mapped_header:
        candidate_headers.append(mapped_header)
    if isinstance(mapped_value, dict) and "default" in mapped_value and not mapped_header:
        return None

    if not mapped_header:
        for legacy_field in LEGACY_FIELD_ALIASES.get(field_name, []):
            legacy_value = mapping.get(legacy_field)
            legacy_header = legacy_value.get("source") if isinstance(legacy_value, dict) else legacy_value
            if isinstance(legacy_header, str) and legacy_header:
                candidate_headers.append(legacy_header)

    candidate_headers.extend(FIELD_FALLBACKS.get(field_name, []))

    for header in candidate_headers:
        if header in columns:
            return header

    return None


def validate_required_mappings(mapping: dict[str, Any], columns: list[str]) -> list[str]:
    missing: list[str] = []
    for field_name in REQUIRED_WHOLESALE_FIELDS:
        rule = mapping.get(field_name)
        has_default = isinstance(rule, dict) and not is_blank(rule.get("default"))
        if not has_default and not resolve_field_header(field_name, mapping, columns):
            missing.append(field_name)
    return missing


def sanitize_column_mapping(
    mapping: Any,
    columns: list[str],
) -> tuple[dict[str, str | dict[str, Any]], list[str]]:
    """Keep only deterministic, bounded mapping rules that the parser understands."""
    sanitized: dict[str, str | dict[str, Any]] = {}
    warnings: list[str] = []
    if not isinstance(mapping, dict):
        return {}, ["column_mapping must be an object."]

    for field_name, raw_rule in mapping.items():
        if field_name not in MAPPABLE_WHOLESALE_FIELDS:
            warnings.append(f"Ignored unknown target field: {field_name}")
            continue
        if isinstance(raw_rule, str):
            if raw_rule in columns:
                sanitized[field_name] = raw_rule
            else:
                warnings.append(f"Ignored missing source header for {field_name}: {raw_rule}")
            continue
        if not isinstance(raw_rule, dict):
            warnings.append(f"Ignored invalid rule for {field_name}.")
            continue

        rule: dict[str, Any] = {}
        source = raw_rule.get("source")
        if isinstance(source, str) and source in columns:
            rule["source"] = source
        elif source:
            warnings.append(f"Ignored missing source header for {field_name}: {source}")

        default = raw_rule.get("default")
        if default is not None and isinstance(default, (str, int, float, bool)):
            rule["default"] = str(default)[:2_000]

        pattern = raw_rule.get("pattern")
        compiled = None
        invalid_pattern = False
        if pattern is not None:
            unsafe_pattern = isinstance(pattern, str) and (
                re.search(r"\\[1-9]", pattern)
                or "(?<=" in pattern
                or "(?<!" in pattern
                or re.search(r"\([^)]*[+*][^)]*\)[+*{]", pattern)
            )
            if not isinstance(pattern, str) or len(pattern) > MAX_REGEX_LENGTH or unsafe_pattern:
                warnings.append(f"Ignored invalid or oversized regex for {field_name}.")
                invalid_pattern = True
            else:
                try:
                    compiled = re.compile(pattern)
                except re.error:
                    warnings.append(f"Ignored invalid regex for {field_name}.")
                    invalid_pattern = True
                else:
                    rule["pattern"] = pattern

        if invalid_pattern:
            continue

        regex_group = raw_rule.get("regex_group")
        if compiled is not None and regex_group is not None:
            valid_group = (
                isinstance(regex_group, int)
                and not isinstance(regex_group, bool)
                and 0 <= regex_group <= compiled.groups
            ) or (
                isinstance(regex_group, str) and regex_group in compiled.groupindex
            )
            if valid_group:
                rule["regex_group"] = regex_group
            else:
                warnings.append(f"Ignored invalid regex_group for {field_name}.")
                continue

        if compiled is not None and isinstance(raw_rule.get("regex_all"), bool):
            rule["regex_all"] = raw_rule["regex_all"]

        join_with = raw_rule.get("join_with")
        if isinstance(join_with, str):
            rule["join_with"] = join_with[:20]

        value_map = raw_rule.get("value_map")
        if isinstance(value_map, dict) and len(value_map) <= 100:
            rule["value_map"] = {
                str(key)[:500]: str(value)[:2_000]
                for key, value in value_map.items()
                if isinstance(value, (str, int, float, bool))
            }
        elif value_map is not None:
            warnings.append(f"Ignored invalid value_map for {field_name}.")

        if "source" in rule or "default" in rule:
            sanitized[field_name] = rule
        else:
            warnings.append(f"Ignored rule without a valid source or default for {field_name}.")

    return sanitized, warnings


def apply_mapping_rule(value: Any, rule: dict[str, Any]) -> Any:
    if is_blank(value):
        value = rule.get("default")
    if is_blank(value):
        return None

    text = clean_text(value) or ""
    pattern = rule.get("pattern")
    if pattern:
        text = text[:MAX_REGEX_INPUT_LENGTH]
        compiled = re.compile(pattern)
        group = rule.get("regex_group", 1 if compiled.groups else 0)
        if rule.get("regex_all"):
            matches = []
            for match in compiled.finditer(text):
                try:
                    matched = match.group(group)
                except (IndexError, KeyError):
                    matched = None
                if matched is not None:
                    matches.append(str(matched).strip())
            text = rule.get("join_with", ",").join(item for item in matches if item)
        else:
            match = compiled.search(text)
            if match is None:
                text = ""
            else:
                try:
                    text = match.group(group) or ""
                except (IndexError, KeyError):
                    text = ""

    value_map = rule.get("value_map")
    if isinstance(value_map, dict):
        text = value_map.get(text, text)
    return None if is_blank(text) else text


def get_mapped_value(
    row: pd.Series,
    mapping: dict[str, Any],
    field_name: str,
    fallbacks: list[str] | None = None,
) -> Any:
    rule = mapping.get(field_name)
    if rule is None:
        for legacy_field in LEGACY_FIELD_ALIASES.get(field_name, []):
            if legacy_field in mapping:
                rule = mapping[legacy_field]
                break

    header = resolve_field_header(
        field_name,
        mapping,
        list(row.index),
    )
    if not header and fallbacks:
        for fallback in fallbacks:
            if fallback in row.index:
                header = fallback
                break

    value = row[header] if header and header in row.index else None
    if isinstance(rule, dict):
        return apply_mapping_rule(value, rule)
    if not is_blank(value):
        return value

    return None


def parse_int_price(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None

    if re.search(r"\d[^/]*\/[^/]*\d", text):
        return None

    normalized = re.sub(r"[^0-9.]", "", text)
    if not normalized:
        return None

    try:
        parsed = int(float(normalized))
    except ValueError:
        return None
    if parsed > 2_147_483_647:
        return None
    return parsed


def parse_signed_int(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    match = re.search(r"[+-]?\s*[\d,]+", text)
    if not match:
        return None
    try:
        return int(match.group().replace(" ", "").replace(",", ""))
    except ValueError:
        return None


def split_csv_text(value: Any) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    return [token.strip() for token in text.split(",") if token.strip()]


def split_option_price_text(value: Any) -> list[str]:
    text = clean_text(value)
    if not text:
        return []

    tokens: list[str] = []
    start = 0
    for index, character in enumerate(text):
        if character != ",":
            continue

        left_digits = re.search(r"(\d+)$", text[start:index].strip())
        right_digits = re.match(r"\s*(\d{3})(?!\d)", text[index + 1 :])
        if left_digits and 1 <= len(left_digits.group(1)) <= 3 and right_digits:
            continue

        token = text[start:index].strip()
        if token:
            tokens.append(token)
        start = index + 1

    last_token = text[start:].strip()
    if last_token:
        tokens.append(last_token)
    return tokens


def parse_option_variants(
    option_values_raw: Any,
    price_wholesale_raw: Any,
    option_price_deltas_raw: Any = None,
) -> dict[str, Any]:
    option_names = split_csv_text(option_values_raw)
    representative_price = parse_int_price(price_wholesale_raw)
    delta_tokens = split_csv_text(option_price_deltas_raw) if option_names else []
    if delta_tokens:
        parsed_deltas = [parse_signed_int(token) for token in delta_tokens]
        parsed_prices = [
            representative_price + delta if representative_price is not None and delta is not None else None
            for delta in parsed_deltas
        ]
        price_tokens = delta_tokens
    else:
        price_tokens = split_option_price_text(price_wholesale_raw) if option_names else []
        simple_price_tokens = split_csv_text(price_wholesale_raw) if option_names else []
        if len(price_tokens) != len(option_names) and len(simple_price_tokens) == len(option_names):
            price_tokens = simple_price_tokens
        parsed_prices = [parse_int_price(token) for token in price_tokens]
        if len(parsed_prices) == 1 and len(option_names) > 1 and parsed_prices[0] is not None:
            parsed_prices *= len(option_names)
            price_tokens *= len(option_names)
        if parsed_prices:
            representative_price = parsed_prices[0]
    warnings: list[dict[str, Any]] = []

    if not option_names:
        if not is_blank(price_wholesale_raw) and representative_price is None:
            warnings.append(
                {
                    "field": "price_wholesale_raw",
                    "message": "One or more option prices could not be parsed.",
                    "raw_value": clean_text(price_wholesale_raw) or "",
                }
            )
        return {
            "price_wholesale": representative_price,
            "option_variants": [],
            "warnings": warnings,
        }

    if option_names and len(option_names) != len(price_tokens):
        warnings.append(
            {
                "field": "option_variants",
                "message": "Option count and price count differ.",
                "option_count": len(option_names),
                "price_count": len(price_tokens),
            }
        )
        return {
            "price_wholesale": representative_price,
            "option_variants": [],
            "warnings": warnings,
        }

    if any(price is None for price in parsed_prices):
        warnings.append(
            {
                "field": "price_wholesale_raw",
                "message": "One or more option prices could not be parsed.",
                "raw_value": clean_text(price_wholesale_raw) or "",
            }
        )
        return {
            "price_wholesale": representative_price,
            "option_variants": [],
            "warnings": warnings,
        }

    option_variants = [
        {
            "name": option_name,
            "price_wholesale": parsed_prices[index],
            "position": index + 1,
        }
        for index, option_name in enumerate(option_names)
    ]

    return {
        "price_wholesale": representative_price,
        "option_variants": option_variants,
        "warnings": warnings,
    }


def build_standard_options(
    *,
    product_code: Any,
    wholesale_status: Any,
    option_values_raw: Any,
    price_wholesale_raw: Any,
    option_image_urls_raw: Any,
    base_supply_price: int | None,
    option_variants: list[dict[str, Any]] | None = None,
    option_skus_raw: Any = None,
    option_price_deltas_raw: Any = None,
) -> list[dict[str, Any]]:
    option_names = split_csv_text(option_values_raw)
    if not option_names:
        return []

    option_price_values = [item.get("price_wholesale") for item in (option_variants or [])]
    if not option_price_values:
        option_price_tokens = split_option_price_text(price_wholesale_raw)
        simple_price_tokens = split_csv_text(price_wholesale_raw)
        if len(option_price_tokens) != len(option_names) and len(simple_price_tokens) == len(option_names):
            option_price_tokens = simple_price_tokens
        option_price_values = [parse_int_price(token) for token in option_price_tokens]
    option_image_urls = split_csv_text(option_image_urls_raw)
    option_skus = split_csv_text(option_skus_raw)
    product_code_text = clean_text(product_code) or ""
    status_text = clean_text(wholesale_status) or ""
    option_usable = status_text not in {"품절", "판매중지", "중지"}

    standard_options: list[dict[str, Any]] = []
    for index, option_name in enumerate(option_names):
        option_supply_price = option_price_values[index] if index < len(option_price_values) else None
        option_main_image_url = option_image_urls[index] if index < len(option_image_urls) else None
        option = {
            "option_group_1": "옵션",
            "option_value_1": option_name,
            "option_value_2": None,
            "option_value_3": None,
        }
        standard_options.append(
            {
                "supplier_product_code": product_code_text,
                "option_sku": option_skus[index] if index < len(option_skus) else f"{product_code_text}-{index + 1}",
                "option_type": "combination",
                "option_group_1": option["option_group_1"],
                "option_value_1": option["option_value_1"],
                "option_group_2": None,
                "option_value_2": option["option_value_2"],
                "option_group_3": None,
                "option_value_3": option["option_value_3"],
                "option_display_name": build_option_display_name(option),
                "option_supply_price": option_supply_price,
                "option_sale_price": None,
                "option_price_delta": derive_option_price_delta(option_supply_price, base_supply_price),
                "option_stock_quantity": None,
                "option_status": status_text or None,
                "option_main_image_url": option_main_image_url,
                "option_extra_image_urls": [],
                "option_position": index + 1,
                "option_usable": option_usable,
                "raw_option_text": option_name,
                "raw_option_metadata": {
                    "option_values_raw": clean_text(option_values_raw),
                    "price_wholesale_raw": clean_text(price_wholesale_raw),
                    "option_image_urls_raw": clean_text(option_image_urls_raw),
                    **(
                        {"option_price_deltas_raw": clean_text(option_price_deltas_raw)}
                        if not is_blank(option_price_deltas_raw)
                        else {}
                    ),
                    **(
                        {"option_skus_raw": clean_text(option_skus_raw)}
                        if not is_blank(option_skus_raw)
                        else {}
                    ),
                },
            }
        )

    return standard_options


def build_images_list(values: dict[str, Any]) -> list[str]:
    images: list[str] = []
    for key in IMAGE_FIELD_KEYS:
        image_value = clean_text(values.get(key))
        if image_value:
            images.append(image_value)
    return images


def json_safe_row(row: pd.Series) -> dict[str, Any]:
    raw_row_data = row.to_dict()
    for key, value in list(raw_row_data.items()):
        if is_blank(value):
            raw_row_data[key] = ""
        elif isinstance(value, (datetime, pd.Timestamp)):
            raw_row_data[key] = value.isoformat()
    return raw_row_data


def coerce_warning_list(value: Any) -> list[Any]:
    if not value:
        return []
    if isinstance(value, list):
        return value
    return [value]


def merge_product_warnings(existing_warnings: Any, processing_warnings: Any) -> dict[str, Any] | None:
    supplier_warnings: list[Any] = []
    existing_processing_warnings: list[Any] = []

    if isinstance(existing_warnings, dict):
        supplier_warnings = coerce_warning_list(
            existing_warnings.get("supplier_warnings") or existing_warnings.get("warnings")
        )
        existing_processing_warnings = coerce_warning_list(existing_warnings.get("processing_warnings"))
    else:
        supplier_warnings = coerce_warning_list(existing_warnings)

    all_processing_warnings = existing_processing_warnings + coerce_warning_list(processing_warnings)
    all_warnings = supplier_warnings + all_processing_warnings

    if not all_warnings:
        return None

    merged = {"warnings": all_warnings}
    if supplier_warnings:
        merged["supplier_warnings"] = supplier_warnings
    if all_processing_warnings:
        merged["processing_warnings"] = all_processing_warnings
    return merged


def parse_wholesale_row(row: pd.Series, mapping: dict[str, Any]) -> dict[str, Any]:
    mapped_values = {
        "wholesale_status": get_mapped_value(row, mapping, "wholesale_status"),
        "wholesale_product_id": get_mapped_value(row, mapping, "wholesale_product_id"),
        "product_code": get_mapped_value(row, mapping, "product_code"),
        "original_name": get_mapped_value(row, mapping, "original_name"),
        "option_values_raw": get_mapped_value(row, mapping, "option_values_raw"),
        "option_price_deltas_raw": get_mapped_value(row, mapping, "option_price_deltas_raw"),
        "option_skus_raw": get_mapped_value(row, mapping, "option_skus_raw"),
        "option_image_urls_raw": get_mapped_value(row, mapping, "option_image_urls_raw"),
        "price_wholesale_raw": get_mapped_value(row, mapping, "price_wholesale_raw"),
        "price_retail": get_mapped_value(row, mapping, "price_retail"),
        "price_min_selling": get_mapped_value(row, mapping, "price_min_selling"),
        "origin": get_mapped_value(row, mapping, "origin"),
        "image_list_1": get_mapped_value(row, mapping, "image_list_1"),
        "image_list_2": get_mapped_value(row, mapping, "image_list_2"),
        "image_list_3": get_mapped_value(row, mapping, "image_list_3"),
        "image_list_4": get_mapped_value(row, mapping, "image_list_4"),
        "image_list_5": get_mapped_value(row, mapping, "image_list_5"),
        "image_detail": get_mapped_value(row, mapping, "image_detail"),
        "wholesale_registered_at": get_mapped_value(row, mapping, "wholesale_registered_at"),
    }
    option_result = parse_option_variants(
        mapped_values["option_values_raw"],
        mapped_values["price_wholesale_raw"],
        mapped_values["option_price_deltas_raw"],
    )
    warnings = list(option_result["warnings"])
    standard_options = (
        []
        if option_result["warnings"]
        else build_standard_options(
            product_code=mapped_values["product_code"],
            wholesale_status=mapped_values["wholesale_status"],
            option_values_raw=mapped_values["option_values_raw"],
            price_wholesale_raw=mapped_values["price_wholesale_raw"],
            option_image_urls_raw=mapped_values["option_image_urls_raw"],
            base_supply_price=option_result["price_wholesale"],
            option_variants=option_result["option_variants"],
            option_skus_raw=mapped_values["option_skus_raw"],
            option_price_deltas_raw=mapped_values["option_price_deltas_raw"],
        )
    )

    for required_field in REQUIRED_WHOLESALE_FIELDS:
        if is_blank(mapped_values.get(required_field)):
            warnings.append(
                {
                    "field": required_field,
                    "message": "Required value is blank.",
                }
            )

    product_data = {
        "wholesale_status": clean_text(mapped_values["wholesale_status"]),
        "wholesale_product_id": clean_text(mapped_values["wholesale_product_id"]),
        "product_code": clean_text(mapped_values["product_code"]),
        "original_name": clean_text(mapped_values["original_name"]) or "",
        "option_values_raw": clean_text(mapped_values["option_values_raw"]),
        "price_wholesale_raw": clean_text(mapped_values["price_wholesale_raw"]),
        "price_wholesale": option_result["price_wholesale"],
        "option_variants": option_result["option_variants"],
        "standard_options": standard_options,
        "price_retail": parse_int_price(mapped_values["price_retail"]),
        "price_min_selling": parse_int_price(mapped_values["price_min_selling"]),
        "origin": clean_text(mapped_values["origin"]),
        "images_list": build_images_list(mapped_values),
        "image_detail": clean_text(mapped_values["image_detail"]),
        "wholesale_registered_at": clean_text(mapped_values["wholesale_registered_at"]),
        "raw_metadata": json_safe_row(row),
    }

    return {
        "product_data": product_data,
        "warnings": warnings,
    }


STANDARD_PRODUCT_EXAMPLE = {
    "wholesale_status": "판매중",
    "wholesale_product_id": "1000000001",
    "product_code": "SUPPLIER-001",
    "original_name": "예시 상품명",
    "option_values_raw": "검정,흰색",
    "price_wholesale_raw": "10000",
    "price_wholesale": 10000,
    "option_variants": [
        {"name": "검정", "price_wholesale": 10000, "position": 1},
        {"name": "흰색", "price_wholesale": 11000, "position": 2},
    ],
    "price_retail": None,
    "price_min_selling": None,
    "origin": "국내",
    "images_list": ["https://example.com/product.jpg"],
    "image_detail": "https://example.com/detail.jpg",
    "wholesale_registered_at": None,
}


def build_mapping_preview(
    dataframe: pd.DataFrame,
    mapping: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    preview: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for row_number, (_, row) in enumerate(dataframe.head(5).iterrows(), start=1):
        parsed = parse_wholesale_row(row, mapping)
        product_data = dict(parsed["product_data"])
        product_data.pop("raw_metadata", None)
        preview.append(product_data)
        warnings.extend({"row": row_number, **warning} for warning in parsed["warnings"])
    return preview, warnings
