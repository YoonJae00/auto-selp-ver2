from __future__ import annotations

import pytest
import yaml

from app.analyzer.adapter_generator import SYSTEM_PROMPT, _build_user_prompt, _finalize_generated_yaml, _strip_empty_selectors
from app.analyzer.mapping_hints import MappingHint, apply_locked_hints_to_yaml_dict, format_mapping_hints_for_prompt
from app.analyzer.site_probe import ProbeResult
from app.crawlers.registry import load_adapter_from_text


def _base_yaml_dict() -> dict:
    return {
        "adapter": {
            "name": "테스트",
            "base_url": "https://example.com",
            "listing": {"product_link": {"selector": "a.old", "attribute": "href"}},
            "product": {
                "raw_product_name": {"selector": ".ai-name", "transform": "strip"},
                "status_mapping": {"mapping": {"품절": "sold_out"}, "default": "available"},
            },
        }
    }


def test_prompt_formatting_sanitizes_and_truncates_observed_values() -> None:
    dirty = "```<script>x</script>" + "a" * 500 + "\x00`"
    text = format_mapping_hints_for_prompt([
        MappingHint("product", "adapter.product.raw_product_name", ".name", observed_value=dirty, locked=False)
    ])
    assert "```" not in text
    assert "`" not in text
    assert "<script>" not in text
    assert "\x00" not in text
    assert len(text) < 700


def test_auto_prompt_marks_detail_extra_and_options_as_manual_only() -> None:
    assert "상세 이미지(detail_content), 추가 이미지(extra_image_urls), 옵션값(groups), 옵션가격(option_price_delta)은 자동 생성하지 마세요." in SYSTEM_PROMPT


def test_locked_product_hint_overrides_ai_selector() -> None:
    data = _base_yaml_dict()
    apply_locked_hints_to_yaml_dict(data, [MappingHint("product", "adapter.product.raw_product_name", ".human-name")])
    assert data["adapter"]["product"]["raw_product_name"]["selector"] == ".human-name"


def test_unlocked_hint_appears_in_prompt_but_does_not_override_yaml() -> None:
    hint = MappingHint("product", "adapter.product.raw_product_name", ".human-name", locked=False)
    prompt = _build_user_prompt(ProbeResult("https://example.com", "https://example.com", "utf-8", False, "", "", ""), "테스트", [hint])
    assert ".human-name" in prompt
    data = _base_yaml_dict()
    apply_locked_hints_to_yaml_dict(data, [hint])
    assert data["adapter"]["product"]["raw_product_name"]["selector"] == ".ai-name"


def test_missing_product_extractor_created_with_defaults() -> None:
    data = _base_yaml_dict()
    apply_locked_hints_to_yaml_dict(data, [
        MappingHint("product", "adapter.product.supply_price", ".price"),
        MappingHint("product", "adapter.product.main_image_url", ".main img"),
        MappingHint("product", "adapter.product.detail_content", ".detail"),
    ])
    product = data["adapter"]["product"]
    assert product["supply_price"] == {"transform": "extract_number", "selector": ".price"}
    assert product["main_image_url"]["attribute"] == "src"
    assert product["main_image_url"]["fallback_attribute"] == "data-src"
    assert product["detail_content"]["attribute"] == "src"
    assert product["detail_content"]["fallback_attribute"] == "data-src"
    assert product["detail_content"]["multiple"] is True


def test_existing_extractor_preserves_unspecified_ai_fields() -> None:
    data = _base_yaml_dict()
    apply_locked_hints_to_yaml_dict(data, [MappingHint("product", "adapter.product.raw_product_name", ".human-name")])
    extractor = data["adapter"]["product"]["raw_product_name"]
    assert extractor["selector"] == ".human-name"
    assert extractor["transform"] == "strip"


def test_listing_product_link_merge_works() -> None:
    data = _base_yaml_dict()
    apply_locked_hints_to_yaml_dict(data, [MappingHint("listing", "adapter.listing.product_link", ".product a")])
    assert data["adapter"]["listing"]["product_link"] == {"selector": ".product a", "attribute": "href"}


def test_option_values_hint_creates_first_group() -> None:
    data = _base_yaml_dict()
    data["adapter"]["options"] = {"groups": []}
    apply_locked_hints_to_yaml_dict(data, [MappingHint("detail", "adapter.options.groups.0.values_selector", ".options option")])
    assert data["adapter"]["options"]["groups"][0] == {"name": "옵션", "values_selector": ".options option"}
    assert data["adapter"]["options"]["detection"] == "dom"


def test_option_price_hint_creates_multiple_price_extractor() -> None:
    data = _base_yaml_dict()
    apply_locked_hints_to_yaml_dict(data, [MappingHint("detail", "adapter.options.option_price_delta", ".option-price")])
    price = data["adapter"]["options"]["option_price_delta"]
    assert price["selector"] == ".option-price"
    assert price["transform"] == "extract_number"
    assert price["multiple"] is True


