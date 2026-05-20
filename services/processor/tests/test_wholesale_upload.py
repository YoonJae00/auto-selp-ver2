import pandas as pd

from utils.wholesale_upload import (
    REQUIRED_WHOLESALE_FIELDS,
    build_images_list,
    parse_int_price,
    parse_option_variants,
    parse_wholesale_row,
    validate_required_mappings,
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


def test_parse_int_price_handles_numeric_formatting():
    assert parse_int_price("2,640원") == 2640
    assert parse_int_price(" 2820.0 ") == 2820
    assert parse_int_price("") is None
    assert parse_int_price(None) is None


def test_parse_option_variants_pairs_options_with_prices_and_uses_first_price():
    result = parse_option_variants("L자형,V자형", "2640,2820")
    assert result["price_wholesale"] == 2640
    assert result["option_variants"] == [
        {"name": "L자형", "price_wholesale": 2640, "position": 1},
        {"name": "V자형", "price_wholesale": 2820, "position": 2},
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


def test_parse_option_variants_warns_on_count_mismatch():
    result = parse_option_variants("L자형,V자형", "2640")
    assert result["price_wholesale"] == 2640
    assert result["option_variants"] == []
    assert result["warnings"] == [
        {
            "field": "option_variants",
            "message": "Option count and price count differ.",
            "option_count": 2,
            "price_count": 1,
        }
    ]


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
