from __future__ import annotations

import asyncio

import pytest

import app.analyzer.adapter_generator as ag
from app.analyzer.adapter_generator import (
    generate_adapter_yaml,
    verify_adapter_against_probe,
)
from app.analyzer.adapter_schema import Adapter
from app.analyzer.mapping_hints import MappingHint
from app.analyzer.platform_hints import (
    PLATFORM_PROMPT_HINTS,
    detect_platform,
    platform_hint_block,
)
from app.analyzer.site_probe import ProbeResult


# ----- 플랫폼 감지 -----

def test_detect_platform_cafe24_by_class():
    assert detect_platform('<div class="xans-product-detail">', "https://x.com") == "cafe24"


def test_detect_platform_makeshop_by_url():
    assert detect_platform("<html></html>", "https://m.co.kr/shopdetail.html?branduid=1") == "makeshop"


def test_detect_platform_youngcart_by_marker():
    assert detect_platform('<div id="sit_title">', "https://y.com/shop/item.php?it_id=1") == "youngcart"


def test_detect_platform_none():
    assert detect_platform("<html><body>hello</body></html>", "https://x.com") is None


def test_platform_hint_block_has_reference_disclaimer():
    block = platform_hint_block("makeshop")
    assert "maxq" in block
    assert "참고용" in block
    assert platform_hint_block(None) == ""
    assert platform_hint_block("unknown") == ""


def test_all_platforms_have_hints():
    for name in ("cafe24", "makeshop", "godomall", "youngcart", "wisa"):
        assert name in PLATFORM_PROMPT_HINTS


# ----- verify_adapter_against_probe -----

def _adapter(product: dict, product_link: str = "a[href*='shopdetail']") -> Adapter:
    return Adapter.model_validate({
        "adapter": {
            "name": "t",
            "base_url": "https://x.com",
            "listing": {"product_link": {"selector": product_link}},
            "product": product,
        }
    })


def _probe(detail_html: str = "", listing_html: str = "") -> ProbeResult:
    return ProbeResult(
        main_url="https://x.com", final_url="https://x.com", encoding="utf-8",
        needs_login=False, login_form_html="",
        listing_html=listing_html, detail_html=detail_html,
    )


DETAIL = (
    '<div class="name">멋진 상품</div>'
    '<div class="price">공급가 12,000원</div>'
    '<div class="thumb"><img data-src="/img/a.jpg"></div>'
)


def test_verify_reports_good_and_bad_selectors():
    adapter = _adapter({
        "raw_product_name": {"selector": ".name"},
        "supply_price": {"selector": ".price", "transform": "extract_number"},
        "main_image_url": {"selector": ".thumb img", "attribute": "src", "fallback_attribute": "data-src"},
        "supplier_product_code": {"selector": ".missing"},
    })
    result = verify_adapter_against_probe(adapter, _probe(DETAIL, "<a href='/shopdetail.html'>x</a>"))
    assert result["failed_fields"] == ["supplier_product_code"]
    assert result["values"]["raw_product_name"] == "멋진 상품"
    assert result["values"]["supply_price"] == 12000  # extract_number 반영
    assert result["values"]["main_image_url"] == "/img/a.jpg"  # data-src lazy 속성 반영
    assert result["product_link_count"] == 1


def test_verify_skips_playwright_pseudo_selectors():
    adapter = _adapter({"origin": {"selector": "span:has-text('원산지')"}})
    result = verify_adapter_against_probe(adapter, _probe(DETAIL))
    # 검증 불가이므로 실패도 값도 없음
    assert "origin" not in result["failed_fields"]
    assert "origin" not in result["values"]


def test_verify_extract_number_failure_is_failed():
    adapter = _adapter({"supply_price": {"selector": ".name", "transform": "extract_number"}})
    result = verify_adapter_against_probe(adapter, _probe(DETAIL))
    assert "supply_price" in result["failed_fields"]  # 숫자 없음 → 실패


def test_verify_bad_syntax_selector_skipped():
    adapter = _adapter({"raw_product_name": {"selector": "div[unclosed"}})
    result = verify_adapter_against_probe(adapter, _probe(DETAIL))
    assert "raw_product_name" not in result["failed_fields"]


def test_verify_product_link_zero_matches_failed():
    adapter = _adapter({}, product_link="a.no-such-link")
    result = verify_adapter_against_probe(adapter, _probe(DETAIL, "<a href='/shopdetail.html'>x</a>"))
    assert result["product_link_count"] == 0
    assert "product_link" in result["failed_fields"]


# ----- generate_adapter_yaml 통합 (LLM mock) -----

class _FakeClient:
    """system 프롬프트로 생성/수리 호출을 구분하는 가짜 LLM 클라이언트."""

    def __init__(self, gen_yaml: str, repair_json: str, calls: list[str]):
        self._gen = gen_yaml
        self._repair = repair_json
        self._calls = calls

    async def generate(self, system: str, user: str) -> str:
        if "교정" in system:  # REPAIR_SYSTEM_PROMPT
            self._calls.append("repair")
            return self._repair
        self._calls.append("generate")
        return self._gen


GEN_YAML_BAD_PRICE = """
adapter:
  name: T
  base_url: https://x.com
  listing:
    product_link:
      selector: a[href*='shopdetail']
  product:
    raw_product_name:
      selector: .name
    supply_price:
      selector: .wrong
      transform: extract_number
"""


def test_generate_triggers_repair_and_adopts_improvement(monkeypatch):
    calls: list[str] = []
    repair_json = '{"supply_price": {"selector": ".price", "attribute": "", "transform": "extract_number"}}'
    fake = _FakeClient(GEN_YAML_BAD_PRICE, repair_json, calls)
    monkeypatch.setattr(ag, "get_llm_client", lambda provider: fake)

    probe = _probe(DETAIL, "<a href='/shopdetail.html'>x</a>")
    result = asyncio.run(generate_adapter_yaml(probe, "테스트몰", llm_provider="gemini"))

    assert "repair" in calls  # 검증 실패로 수리 발동
    assert ".price" in result.yaml_text  # 개선된 선택자 채택
    assert result.verification["failed_fields"] == []  # 재검증 통과


def test_generate_excludes_locked_hint_from_repair(monkeypatch):
    calls: list[str] = []
    fake = _FakeClient(GEN_YAML_BAD_PRICE, "{}", calls)
    monkeypatch.setattr(ag, "get_llm_client", lambda provider: fake)

    # supply_price 를 라이브 DOM 기준 선택자로 잠금 → 축소 DOM에서 안 잡혀도 실패/수리 제외.
    hint = MappingHint(
        page_kind="detail",
        field_path="adapter.product.supply_price",
        chosen_selector=".live-only-price",
        transform="extract_number",
        locked=True,
    )
    probe = _probe(DETAIL, "<a href='/shopdetail.html'>x</a>")
    result = asyncio.run(
        generate_adapter_yaml(probe, "테스트몰", llm_provider="gemini", mapping_hints=[hint])
    )

    assert "repair" not in calls  # 잠금 필드는 수리 대상 아님
    assert "supply_price" not in result.verification["failed_fields"]
    assert ".live-only-price" in result.yaml_text  # 잠금 선택자 유지


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
