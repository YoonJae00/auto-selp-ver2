from __future__ import annotations

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
    get_product_field_mappings,
)


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
    assert rows[-1]["fieldPath"] == "adapter.options.groups.0.values_selector"
    assert rows[-1]["selector"] == ".opt option"


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