def test_final_yaml_strips_manual_only_fields_from_auto_generation() -> None:
    data = _base_yaml_dict()
    data["adapter"]["product"]["detail_content"] = {"selector": ".detail img", "attribute": "src", "multiple": True}
    data["adapter"]["product"]["extra_image_urls"] = {"selector": ".extra img", "attribute": "src", "multiple": True}
    data["adapter"]["options"] = {
        "groups": [{"name": "색상", "values_selector": ".option"}],
        "option_price_delta": {"selector": ".option-price", "multiple": True, "transform": "extract_number"},
    }

    yaml_text, adapter = _finalize_generated_yaml(yaml.safe_dump(data, allow_unicode=True))

    assert adapter.adapter.product.detail_content is None
    assert adapter.adapter.product.extra_image_urls is None
    assert adapter.adapter.options.groups == []
    assert adapter.adapter.options.option_price_delta is None
    assert "detail_content" not in yaml_text
    assert "extra_image_urls" not in yaml_text
    assert "option_price_delta" not in yaml_text


def test_final_yaml_keeps_manual_only_fields_when_locked_by_user_hint() -> None:
    yaml_text, adapter = _finalize_generated_yaml(yaml.safe_dump(_base_yaml_dict(), allow_unicode=True), [
        MappingHint("product", "adapter.product.detail_content", ".detail img"),
        MappingHint("product", "adapter.product.extra_image_urls", ".extra img"),
        MappingHint("detail", "adapter.options.groups.0.values_selector", ".option"),
        MappingHint("detail", "adapter.options.option_price_delta", ".option-price"),
    ])

    assert adapter.adapter.product.detail_content is not None
    assert adapter.adapter.product.extra_image_urls is not None
    assert adapter.adapter.options.groups[0].values_selector == ".option"
    assert adapter.adapter.options.option_price_delta is not None
    assert "detail_content" in yaml_text
    assert "extra_image_urls" in yaml_text


def test_unknown_field_path_rejected() -> None:
    with pytest.raises(ValueError):
        MappingHint("product", "adapter.login.fields.password", "#pw")


def test_empty_chosen_selector_rejected() -> None:
    with pytest.raises(ValueError):
        MappingHint("product", "adapter.product.raw_product_name", "   ")


def test_strip_empty_selectors_preserves_fallback_only_status_field() -> None:
    data = _base_yaml_dict()
    data["adapter"]["product"]["supplier_status"] = {"selector": "", "fallback_from": "maxq"}
    _strip_empty_selectors(data)
    assert data["adapter"]["product"]["supplier_status"] == {"selector": "", "fallback_from": "maxq"}


def test_duplicate_locked_hints_are_last_wins() -> None:
    data = _base_yaml_dict()
    apply_locked_hints_to_yaml_dict(data, [
        MappingHint("product", "adapter.product.raw_product_name", ".first"),
        MappingHint("product", "adapter.product.raw_product_name", ".last"),
    ])
    assert data["adapter"]["product"]["raw_product_name"]["selector"] == ".last"


def test_final_yaml_revalidates_and_contains_no_hint_metadata() -> None:
    yaml_text, _adapter = _finalize_generated_yaml(yaml.safe_dump(_base_yaml_dict(), allow_unicode=True), [
        MappingHint("product", "adapter.product.raw_product_name", ".human-name", observed_value="secret", locked=True)
    ])
    loaded = load_adapter_from_text(yaml_text)
    assert loaded.adapter.product.raw_product_name.selector == ".human-name"
    assert "observed_value" not in yaml_text
    assert "locked" not in yaml_text
    assert "mapping_hints" not in yaml_text


def test_listing_hint_final_yaml_contains_no_hint_only_metadata() -> None:
    yaml_text, _adapter = _finalize_generated_yaml(yaml.safe_dump(_base_yaml_dict(), allow_unicode=True), [
        MappingHint(
            "listing",
            "adapter.listing.product_link",
            ".item a",
            observed_value="상품 링크",
            selector_candidates=[".item a", "a[href*='goods']"],
            locked=True,
        )
    ])
    assert ".item a" in yaml_text
    for metadata_key in ("observed_value", "locked", "page_kind", "selector_candidates"):
        assert metadata_key not in yaml_text


def test_finalize_fallback_path_helper_applies_merge() -> None:
    yaml_text, adapter = _finalize_generated_yaml(yaml.safe_dump(_base_yaml_dict(), allow_unicode=True), [
        MappingHint("product", "adapter.product.origin", ".origin")
    ])
    assert adapter.adapter.product.origin.selector == ".origin"
    assert ".origin" in yaml_text


def test_locked_all_products_hint_sets_url_and_available() -> None:
    data = _base_yaml_dict()
    apply_locked_hints_to_yaml_dict(data, [
        MappingHint("listing", "adapter.categories.all_products.url", "https://example.com/all-products", locked=True)
    ])
    categories = data["adapter"]["categories"]
    assert categories["all_products"]["url"] == "https://example.com/all-products"
    assert categories["all_products"]["available"] is True
