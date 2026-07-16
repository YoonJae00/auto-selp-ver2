import pandas as pd

from utils.wholesale_upload import (
    REQUIRED_WHOLESALE_FIELDS,
    build_images_list,
    build_mapping_preview,
    merge_product_warnings,
    parse_int_price,
    parse_option_variants,
    parse_wholesale_row,
    sanitize_column_mapping,
    validate_required_mappings,
)
from utils.standard_product_schema import (
    REQUIRED_STANDARD_PRODUCT_FIELDS,
    build_option_display_name,
    derive_option_price_delta,
)


def test_validate_required_mappings_reports_missing_required_fields():
    columns = ["상태", "상품코드", "상품명", "가격", "원산지", "목록이미지1", "상세이미지"]
    mapping = {
        "wholesale_status": "상태",
        "product_code": "상품코드",
        "original_name": "상품명",
        "price_wholesale_raw": "가격",
        "origin": "원산지",
        "image_list_1": "목록이미지1",
        "image_detail": "상세이미지",
    }
    missing = validate_required_mappings(mapping, columns)
    assert REQUIRED_WHOLESALE_FIELDS[1] == "wholesale_product_id"
    assert missing == ["wholesale_product_id"]


def test_validate_required_mappings_reports_missing_excel_headers():
    columns = ["상태", "제품번호", "상품코드", "상품명", "가격", "원산지", "상세이미지"]
    mapping = {
        "wholesale_status": "상태",
        "wholesale_product_id": "제품번호",
        "product_code": "상품코드",
        "original_name": "상품명",
        "price_wholesale_raw": "가격",
        "origin": "원산지",
        "image_list_1": "목록이미지1",
        "image_detail": "상세이미지",
    }
    missing = validate_required_mappings(mapping, columns)
    assert missing == ["image_list_1"]


def test_validate_required_mappings_accepts_parser_fallback_headers_without_mapping():
    columns = ["상태", "제품번호", "상품코드", "상품명", "가격", "원산지", "목록이미지1", "상세이미지"]

    missing = validate_required_mappings({}, columns)

    assert missing == []


def test_validate_required_mappings_accepts_legacy_mapping_keys():
    columns = ["품절유무", "제품번호", "도매상품코드", "상품명", "공급가", "원산지", "이미지", "상세이미지"]
    mapping = {
        "wholesale_status": "품절유무",
        "wholesale_product_id": "제품번호",
        "product_code": "도매상품코드",
        "original_name": "상품명",
        "price_wholesale": "공급가",
        "origin": "원산지",
        "images_list": "이미지",
        "image_detail": "상세이미지",
    }

    missing = validate_required_mappings(mapping, columns)

    assert missing == []


def test_parse_int_price_handles_numeric_formatting():
    assert parse_int_price("2,640원") == 2640
    assert parse_int_price(" 2820.0 ") == 2820
    assert parse_int_price("") is None
    assert parse_int_price(None) is None


def test_parse_int_price_rejects_multi_price_separator_strings():
    assert parse_int_price("2,640원 / 2,820원") is None
    assert parse_int_price("740,740,740,740") is None


def test_parse_option_variants_pairs_options_with_prices_and_uses_first_price():
    result = parse_option_variants("L자형,V자형", "2640,2820")
    assert result["price_wholesale"] == 2640
    assert result["option_variants"] == [
        {"name": "L자형", "price_wholesale": 2640, "position": 1},
        {"name": "V자형", "price_wholesale": 2820, "position": 2},
    ]
    assert result["warnings"] == []


def test_parse_option_variants_pairs_options_with_formatted_prices():
    result = parse_option_variants("L자형,V자형", "2,640원,2,820원")
    assert result["price_wholesale"] == 2640
    assert result["option_variants"] == [
        {"name": "L자형", "price_wholesale": 2640, "position": 1},
        {"name": "V자형", "price_wholesale": 2820, "position": 2},
    ]
    assert result["warnings"] == []


def test_parse_option_variants_pairs_repeated_unformatted_prices():
    result = parse_option_variants("대(8P),소(32P)", "740,740")
    assert result["price_wholesale"] == 740
    assert result["option_variants"] == [
        {"name": "대(8P)", "price_wholesale": 740, "position": 1},
        {"name": "소(32P)", "price_wholesale": 740, "position": 2},
    ]
    assert result["warnings"] == []


