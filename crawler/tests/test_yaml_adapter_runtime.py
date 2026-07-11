from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.crawlers.yaml_adapter import (
    YAMLAdapter,
    _fill_from_structured,
    _first_nonempty_str,
    _first_number,
    _option_price_at,
)


# ===== 작업 1: 옵션 가격 인덱스 정렬 =====

def test_option_price_at_uses_raw_index_when_counts_match() -> None:
    # price_values가 전체 요소 수(placeholder 포함)와 같으면 raw_idx로 집는다.
    prices = [None, 10000, 20000]  # index0은 placeholder 자리
    # 걸러진 첫 옵션(accepted 0)은 raw 1 → 10000, 밀리지 않는다.
    assert _option_price_at(prices, 3, 1, 0) == 10000
    assert _option_price_at(prices, 3, 2, 1) == 20000


def test_option_price_at_falls_back_to_accepted_index_when_counts_differ() -> None:
    prices = [10000, 20000]  # placeholder 없이 걸러진 값만
    assert _option_price_at(prices, 3, 1, 0) == 10000
    assert _option_price_at(prices, 3, 2, 1) == 20000


def test_option_price_at_out_of_range_is_none() -> None:
    assert _option_price_at([], 0, 0, 0) is None
    assert _option_price_at([100], 3, 5, 5) is None


# ===== 작업 3: 구조화 데이터 폴백 병합(순수 함수) =====

def test_fill_from_structured_only_fills_empty() -> None:
    sd = {"og_title": "OG이름", "ld_name": "LD이름",
          "og_image": "http://x/og.jpg", "ld_image": "http://x/ld.jpg",
          "og_price": "9000", "ld_price": "8000"}
    # 이미 값이 있으면 그대로 둔다.
    name, image, price = _fill_from_structured("추출이름", "http://x/e.jpg", 5000, sd)
    assert (name, image, price) == ("추출이름", "http://x/e.jpg", 5000)


def test_fill_from_structured_name_prefers_og_then_ld() -> None:
    name, _, _ = _fill_from_structured("", None, 1, {"og_title": "OG", "ld_name": "LD"})
    assert name == "OG"
    name, _, _ = _fill_from_structured("  ", None, 1, {"og_title": "", "ld_name": "LD"})
    assert name == "LD"


def test_fill_from_structured_price_prefers_ld_then_og() -> None:
    _, _, price = _fill_from_structured("n", "i", None, {"ld_price": "8,000원", "og_price": "9000"})
    assert price == 8000
    _, _, price = _fill_from_structured("n", "i", None, {"ld_price": None, "og_price": "9000"})
    assert price == 9000


def test_first_helpers_edge() -> None:
    assert _first_nonempty_str(None, "", "  ", "x") == "x"
    assert _first_nonempty_str(None, "") is None
    assert _first_number(None, "abc", "1,200") == 1200
    assert _first_number(0) == 0  # 0은 유효한 값
    assert _first_number(None) is None


# ===== 작업 2: 의존 옵션 placeholder 필터 + 인덱스 재질의 =====

class _El:
    def __init__(self, text: str = "", value: str | None = None, tag: str = "OPTION") -> None:
        self._text = text
        self._value = value if value is not None else text
        self._tag = tag
        self.clicked = False
        self.selected_with: dict | None = None
        self.evaluated: list[str] = []

    async def inner_text(self) -> str:
        return self._text

    async def get_attribute(self, name: str):
        if name == "value":
            return self._value
        if name == "class":
            return ""
        return None  # disabled 없음

    async def evaluate(self, script: str):
        self.evaluated.append(script)
        return self._tag if "tagName" in script else None

    async def click(self) -> None:
        self.clicked = True

    async def select_option(self, **kw) -> None:
        self.selected_with = kw


class _Page:
    url = "http://x/p"

    def __init__(self, level1, level2, l1_sel, l2_sel) -> None:
        self._level1 = level1
        self._level2 = level2
        self._l1_sel = l1_sel
        self._l2_sel = l2_sel

    async def query_selector_all(self, selector: str):
        if selector == self._l1_sel:
            return self._level1
        if selector == self._l2_sel:
            return self._level2
        return []

    async def wait_for_timeout(self, ms: int) -> None:
        return None


def _dep_config(l1_sel: str, l2_sel: str, trigger: str = "click"):
    return SimpleNamespace(
        groups=[SimpleNamespace(name="색상", values_selector=l1_sel,
                                value_text="text", value_attribute=None)],
        dependent_options=SimpleNamespace(
            enabled=True, level_1_group="색상", level_2_group="사이즈",
            level_2_trigger=trigger, level_2_load_indicator=None,
            level_2_values_selector=l2_sel,
        ),
    )


def test_dependent_options_filters_placeholders_and_maps_by_index() -> None:
    l1 = [_El("- 선택하세요 -"), _El("빨강"), _El("파랑")]  # index0은 placeholder
    l2 = [_El("S"), _El("M"), _El("- 선택 -")]              # 마지막은 placeholder
    page = _Page(l1, l2, "#c option", "#s option")
    adapter = YAMLAdapter.__new__(YAMLAdapter)

    options = asyncio.run(
        adapter._extract_dependent_options(page, _dep_config("#c option", "#s option"), "P1", 1000)
    )
    # 유효 l1 2개 × 유효 l2 2개 = 4, placeholder는 전부 제외
    assert len(options) == 4
    assert {o.option_value_1 for o in options} == {"빨강", "파랑"}
    assert {o.option_value_2 for o in options} == {"S", "M"}
    # click 트리거로 선택된 l1 요소만 클릭됨(placeholder는 클릭 안 함)
    assert l1[1].clicked and l1[2].clicked and not l1[0].clicked


def test_select_dependent_level1_select_vs_option() -> None:
    adapter = YAMLAdapter.__new__(YAMLAdapter)
    sel = _El("빨강", tag="SELECT")
    asyncio.run(adapter._select_dependent_level1(sel, "빨강"))
    assert sel.selected_with == {"label": "빨강"}

    opt = _El("빨강", value="r", tag="OPTION")
    asyncio.run(adapter._select_dependent_level1(opt, "빨강"))
    # option 요소는 부모 select에 change 이벤트를 dispatch (closest('select'))
    assert any("closest('select')" in s for s in opt.evaluated)
    assert opt.selected_with is None
