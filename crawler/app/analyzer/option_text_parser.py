from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ParsedOptionText:
    value: str | None
    price_delta: int | None = None
    supply_price: int | None = None


def is_option_placeholder(text: str | None) -> bool:
    cleaned = re.sub(r"[\s\-\[\]\(\)<>]+", "", text or "").casefold()
    if not cleaned:
        return True
    return "선택" in cleaned and any(token in cleaned for token in ("필수", "옵션", "선택해주세요", "선택해 주세요"))


def _int_amount(value: str | None, sign: str | None = None) -> int | None:
    if not value:
        return None
    text = value.strip()
    own_sign = -1 if text.startswith("-") else 1
    if sign and sign.strip() == "-":
        own_sign = -1
    cleaned = re.sub(r"[^\d]", "", text)
    return own_sign * int(cleaned) if cleaned else None


def _parser_value(parser: Any, key: str, default: Any = None) -> Any:
    if parser is None:
        return default
    if isinstance(parser, dict):
        return parser.get(key, default)
    return getattr(parser, key, default)


def _legacy_split_option_text_price(text: str | None) -> tuple[str | None, int | None]:
    if not text:
        return None, None
    cleaned = re.sub(r"\s+", " ", text).strip()
    for pattern in (
        r"\s*[\(\[]\s*(?P<sign>[+-])\s*(?P<amount>[\d,]+)\s*원?\s*[\)\]]\s*$",
        r"\s*(?:[/|:]\s*)?(?P<sign>[+-])\s*(?P<amount>[\d,]+)\s*원?\s*$",
    ):
        match = re.search(pattern, cleaned)
        if not match:
            continue
        name = cleaned[:match.start()].strip()
        if not name:
            return cleaned, None
        return name, _int_amount(match.group("amount"), match.group("sign"))
    return cleaned or None, None


def parse_option_text(
    text: str | None,
    parser: Any = None,
    base_price: int | None = None,
    *,
    use_legacy: bool = True,
) -> ParsedOptionText:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned or is_option_placeholder(cleaned):
        return ParsedOptionText(None)

    if (
        _parser_value(parser, "enabled", False)
        and _parser_value(parser, "confidence", "low") != "low"
        and _parser_value(parser, "pattern")
    ):
        try:
            match = re.search(str(_parser_value(parser, "pattern")), cleaned)
        except re.error:
            match = None
        if match:
            groups = match.groupdict()
            value = re.sub(r"\s+", " ", groups.get("value") or "").strip() or None
            price = _int_amount(groups.get("price"), groups.get("sign"))
            if value and price is not None:
                if _parser_value(parser, "price_kind") == "supply":
                    delta = price - base_price if base_price is not None else None
                    return ParsedOptionText(value, delta, price)
                supply = base_price + price if base_price is not None else None
                return ParsedOptionText(value, price, supply)

    if not use_legacy:
        return ParsedOptionText(cleaned)
    value, delta = _legacy_split_option_text_price(cleaned)
    supply = base_price + delta if base_price is not None and delta is not None else None
    return ParsedOptionText(value, delta, supply)