def test_parse_option_variants_keeps_single_price_without_options():
    result = parse_option_variants(None, "3900")
    assert result["price_wholesale"] == 3900
    assert result["option_variants"] == []
    assert result["warnings"] == []


def test_parse_option_variants_treats_formatted_price_as_single_price_without_options():
    result = parse_option_variants(None, "2,640원")
    assert result["price_wholesale"] == 2640
    assert result["option_variants"] == []
    assert result["warnings"] == []


def test_parse_option_variants_uses_first_option_price_as_representative_even_when_invalid():
    result = parse_option_variants("L자형,V자형", "bad,2820")
    assert result["price_wholesale"] is None
    assert result["option_variants"] == []
    assert result["warnings"] == [
        {
            "field": "price_wholesale_raw",
            "message": "One or more option prices could not be parsed.",
            "raw_value": "bad,2820",
        }
    ]


def test_parse_option_variants_reuses_single_base_price_for_each_option():
    result = parse_option_variants("L자형,V자형", "2640")
    assert result["price_wholesale"] == 2640
    assert result["option_variants"] == [
        {"name": "L자형", "price_wholesale": 2640, "position": 1},
        {"name": "V자형", "price_wholesale": 2640, "position": 2},
    ]
    assert result["warnings"] == []


def test_build_images_list_uses_ordered_slots_and_drops_blanks():
    values = {
        "image_list_1": "https://img.example/1.jpg",
        "image_list_2": "",
        "image_list_3": "https://img.example/3.jpg",
        "image_list_4": None,
        "image_list_5": float("nan"),
    }
    assert build_images_list(values) == [
        "https://img.example/1.jpg",
        "https://img.example/3.jpg",
    ]


def test_parse_wholesale_row_normalizes_supplier_schema():
    row = pd.Series(
        {
            "상태": "정상",
            "제품번호": "12345",
            "상품코드": "ABC-001",
            "상품명": "테스트 상품",
            "옵션값": "L자형,V자형",
            "가격": "2640,2820",
            "소비자가": "5,000",
            "판매준수가": "3,500",
            "원산지": "해외|아시아|중국",
            "목록이미지1": "https://img.example/1.jpg",
            "목록이미지2": "https://img.example/2.jpg",
            "상세이미지": "<img src='detail.jpg'>",
            "등록일": "2026-05-20",
        }
    )
    mapping = {
        "wholesale_status": "상태",
        "wholesale_product_id": "제품번호",
        "product_code": "상품코드",
        "original_name": "상품명",
        "option_values_raw": "옵션값",
        "price_wholesale_raw": "가격",
        "price_retail": "소비자가",
        "price_min_selling": "판매준수가",
        "origin": "원산지",
        "image_list_1": "목록이미지1",
        "image_list_2": "목록이미지2",
        "image_detail": "상세이미지",
        "wholesale_registered_at": "등록일",
    }
    parsed = parse_wholesale_row(row, mapping)
    assert parsed["product_data"]["wholesale_status"] == "정상"
    assert parsed["product_data"]["wholesale_product_id"] == "12345"
    assert parsed["product_data"]["product_code"] == "ABC-001"
    assert parsed["product_data"]["original_name"] == "테스트 상품"
    assert parsed["product_data"]["price_wholesale_raw"] == "2640,2820"
    assert parsed["product_data"]["price_wholesale"] == 2640
    assert parsed["product_data"]["price_retail"] == 5000
    assert parsed["product_data"]["price_min_selling"] == 3500
    assert parsed["product_data"]["origin"] == "해외|아시아|중국"
    assert parsed["product_data"]["images_list"] == [
        "https://img.example/1.jpg",
        "https://img.example/2.jpg",
    ]
    assert parsed["product_data"]["image_detail"] == "<img src='detail.jpg'>"
    assert parsed["product_data"]["wholesale_registered_at"] == "2026-05-20"
    assert parsed["product_data"]["option_variants"][1] == {
        "name": "V자형",
        "price_wholesale": 2820,
        "position": 2,
    }
    assert parsed["warnings"] == []


