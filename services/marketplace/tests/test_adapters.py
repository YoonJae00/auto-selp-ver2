from adapters import CoupangAdapter, SmartstoreAdapter


def _smartstore_pricing_policy():
    return {
        "version": "smartstore-pricing:v1",
        "shippingCost": {"type": "fixed", "amount": 3000},
        "marketplaceFee": {"type": "percent_of_sale_price", "rate": 5.0},
        "advertisingCost": {"type": "percent_of_sale_price", "rate": 3.0},
        "otherCost": {"type": "fixed", "amount": 500},
        "targetMargin": {"type": "percent_of_sale_price", "rate": 25.0},
        "rounding": {"unit": 100, "mode": "ceil"},
    }


def _coupang_pricing_policy():
    return {
        "version": "coupang-pricing:v1",
        "shippingCost": {"type": "fixed", "amount": 0},
        "marketplaceFee": {"type": "percent_of_sale_price", "rate": 10.0},
        "advertisingCost": {"type": "percent_of_sale_price", "rate": 0.0},
        "otherCost": {"type": "fixed", "amount": 0},
        "targetMargin": {"type": "percent_of_sale_price", "rate": 20.0},
        "rounding": {"unit": 100, "mode": "ceil"},
    }


def _source_snapshot():
    return {
        "product_id": "8f19eb9d-c852-4ed1-8c41-ef4ece5be177",
        "version": "2026-05-27T12:30:45",
        "original_name": "원본 상품명",
        "refined_name": "브랜드 무선 선풍기",
        "brand_name": "브랜드",
        "keywords": ["저소음", "강풍"],
        "origin": "해외|아시아|중국",
        "price": {
            "wholesale": 8000,
            "retail": 18000,
            "minimum_selling": 15000,
        },
        "images": {
            "list": [
                "https://img.example/1.jpg",
                "https://img.example/2.jpg",
            ],
            "detail_content": "<img src='detail.jpg'>",
        },
        "options": [
            {"name": "L자형", "price_wholesale": 8000, "position": 1},
            {"name": "V자형", "price_wholesale": 9000, "position": 2},
        ],
        "market_categories": {
            "smartstore": {"category_id": "50000001"},
            "coupang": {"category_id": "12345"},
        },
    }


def _source_snapshot_with_standard_options():
    snapshot = _source_snapshot()
    snapshot["options"] = []
    snapshot["standard_options"] = [
        {
            "supplier_product_code": "P-100",
            "option_sku": "P-100-1",
            "option_type": "combination",
            "option_group_1": "색상",
            "option_value_1": "블랙",
            "option_group_2": "사이즈",
            "option_value_2": "L",
            "option_group_3": None,
            "option_value_3": None,
            "option_display_name": "블랙 / L",
            "option_supply_price": 8000,
            "option_sale_price": None,
            "option_price_delta": 0,
            "option_stock_quantity": 12,
            "option_status": "정상",
            "option_usable": True,
            "option_main_image_url": "https://img.example/black-l.jpg",
            "option_extra_image_urls": ["https://img.example/black-l-detail.jpg"],
            "option_position": 1,
            "raw_option_text": "블랙/L",
            "raw_option_metadata": {"source": "fixture"},
        },
        {
            "supplier_product_code": "P-100",
            "option_sku": "P-100-2",
            "option_type": "combination",
            "option_group_1": "색상",
            "option_value_1": "화이트",
            "option_group_2": "사이즈",
            "option_value_2": "M",
            "option_group_3": None,
            "option_value_3": None,
            "option_display_name": "화이트 / M",
            "option_supply_price": 9000,
            "option_sale_price": None,
            "option_price_delta": 1000,
            "option_stock_quantity": 5,
            "option_status": "정상",
            "option_usable": True,
            "option_main_image_url": None,
            "option_extra_image_urls": [],
            "option_position": 2,
            "raw_option_text": "화이트/M",
            "raw_option_metadata": {"source": "fixture"},
        },
    ]
    return snapshot


def _smartstore_settings(*, listing_defaults=None, pricing_policy=None):
    if listing_defaults is None:
        listing_defaults = {"sellerManagementCode": "MAIN-SMART"}
    if pricing_policy is None:
        pricing_policy = _smartstore_pricing_policy()

    return {
        "listing_defaults": listing_defaults,
        "generation_rules": {"pricingPolicy": pricing_policy},
    }


