from __future__ import annotations

from app.schema.standard import (
    REQUIRED_STANDARD_PRODUCT_FIELDS,
    StandardOption,
    StandardProduct,
    build_option_display_name,
    clean_standard_text,
    derive_option_price_delta,
)


def test_required_fields_match_processor_schema() -> None:
    assert REQUIRED_STANDARD_PRODUCT_FIELDS == [
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


def test_clean_standard_text_handles_none_and_blank() -> None:
    assert clean_standard_text(None) is None
    assert clean_standard_text("") is None
    assert clean_standard_text("  ") is None
    assert clean_standard_text(" hello ") == "hello"


def test_build_option_display_name_joins_non_blank() -> None:
    option = {"option_value_1": "블랙", "option_value_2": "L", "option_value_3": ""}
    assert build_option_display_name(option) == "블랙 / L"


def test_derive_option_price_delta() -> None:
    assert derive_option_price_delta(13000, 12000) == 1000
    assert derive_option_price_delta(12000, 12000) == 0
    assert derive_option_price_delta(None, 12000) is None
    assert derive_option_price_delta(13000, None) is None


def test_standard_product_dataclass_defaults() -> None:
    product = StandardProduct(
        supplier_name="테스트",
        supplier_product_id="1",
        supplier_product_code="P-1",
        supplier_status="available",
        raw_product_name="상품",
        origin="국산",
        supply_price=10000,
        main_image_url="http://img/test.jpg",
        detail_content="<p>detail</p>",
    )
    assert product.extra_image_urls == []
    assert product.raw_metadata == {}
    assert product.supplier_category is None
    assert product.brand_name is None


def test_standard_option_dataclass_defaults() -> None:
    option = StandardOption(
        supplier_product_code="P-1",
        option_sku="P-1-1",
        option_type="combination",
        option_group_1="색상",
        option_value_1="블랙",
        option_group_2=None,
        option_value_2=None,
        option_group_3=None,
        option_value_3=None,
        option_display_name="블랙",
        option_supply_price=12000,
        option_sale_price=None,
        option_price_delta=0,
        option_stock_quantity=None,
        option_status="available",
        option_usable=True,
        option_main_image_url=None,
        option_extra_image_urls=[],
        option_position=1,
        raw_option_text="블랙",
        raw_option_metadata={},
    )
    assert option.option_extra_image_urls == []
    assert option.option_usable is True