def test_parse_wholesale_row_uses_legacy_mapping_keys_for_supplier_fields():
    row = pd.Series(
        {
            "상태": "정상",
            "제품번호": "12345",
            "상품코드": "ABC-001",
            "상품명": "테스트 상품",
            "옵션": "L자형,V자형",
            "도매가": "2640,2820",
            "원산지": "국내",
            "이미지": "https://img.example/1.jpg",
            "상세이미지": "https://img.example/detail.jpg",
        }
    )
    mapping = {
        "price_wholesale": "도매가",
        "options": "옵션",
        "images_list": "이미지",
    }

    parsed = parse_wholesale_row(row, mapping)

    assert parsed["product_data"]["option_values_raw"] == "L자형,V자형"
    assert parsed["product_data"]["price_wholesale_raw"] == "2640,2820"
    assert parsed["product_data"]["images_list"] == ["https://img.example/1.jpg"]
    assert parsed["product_data"]["option_variants"] == [
        {"name": "L자형", "price_wholesale": 2640, "position": 1},
        {"name": "V자형", "price_wholesale": 2820, "position": 2},
    ]
    assert parsed["warnings"] == []


def test_parse_wholesale_row_emits_standard_options_with_images_and_price_deltas():
    row = pd.Series(
        {
            "상태": "정상",
            "제품번호": "12345",
            "상품코드": "ABC-001",
            "상품명": "테스트 상품",
            "옵션값": "블랙,L",
            "가격": "12000,13000",
            "옵션이미지": "https://img.example/black.jpg,https://img.example/large.jpg",
            "원산지": "국내",
            "목록이미지1": "https://img.example/1.jpg",
            "상세이미지": "https://img.example/detail.jpg",
        }
    )
    mapping = {
        "wholesale_status": "상태",
        "wholesale_product_id": "제품번호",
        "product_code": "상품코드",
        "original_name": "상품명",
        "option_values_raw": "옵션값",
        "price_wholesale_raw": "가격",
        "option_image_urls_raw": "옵션이미지",
        "origin": "원산지",
        "image_list_1": "목록이미지1",
        "image_detail": "상세이미지",
    }

    parsed = parse_wholesale_row(row, mapping)

    assert parsed["product_data"]["standard_options"] == [
        {
            "supplier_product_code": "ABC-001",
            "option_sku": "ABC-001-1",
            "option_type": "combination",
            "option_group_1": "옵션",
            "option_value_1": "블랙",
            "option_group_2": None,
            "option_value_2": None,
            "option_group_3": None,
            "option_value_3": None,
            "option_display_name": "블랙",
            "option_supply_price": 12000,
            "option_sale_price": None,
            "option_price_delta": 0,
            "option_stock_quantity": None,
            "option_status": "정상",
            "option_usable": True,
            "option_main_image_url": "https://img.example/black.jpg",
            "option_extra_image_urls": [],
            "option_position": 1,
            "raw_option_text": "블랙",
            "raw_option_metadata": {
                "option_values_raw": "블랙,L",
                "price_wholesale_raw": "12000,13000",
                "option_image_urls_raw": "https://img.example/black.jpg,https://img.example/large.jpg",
            },
        },
        {
            "supplier_product_code": "ABC-001",
            "option_sku": "ABC-001-2",
            "option_type": "combination",
            "option_group_1": "옵션",
            "option_value_1": "L",
            "option_group_2": None,
            "option_value_2": None,
            "option_group_3": None,
            "option_value_3": None,
            "option_display_name": "L",
            "option_supply_price": 13000,
            "option_sale_price": None,
            "option_price_delta": 1000,
            "option_stock_quantity": None,
            "option_status": "정상",
            "option_usable": True,
            "option_main_image_url": "https://img.example/large.jpg",
            "option_extra_image_urls": [],
            "option_position": 2,
            "raw_option_text": "L",
            "raw_option_metadata": {
                "option_values_raw": "블랙,L",
                "price_wholesale_raw": "12000,13000",
                "option_image_urls_raw": "https://img.example/black.jpg,https://img.example/large.jpg",
            },
        },
    ]