def _coupang_settings(*, listing_defaults=None, pricing_policy=None):
    if listing_defaults is None:
        listing_defaults = {"sellerProductItemCodePrefix": "CP"}
    if pricing_policy is None:
        pricing_policy = _coupang_pricing_policy()

    return {
        "listing_defaults": listing_defaults,
        "generation_rules": {"pricingPolicy": pricing_policy},
    }


def _error_codes(result):
    return sorted(error["code"] for error in result.validation_result.get("errors", []))


def test_smartstore_adapter_builds_payload_and_pricing_snapshot():
    result = SmartstoreAdapter().generate_draft(_source_snapshot(), _smartstore_settings())

    assert result.display_title == "브랜드 무선 선풍기 저소음"
    assert result.category_id == "50000001"
    assert result.sale_price == 17200
    assert result.cost_price == 8000
    assert result.expected_profit == 4324
    assert result.expected_margin_rate == 25.14
    assert result.primary_image_url == "https://img.example/1.jpg"
    assert result.adapter_version == "smartstore-adapter:v1"
    assert result.recipe_versions["title"] == "smartstore-title:v1"
    assert result.validation_result == {"status": "valid"}

    payload = result.generated_payload
    assert payload["originProduct"]["name"] == "브랜드 무선 선풍기 저소음"
    assert payload["originProduct"]["leafCategoryId"] == "50000001"
    assert payload["originProduct"]["salePrice"] == 17200
    assert payload["originProduct"]["images"]["representativeImage"]["url"] == "https://img.example/1.jpg"
    assert payload["originProduct"]["images"]["optionalImages"] == [
        {"url": "https://img.example/2.jpg"}
    ]
    assert payload["originProduct"]["detailContent"] == "<img src='detail.jpg'>"
    assert payload["originProduct"]["detailAttribute"]["originAreaInfo"]["rawOrigin"] == "해외|아시아|중국"
    assert payload["originProduct"]["detailAttribute"]["optionInfo"]["optionCombinations"] == [
        {"name": "L자형", "price_wholesale": 8000, "position": 1},
        {"name": "V자형", "price_wholesale": 9000, "position": 2},
    ]
    assert payload["smartstoreChannelProduct"] == {"sellerManagementCode": "MAIN-SMART"}
    assert payload["pricing"] == {
        "policyVersion": "smartstore-pricing:v1",
        "costPrice": 8000,
        "proposedSalePrice": 17200,
        "shippingCost": 3000,
        "marketplaceFee": 860,
        "advertisingCost": 516,
        "otherCost": 500,
        "expectedProfit": 4324,
        "expectedMarginRate": 25.14,
    }


def test_coupang_adapter_uses_market_specific_policy_and_keeps_item_assets():
    result = CoupangAdapter().generate_draft(_source_snapshot(), _coupang_settings())

    assert result.display_title == "브랜드 무선 선풍기 저소음"
    assert result.category_id == "12345"
    assert result.sale_price == 11500
    assert result.cost_price == 8000
    assert result.expected_profit == 2350
    assert result.expected_margin_rate == 20.43
    assert result.primary_image_url == "https://img.example/1.jpg"
    assert result.adapter_version == "coupang-adapter:v1"
    assert result.recipe_versions["title"] == "coupang-title:v1"
    assert result.validation_result == {"status": "valid"}

    payload = result.generated_payload
    assert payload["displayCategoryCode"] == "12345"
    assert payload["displayProductName"] == "브랜드 무선 선풍기 저소음"
    assert payload["sellerProductName"] == "브랜드 무선 선풍기 저소음"
    assert payload["items"][0]["itemName"] == "L자형"
    assert payload["items"][0]["salePrice"] == 11500
    assert payload["items"][0]["images"][0]["imageOrder"] == 0
    assert payload["items"][0]["images"][0]["imageType"] == "REPRESENTATION"
    assert payload["items"][0]["images"][0]["vendorPath"] == "https://img.example/1.jpg"
    assert payload["items"][0]["images"][1]["imageType"] == "DETAIL"
    assert payload["items"][0]["contents"][0]["contentsType"] == "HTML"
    assert payload["items"][0]["contents"][0]["contentDetails"][0]["detailType"] == "TEXT"
    assert payload["items"][0]["contents"][0]["contentDetails"][0]["content"] == "<img src='detail.jpg'>"
    assert payload["items"][0]["attributes"] == [{"attributeTypeName": "옵션", "attributeValueName": "L자형"}]
    assert payload["pricing"]["policyVersion"] == "coupang-pricing:v1"


