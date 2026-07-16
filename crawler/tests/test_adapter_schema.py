from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from app.analyzer.adapter_schema import (
    Adapter,
    AdapterData,
    CategoriesConfig,
    FieldExtractor,
    NavigationConfig,
    OptionsConfig,
    ProductConfig,
    clean_field_value,
    extract_url_value,
    get_product_field_mappings,
)


# ── clean_field_value: 라벨 오염 자동 정리 ──────────────────────────────────
def test_clean_origin_strips_label_and_takes_value_after_colon():
    # itopic 시나리오: 브랜드+원산지가 한 컨테이너에 섞임 → "원산지 :" 뒤 국가만
    assert clean_field_value("origin", "브랜드 : VIGA\n원산지 : 중국(외 아시아)") == "중국(외 아시아)"
    assert clean_field_value("origin", "원산지 : 중국") == "중국"
    assert clean_field_value("origin", "제조국：대한민국") == "대한민국"


def test_clean_origin_leaves_plain_value_untouched():
    assert clean_field_value("origin", "국산") == "국산"
    assert clean_field_value("origin", "중국") == "중국"


def test_clean_origin_generic_label_when_no_origin_keyword():
    assert clean_field_value("origin", "made in : China") == "China"


def test_clean_name_and_code_strip_leading_label_prefix():
    assert clean_field_value("raw_product_name", "상품명 : 멋진 상품") == "멋진 상품"
    assert clean_field_value("supplier_product_code", "상품코드 : V50672") == "V50672"
    assert clean_field_value("brand_name", "브랜드 : VIGA") == "VIGA"
    assert clean_field_value("model_name", "모델명 : V-50672") == "V-50672"


def test_clean_name_preserves_mid_value_colon_and_no_label():
    # 라벨 접두 없으면 그대로 (중간 콜론 보존)
    assert clean_field_value("raw_product_name", "비가(VIGA) 쇼핑카트 (V50672)") == "비가(VIGA) 쇼핑카트 (V50672)"
    assert clean_field_value("raw_product_name", "특가 : 한정판 세트") == "특가 : 한정판 세트"


def test_clean_ignores_unknown_field_and_empty():
    assert clean_field_value("supply_price", "원산지 : 중국") == "원산지 : 중국"
    assert clean_field_value("origin", None) is None
    assert clean_field_value("origin", "") == ""


def test_clean_supply_price_picks_sale_price_over_consumer_price():
    # itopic: 상품정보 패널을 통째로 잡아 소비자가(취소선)가 앞에 온 경우 → 판매가격 값만.
    raw = "브랜드 : 아이넷  소비자가 : 59,000원 판매가격 : 35,400원 수량 1 EA"
    cleaned = clean_field_value("supply_price", raw)
    assert re.search(r"-?\d[\d,]*", cleaned).group().replace(",", "") == "35400"


def test_clean_supply_price_prefers_supply_label():
    assert clean_field_value("supply_price", "소비자가 : 59,000원 공급가 : 30,000원") == "30,000원"


def test_clean_supply_price_untouched_with_one_or_zero_labels():
    # 판매가는 판매가격의 부분문자열이지만 이중집계되지 않아 1개로 취급 → 무변형.
    assert clean_field_value("supply_price", "판매가격 : 35,400원") == "판매가격 : 35,400원"
    assert clean_field_value("supply_price", "35,400원") == "35,400원"


def _minimal_adapter_data() -> AdapterData:
    return AdapterData(
        name="테스트도매처",
        base_url="https://example.com",
    )


def test_minimal_adapter_loads() -> None:
    adapter = Adapter(adapter=_minimal_adapter_data())
    assert adapter.adapter.name == "테스트도매처"
    assert adapter.adapter.encoding == "utf-8"


def test_field_extractor_allows_empty_selector() -> None:
    """Empty selectors are allowed (LLM may generate them for fields it can't find).
    The adapter generator strips them before validation."""
    extractor = FieldExtractor(selector="")
    assert extractor.selector == ""


def test_field_extractor_allows_whitespace_selector() -> None:
    extractor = FieldExtractor(selector="   ")
    assert extractor.selector == "   "


def test_categories_tree_mode_requires_navigation() -> None:
    config = CategoriesConfig(mode="tree")
    assert config.navigation is None


def test_adapter_with_full_yaml_dict() -> None:
    raw = {
        "adapter": {
            "name": "아이토픽",
            "base_url": "https://www.itopic.co.kr",
            "encoding": "utf-8",
            "browser": {"channel": "msedge"},
            "login": {
                "required": True,
                "login_url": "https://www.itopic.co.kr/shop/member.html?type=login",
                "fields": {"id": "#login_id", "password": "#login_pw"},
                "submit": "button[type=submit]",
                "success_indicator": ".logout",
            },
            "categories": {
                "mode": "tree",
                "navigation": {
                    "menu_selector": ".gnb > li",
                    "link_selector": "a",
                    "max_depth": 2,
                    "submenu": {"selector": ".submenu a", "expand_trigger": "hover"},
                },
                "url_template": "https://www.itopic.co.kr/shop/goods/goods_list?category={category_id}&page={page}",
            },
            "listing": {
                "pagination": {"type": "page_number", "page_param": "page", "max_pages": 100},
                "product_link": {"selector": ".goods_list .goods_name a", "base": "relative"},
            },
            "product": {
                "supplier_product_id": {"selector": ".product_no"},
                "supplier_product_code": {"selector": ".goods_code"},
                "raw_product_name": {"selector": "h2.goods_name"},
                "supply_price": {"selector": ".sale_price", "transform": "extract_number"},
                "origin": {"selector": ".origin", "fallback": "국산"},
                "main_image_url": {"selector": ".main_image img", "attribute": "src", "fallback_attribute": "data-src"},
                "detail_content": {"selector": ".detail_content", "html": True},
            },
            "options": {
                "detection": "dom",
                "type": "combination",
                "groups": [{"name": "색상", "values_selector": ".option_color option"}],
                "dependent_options": {
                    "enabled": True,
                    "level_1_group": "색상",
                    "level_2_group": "사이즈",
                    "level_2_trigger": "click",
                    "level_2_values_selector": ".option_size option",
                },
            },
        }
    }
    adapter = Adapter.model_validate(raw)
    assert adapter.adapter.login.required is True
    assert adapter.adapter.categories.navigation is not None
    assert adapter.adapter.categories.navigation.max_depth == 2
    assert adapter.adapter.options.dependent_options.enabled is True
    assert len(adapter.adapter.options.groups) == 1