def test_parse_wholesale_row_without_options_emits_empty_option_sets_and_keeps_price():
    row = pd.Series(
        {
            "상태": "정상",
            "제품번호": "12345",
            "상품코드": "ABC-001",
            "상품명": "테스트 상품",
            "가격": "12000",
            "원산지": "국내",
            "목록이미지1": "https://img.example/1.jpg",
            "상세이미지": "https://img.example/detail.jpg",
        }
    )
    mapping = {
        "wholesale_status": "상태",
        "wholesale_product_id": "제품번호",
        "product_code": "상품코드",
        "original_name": "상품명",
        "price_wholesale_raw": "가격",
        "origin": "원산지",
        "image_list_1": "목록이미지1",
        "image_detail": "상세이미지",
    }

    parsed = parse_wholesale_row(row, mapping)

    assert parsed["product_data"]["price_wholesale"] == 12000
    assert parsed["product_data"]["option_variants"] == []
    assert parsed["product_data"]["standard_options"] == []


def test_parse_wholesale_row_standard_options_uses_simple_split_fallback_for_repeated_prices():
    row = pd.Series(
        {
            "상태": "정상",
            "제품번호": "12345",
            "상품코드": "ABC-001",
            "상품명": "테스트 상품",
            "옵션값": "대(8P),소(32P)",
            "가격": "740,740",
            "원산지": "국내",
            "목록이미지1": "https://img.example/1.jpg",
            "상세이미지": "https://img.example/detail.jpg",
        }
    )
    mapping = {
        "wholesale_status": "상태",
        "wholesale_product_id": "제품번호",
        "product_code": "상품코드",
        "original_name": "상품명",
        "option_values_raw": "옵션값",
        "price_wholesale_raw": "가격",
        "origin": "원산지",
        "image_list_1": "목록이미지1",
        "image_detail": "상세이미지",
    }

    parsed = parse_wholesale_row(row, mapping)
    standard_options = parsed["product_data"]["standard_options"]

    assert [option["option_supply_price"] for option in standard_options] == [740, 740]
    assert [option["option_price_delta"] for option in standard_options] == [0, 0]


def test_parse_wholesale_row_reuses_base_price_when_option_price_list_is_absent():
    row = pd.Series(
        {
            "상태": "정상",
            "제품번호": "12345",
            "상품코드": "ABC-001",
            "상품명": "테스트 상품",
            "옵션값": "블랙,L",
            "가격": "12000",
            "원산지": "국내",
            "목록이미지1": "https://img.example/1.jpg",
            "상세이미지": "https://img.example/detail.jpg",
        }
    )

    parsed = parse_wholesale_row(row, {})

    assert [item["price_wholesale"] for item in parsed["product_data"]["option_variants"]] == [12000, 12000]
    assert [item["option_supply_price"] for item in parsed["product_data"]["standard_options"]] == [12000, 12000]
    assert parsed["warnings"] == []


def test_rule_mapping_supports_default_value_map_and_regex_all():
    row = pd.Series(
        {
            "상태": "Y",
            "상품코드": "1000000051",
            "자체상품코드": "JDM1000010",
            "상품명(기본)": "족집게",
            "판매가": 370,
            "이미지": "https://img.example/list.jpg",
            "PC쇼핑몰상세설명": "<p>detail</p>",
            "옵션/추가금액/옵션코드": "01) 평타입/0원/01_JDM1000010\n02) 뾰족타입/+100원/02_JDM1000010",
        }
    )
    combined = "옵션/추가금액/옵션코드"
    mapping = {
        "wholesale_status": {"source": "상태", "value_map": {"Y": "판매중"}},
        "wholesale_product_id": "상품코드",
        "product_code": "자체상품코드",
        "original_name": "상품명(기본)",
        "price_wholesale_raw": "판매가",
        "origin": {"default": "중국"},
        "image_list_1": "이미지",
        "image_detail": "PC쇼핑몰상세설명",
        "option_values_raw": {"source": combined, "pattern": r"\d+\)\s*([^/\n]+?)/", "regex_all": True},
        "option_price_deltas_raw": {"source": combined, "pattern": r"/([+-]?\d+)원/", "regex_all": True},
        "option_skus_raw": {"source": combined, "pattern": r"(?m)/([^/\n]+)$", "regex_all": True},
    }

    parsed = parse_wholesale_row(row, mapping)

    assert parsed["product_data"]["wholesale_status"] == "판매중"
    assert parsed["product_data"]["origin"] == "중국"
    assert parsed["product_data"]["option_variants"] == [
        {"name": "평타입", "price_wholesale": 370, "position": 1},
        {"name": "뾰족타입", "price_wholesale": 470, "position": 2},
    ]
    assert [item["option_sku"] for item in parsed["product_data"]["standard_options"]] == [
        "01_JDM1000010",
        "02_JDM1000010",
    ]
    assert parsed["warnings"] == []