def test_coupang_adapter_falls_back_to_single_item_when_source_has_no_options():
    snapshot = _source_snapshot()
    snapshot["options"] = []

    result = CoupangAdapter().generate_draft(snapshot, _coupang_settings())

    assert result.validation_result == {"status": "valid"}
    assert len(result.generated_payload["items"]) == 1
    assert result.generated_payload["items"][0]["itemName"] == "브랜드 무선 선풍기 저소음"
    assert result.generated_payload["items"][0]["attributes"] == []


def test_smartstore_adapter_prefers_standard_options_for_option_info():
    result = SmartstoreAdapter().generate_draft(
        _source_snapshot_with_standard_options(), _smartstore_settings()
    )

    option_info = result.generated_payload["originProduct"]["detailAttribute"]["optionInfo"]

    assert option_info["optionCombinationGroupNames"] == ["색상", "사이즈"]
    assert option_info["optionCombinations"] == [
        {
            "optionName1": "블랙",
            "optionName2": "L",
            "stockQuantity": 12,
            "price": 0,
            "usable": True,
            "sellerManagerCode": "P-100-1",
        },
        {
            "optionName1": "화이트",
            "optionName2": "M",
            "stockQuantity": 5,
            "price": 1000,
            "usable": True,
            "sellerManagerCode": "P-100-2",
        },
    ]


def test_coupang_adapter_prefers_standard_options_for_items_and_images():
    result = CoupangAdapter().generate_draft(
        _source_snapshot_with_standard_options(), _coupang_settings()
    )

    first_item = result.generated_payload["items"][0]
    second_item = result.generated_payload["items"][1]

    assert first_item["itemName"] == "블랙 / L"
    assert first_item["externalVendorSku"] == "P-100-1"
    assert first_item["maximumBuyCount"] == 12
    assert first_item["images"] == [
        {
            "imageType": "REPRESENTATION",
            "vendorPath": "https://img.example/black-l.jpg",
            "imageOrder": 0,
        },
        {
            "imageType": "DETAIL",
            "vendorPath": "https://img.example/black-l-detail.jpg",
            "imageOrder": 1,
        },
    ]
    assert first_item["attributes"] == [
        {"attributeTypeName": "색상", "attributeValueName": "블랙"},
        {"attributeTypeName": "사이즈", "attributeValueName": "L"},
    ]
    assert second_item["itemName"] == "화이트 / M"
    assert second_item["images"][0]["vendorPath"] == "https://img.example/1.jpg"


def test_missing_category_and_image_are_blocking_for_both_adapters():
    snapshot = _source_snapshot()
    snapshot["market_categories"]["smartstore"] = {"category_id": None}
    snapshot["market_categories"]["coupang"] = {"category_id": None}
    snapshot["images"]["list"] = []

    smartstore_result = SmartstoreAdapter().generate_draft(snapshot, _smartstore_settings())
    coupang_result = CoupangAdapter().generate_draft(snapshot, _coupang_settings())

    assert "SMARTSTORE_MISSING_CATEGORY" in _error_codes(smartstore_result)
    assert "SMARTSTORE_MISSING_PRIMARY_IMAGE" in _error_codes(smartstore_result)
    assert smartstore_result.validation_result["status"] == "blocked"

    assert "COUPANG_MISSING_CATEGORY" in _error_codes(coupang_result)
    assert "COUPANG_MISSING_PRIMARY_IMAGE" in _error_codes(coupang_result)
    assert coupang_result.validation_result["status"] == "blocked"


def test_missing_and_invalid_pricing_policy_are_market_specific_blocks():
    settings_without_pricing_smartstore = {"listing_defaults": _smartstore_settings()["listing_defaults"], "generation_rules": {}}
    settings_without_pricing_coupang = {"listing_defaults": _coupang_settings()["listing_defaults"], "generation_rules": {}}
    missing_policy_smartstore = SmartstoreAdapter().generate_draft(
        _source_snapshot(), settings_without_pricing_smartstore
    )
    missing_policy_coupang = CoupangAdapter().generate_draft(
        _source_snapshot(), settings_without_pricing_coupang
    )
    assert _error_codes(missing_policy_smartstore) == [
        "SMARTSTORE_MISSING_PRICING_POLICY",
        "SMARTSTORE_MISSING_SALE_PRICE",
    ]
    assert _error_codes(missing_policy_coupang) == [
        "COUPANG_MISSING_PRICING_POLICY",
        "COUPANG_MISSING_SALE_PRICE",
    ]

    invalid_settings_smartstore = _smartstore_settings(pricing_policy={"version": "broken"})
    invalid_settings_coupang = _coupang_settings(pricing_policy={"version": "broken"})

    invalid_policy_smartstore = SmartstoreAdapter().generate_draft(
        _source_snapshot(), invalid_settings_smartstore
    )
    invalid_policy_coupang = CoupangAdapter().generate_draft(
        _source_snapshot(), invalid_settings_coupang
    )
    assert _error_codes(invalid_policy_smartstore) == [
        "SMARTSTORE_INVALID_PRICING_POLICY",
        "SMARTSTORE_MISSING_SALE_PRICE",
    ]
    assert _error_codes(invalid_policy_coupang) == [
        "COUPANG_INVALID_PRICING_POLICY",
        "COUPANG_MISSING_SALE_PRICE",
    ]


