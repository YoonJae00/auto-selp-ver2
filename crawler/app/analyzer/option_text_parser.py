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
    if "선택" not in cleaned:
        return False
    # bare '선택'(단일 안내행)도 placeholder로 처리
    return cleaned == "선택" or any(token in cleaned for token in ("필수", "옵션", "하세요", "주세요", "바랍니다"))


def format_option_group(parsed_list: "list[ParsedOptionText]") -> str | None:
    """병합 표시용: '3개 · S, M, L / +0원, +10,000원, +20,000원'.
    값 묶음 / 가격 묶음 — 엑셀의 옵션값 열·옵션가격 열 구조와 동일. 개수 항상 일치."""
    values: list[str] = []
    prices: list[str] = []
    for parsed in parsed_list:
        if not parsed.value:
            continue
        values.append(parsed.value)
        amount = parsed.price_delta if parsed.price_delta is not None else parsed.supply_price
        prices.append(f"{amount:+,}원" if amount is not None else "-")
    if not values:
        return None
    return f"{len(values)}개 · {', '.join(values)} / {', '.join(prices)}"


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

    parser_enabled = bool(
        _parser_value(parser, "enabled", False)
        and _parser_value(parser, "confidence", "low") != "low"
        and _parser_value(parser, "pattern")
    )
    if parser_enabled:
        try:
            match = re.search(str(_parser_value(parser, "pattern")), cleaned)
        except re.error:
            match = None
        if match:
            groups = match.groupdict()
            value = re.sub(r"\s+", " ", groups.get("value") or "").strip() or None
            price = _int_amount(groups.get("price"), groups.get("sign"))
            if value:
                if price is None:
                    # 기본 옵션 등 가격 토큰 없음 → +0원 (값이 있으면 항상 delta 존재 → 개수 일치)
                    return ParsedOptionText(value, 0, base_price)
                if _parser_value(parser, "price_kind") == "supply":
                    delta = price - base_price if base_price is not None else None
                    return ParsedOptionText(value, delta, price)
                supply = base_price + price if base_price is not None else None
                return ParsedOptionText(value, price, supply)

    if not use_legacy:
        return ParsedOptionText(cleaned)
    value, delta = _legacy_split_option_text_price(cleaned)
    if parser_enabled and value and delta is None:
        delta = 0  # 파서 활성 상태: 값이 있으면 가격 없어도 +0원으로
    supply = base_price + delta if base_price is not None and delta is not None else None
    return ParsedOptionText(value, delta, supply)


if __name__ == "__main__":
    # 형식이 하드코딩이 아님을 보이기 위해 몰마다 '다른' AI 정규식으로 같은 로직 검증.
    def check(pattern, raw, expect_summary, expect_delta):
        parser = {"enabled": True, "confidence": "high", "price_kind": "delta", "pattern": pattern}
        parsed = [parse_option_text(t, parser) for t in raw]
        summary = format_option_group(parsed)
        assert summary == expect_summary, summary
        deltas = [p.price_delta for p in parsed if p.value]
        assert deltas == expect_delta, deltas  # placeholder 제외, 값·가격 개수 일치
        return summary

    a = check(
        r"^(?P<value>.+?)(?:\s*\(\s*(?P<sign>[+-])\s*(?P<price>[\d,]+)\s*원\s*\))?$",
        ["- [필수] 옵션을 선택해 주세요 -", "S (기본) [품절아님]", "M (+10,000원)", "L (+20,000원)"],
        "3개 · S (기본) [품절아님], M, L / +0원, +10,000원, +20,000원",
        [0, 10000, 20000],
    )
    b = check(  # 다른 형식 + bare '선택'
        r"^(?P<value>.+?)(?:\s*(?P<sign>[+-])\s*(?P<price>[\d,]+)\s*원)?$",
        ["선택", "아이보리 + 0원", "브라운 + 0원"],
        "2개 · 아이보리, 브라운 / +0원, +0원",
        [0, 0],
    )
    print("option_text_parser self-check OK:", a, "|", b)