def test_mapping_preview_normalizes_up_to_five_rows_and_sanitizes_rules():
    dataframe = pd.DataFrame([{"상품명": f"상품 {index}", "코드": f"P-{index}"} for index in range(6)])
    mapping, warnings = sanitize_column_mapping(
        {
            "original_name": "상품명",
            "product_code": "코드",
            "origin": {"default": "국내"},
            "unknown": "상품명",
            "wholesale_status": {"source": "상품명", "pattern": "("},
        },
        list(dataframe.columns),
    )
    preview, row_warnings = build_mapping_preview(dataframe, mapping)

    assert len(preview) == 5
    assert preview[0]["original_name"] == "상품 0"
    assert preview[0]["origin"] == "국내"
    assert any("unknown target" in warning for warning in warnings)
    assert any("invalid regex" in warning for warning in warnings)
    assert row_warnings


def test_parse_wholesale_row_suppresses_standard_options_when_option_price_is_invalid():
    row = pd.Series(
        {
            "상태": "정상",
            "제품번호": "12345",
            "상품코드": "ABC-001",
            "상품명": "테스트 상품",
            "옵션값": "블랙,L",
            "가격": "bad,13000",
            "원산지": "국내",
            "목록이미지1": "https://img.example/1.jpg",
            "상세이미지": "https://img.example/detail.jpg",
        }
    )

    parsed = parse_wholesale_row(row, {})

    assert parsed["product_data"]["option_variants"] == []
    assert parsed["product_data"]["standard_options"] == []
    assert parsed["warnings"] == [
        {
            "field": "price_wholesale_raw",
            "message": "One or more option prices could not be parsed.",
            "raw_value": "bad,13000",
        }
    ]


def test_merge_product_warnings_preserves_supplier_warnings_and_adds_processing_warnings():
    supplier_warning = {"field": "price_wholesale_raw", "message": "Required value is blank."}
    processing_warning = {"keyword": "브랜드", "reason": "trademark"}

    merged = merge_product_warnings(
        {"warnings": [supplier_warning], "supplier_warnings": [supplier_warning]},
        [processing_warning],
    )

    assert merged == {
        "warnings": [supplier_warning, processing_warning],
        "supplier_warnings": [supplier_warning],
        "processing_warnings": [processing_warning],
    }


def test_merge_product_warnings_keeps_supplier_warnings_when_processing_has_none():
    supplier_warning = {"field": "image_detail", "message": "Required value is blank."}

    merged = merge_product_warnings({"warnings": [supplier_warning]}, [])

    assert merged == {
        "warnings": [supplier_warning],
        "supplier_warnings": [supplier_warning],
    }


def test_standard_required_fields_include_origin_and_supplier_identity():
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


def test_build_option_display_name_joins_non_blank_values():
    option = {
        "option_value_1": "블랙",
        "option_value_2": "L",
        "option_value_3": "",
    }

    assert build_option_display_name(option) == "블랙 / L"


def test_build_option_display_name_ignores_nan_values():
    option = {
        "option_value_1": "블랙",
        "option_value_2": float("nan"),
        "option_value_3": None,
    }

    assert build_option_display_name(option) == "블랙"


def test_derive_option_price_delta_uses_option_supply_price_as_source():
    assert derive_option_price_delta(option_supply_price=13000, base_supply_price=12000) == 1000
    assert derive_option_price_delta(option_supply_price=12000, base_supply_price=12000) == 0
    assert derive_option_price_delta(option_supply_price=None, base_supply_price=12000) is None
    assert derive_option_price_delta(option_supply_price=13000, base_supply_price=None) is None