def test_pricing_errors_append_to_existing_blocking_errors_for_both_adapters():
    snapshot = _source_snapshot()
    snapshot["market_categories"]["smartstore"] = {"category_id": None}
    snapshot["market_categories"]["coupang"] = {"category_id": None}
    snapshot["images"]["list"] = []
    settings_without_pricing_smartstore = {"listing_defaults": _smartstore_settings()["listing_defaults"], "generation_rules": {}}
    settings_without_pricing_coupang = {"listing_defaults": _coupang_settings()["listing_defaults"], "generation_rules": {}}

    smartstore_result = SmartstoreAdapter().generate_draft(snapshot, settings_without_pricing_smartstore)
    coupang_result = CoupangAdapter().generate_draft(snapshot, settings_without_pricing_coupang)

    assert _error_codes(smartstore_result) == [
        "SMARTSTORE_MISSING_CATEGORY",
        "SMARTSTORE_MISSING_PRICING_POLICY",
        "SMARTSTORE_MISSING_PRIMARY_IMAGE",
        "SMARTSTORE_MISSING_SALE_PRICE",
    ]
    assert _error_codes(coupang_result) == [
        "COUPANG_MISSING_CATEGORY",
        "COUPANG_MISSING_PRICING_POLICY",
        "COUPANG_MISSING_PRIMARY_IMAGE",
        "COUPANG_MISSING_SALE_PRICE",
    ]


def test_image_urls_are_normalized_once_with_blank_leading_slots():
    snapshot = _source_snapshot()
    snapshot["images"]["list"] = [
        " ",
        "\n",
        " https://img.example/normalized-1.jpg ",
        "",
        "\t",
        "https://img.example/normalized-2.jpg",
    ]

    smartstore_result = SmartstoreAdapter().generate_draft(snapshot, _smartstore_settings())
    coupang_result = CoupangAdapter().generate_draft(snapshot, _coupang_settings())

    smartstore_images = smartstore_result.generated_payload["originProduct"]["images"]
    assert smartstore_images["representativeImage"]["url"] == "https://img.example/normalized-1.jpg"
    assert smartstore_images["optionalImages"] == [{"url": "https://img.example/normalized-2.jpg"}]

    coupang_images = coupang_result.generated_payload["items"][0]["images"]
    assert [image["vendorPath"] for image in coupang_images] == [
        "https://img.example/normalized-1.jpg",
        "https://img.example/normalized-2.jpg",
    ]


def test_generated_payload_keeps_detached_nested_option_data_from_source_snapshot():
    snapshot = _source_snapshot()

    result = SmartstoreAdapter().generate_draft(snapshot, _smartstore_settings())
    payload_options = result.generated_payload["originProduct"]["detailAttribute"]["optionInfo"][
        "optionCombinations"
    ]

    snapshot["options"][0]["name"] = "MUTATED"
    snapshot["options"][0]["position"] = 999

    assert payload_options[0] == {"name": "L자형", "price_wholesale": 8000, "position": 1}


def test_coupang_generated_items_do_not_share_mutable_image_and_content_collections():
    result = CoupangAdapter().generate_draft(_source_snapshot(), _coupang_settings())
    first_item = result.generated_payload["items"][0]
    second_item = result.generated_payload["items"][1]

    first_item["images"][0]["vendorPath"] = "https://img.example/mutated.jpg"
    first_item["contents"][0]["contentDetails"][0]["content"] = "mutated-content"

    assert second_item["images"][0]["vendorPath"] == "https://img.example/1.jpg"
    assert second_item["contents"][0]["contentDetails"][0]["content"] == "<img src='detail.jpg'>"