def test_mapping_rows_hide_unused_fields_and_include_option_row() -> None:
    adapter = Adapter.model_validate({
        "adapter": {
            "name": "Shop",
            "base_url": "https://shop.example",
            "product": {
                "supplier_product_id": {"selector": ".id"},
                "supplier_product_code": {"selector": ".code"},
                "brand_name": {"selector": ".brand"},
                "manufacturer": {"selector": ".maker"},
                "model_name": {"selector": ".model"},
            },
            "options": {"groups": [{"name": "색상", "values_selector": ".opt option"}]},
        }
    })

    rows = get_product_field_mappings(adapter)
    keys = [row["key"] for row in rows]
    assert "supplier_product_id" not in keys
    assert "brand_name" not in keys
    assert "manufacturer" not in keys
    assert "model_name" not in keys
    assert rows[-1]["key"] == "option_values"
    assert rows[-1]["label"] == "옵션값/가격"
    assert rows[-1]["fieldPath"] == "adapter.options.groups.0.values_selector"
    assert rows[-1]["selector"] == ".opt option"
    assert rows[-1]["testable"] is True


def test_mapping_rows_hide_option_price_row_but_keep_option_value_row() -> None:
    adapter = Adapter.model_validate({
        "adapter": {
            "name": "Shop",
            "base_url": "https://shop.example",
            "options": {
                "groups": [{"name": "색상", "values_selector": ".opt"}],
                "option_price_delta": {"selector": ".price", "multiple": True, "transform": "extract_number"},
            },
        }
    })

    rows = get_product_field_mappings(adapter)
    keys = [row["key"] for row in rows]
    option = rows[-1]
    assert "option_prices" not in keys
    assert option["key"] == "option_values"
    assert option["selector"] == ".opt"


def test_mapping_row_unmapped_option_is_optional_not_missing() -> None:
    # 옵션 그룹이 없으면 옵션 행은 오류('missing')가 아니라 선택사항('optional')이어야 한다.
    adapter = Adapter.model_validate({
        "adapter": {
            "name": "Shop",
            "base_url": "https://shop.example",
            "product": {"supplier_product_code": {"selector": ".code"}},
        }
    })
    option_row = next(r for r in get_product_field_mappings(adapter) if r["key"] == "option_values")
    assert option_row["status"] == "optional"


def test_mapping_row_url_param_marks_ok() -> None:
    adapter = Adapter.model_validate({
        "adapter": {
            "name": "Shop",
            "base_url": "https://shop.example",
            "product": {
                "supplier_product_code": {"fallback_from": "url", "url_param": "goodsno"},
            },
        }
    })
    row = next(r for r in get_product_field_mappings(adapter) if r["key"] == "supplier_product_code")
    assert row["status"] == "ok"
    assert row["urlParam"] == "goodsno"


def test_mapping_row_fallback_from_marks_ok() -> None:
    adapter = Adapter.model_validate({
        "adapter": {
            "name": "Shop",
            "base_url": "https://shop.example",
            "product": {
                "supplier_status": {"fallback_from": "maxq"},
            },
        }
    })
    row = next(r for r in get_product_field_mappings(adapter) if r["key"] == "supplier_status")
    assert row["status"] == "ok"
    assert row["selector"] == "자동 판정: maxq"


def test_extract_url_value_prefers_query_param() -> None:
    url = "https://shop.example/goods/view?goodsno=12345&cate=001"
    assert extract_url_value(url, FieldExtractor(url_param="goodsno")) == "12345"
    assert extract_url_value(url, FieldExtractor(url_param="cate")) == "001"
    # missing param -> None
    assert extract_url_value(url, FieldExtractor(url_param="nope")) is None
    # regex fallback still works when no url_param
    assert extract_url_value(url, FieldExtractor(url_pattern=r"goodsno=(\d+)")) == "12345"
    # url_param wins over url_pattern
    assert extract_url_value(url, FieldExtractor(url_param="cate", url_pattern=r"goodsno=(\d+)")) == "001"


def test_invalid_browser_channel_raises() -> None:
    with pytest.raises(ValidationError):
        AdapterData(name="x", base_url="https://x.com", browser={"channel": "firefox"})


def test_invalid_pagination_type_raises() -> None:
    with pytest.raises(ValidationError):
        AdapterData(
            name="x",
            base_url="https://x.com",
            listing={"pagination": {"type": "invalid"}},
        )