def test_nested_listing_defaults_are_preserved_in_payload_and_detached_from_source_mutation():
    settings = _smartstore_settings(
        listing_defaults={
            "sellerManagementCode": "MAIN-SMART",
            "delivery": {"templateId": "DLV-1", "bundle": {"enabled": True}},
            "claim": {"returnCenterCode": "RET-1"},
            "metadata": 7,
        }
    )

    result = SmartstoreAdapter().generate_draft(_source_snapshot(), settings)
    channel_payload = result.generated_payload["smartstoreChannelProduct"]

    settings["listing_defaults"]["delivery"]["bundle"]["enabled"] = False
    settings["listing_defaults"]["claim"]["returnCenterCode"] = "MUTATED"
    settings["listing_defaults"]["metadata"] = 0

    assert channel_payload == {
        "sellerManagementCode": "MAIN-SMART",
        "delivery": {"templateId": "DLV-1", "bundle": {"enabled": True}},
        "claim": {"returnCenterCode": "RET-1"},
        "metadata": 7,
    }


def test_namespaced_pricing_policy_cannot_be_borrowed_by_current_adapter():
    settings = _smartstore_settings(pricing_policy={"future-market": _smartstore_pricing_policy()})

    result = SmartstoreAdapter().generate_draft(_source_snapshot(), settings)

    assert _error_codes(result) == [
        "SMARTSTORE_MISSING_PRICING_POLICY",
        "SMARTSTORE_MISSING_SALE_PRICE",
    ]


def test_market_keyed_pricing_policy_map_is_not_supported_for_single_account_settings():
    settings = _smartstore_settings(pricing_policy={"smartstore": _smartstore_pricing_policy()})

    result = SmartstoreAdapter().generate_draft(_source_snapshot(), settings)

    assert _error_codes(result) == [
        "SMARTSTORE_MISSING_PRICING_POLICY",
        "SMARTSTORE_MISSING_SALE_PRICE",
    ]


def test_smartstore_adapter_consumes_attributes():
    from adapters.smartstore import SmartstoreAdapter
    adapter = SmartstoreAdapter()
    snapshot = {
        "product_id": "8f19eb9d-c852-4ed1-8c41-ef4ece5be177",
        "version": "2026-05-27T12:30:45",
        "original_name": "원본",
        "refined_name": "정제",
        "brand_name": "브랜드",
        "keywords": [],
        "origin": "해외|아시아|중국",
        "price": {"wholesale": 8000, "retail": 18000, "minimum_selling": 15000},
        "images": {"list": ["https://img.example/1.jpg"], "detail_content": ""},
        "options": [],
        "market_categories": {
            "smartstore": {
                "category_id": "50000001",
                "mapped_attributes": {
                    "naver_attributes": [{"attributeSeq": 1, "attributeValueSeq": 2}]
                }
            }
        }
    }
    result = adapter.generate_draft(snapshot, _smartstore_settings())
    
    assert "productAttributes" in result.generated_payload["originProduct"]["detailAttribute"]
    assert result.generated_payload["originProduct"]["detailAttribute"]["productAttributes"][0]["attributeSeq"] == 1


def test_coupang_adapter_consumes_attributes():
    from adapters.coupang import CoupangAdapter
    adapter = CoupangAdapter()
    snapshot = {
        "product_id": "8f19eb9d-c852-4ed1-8c41-ef4ece5be177",
        "version": "2026-05-27T12:30:45",
        "original_name": "원본",
        "refined_name": "정제",
        "brand_name": "브랜드",
        "keywords": [],
        "origin": "해외|아시아|중국",
        "price": {"wholesale": 8000, "retail": 18000, "minimum_selling": 15000},
        "images": {"list": ["https://img.example/1.jpg"], "detail_content": ""},
        "options": [],
        "market_categories": {
            "coupang": {
                "category_id": "12345",
                "mapped_attributes": {
                    "coupang_attributes": {
                        "product_attributes": [{"attributeTypeName": "브랜드", "attributeValueName": "우리브랜드"}],
                        "item_attributes": [{"attributeTypeName": "색상", "attributeValueName": "레드"}]
                    }
                }
            }
        }
    }
    result = adapter.generate_draft(snapshot, _coupang_settings())
    
    payload = result.generated_payload
    assert payload["attributes"] == [{"attributeTypeName": "브랜드", "attributeValueName": "우리브랜드"}]
    assert payload["items"][0]["attributes"][0] == {"attributeTypeName": "색상", "attributeValueName": "레드"}
