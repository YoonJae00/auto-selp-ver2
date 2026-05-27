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


def _settings():
    return {
        "listing_defaults": {
            "smartstore": {"sellerManagementCode": "MAIN-SMART"},
            "coupang": {"sellerProductItemCodePrefix": "CP"},
        },
        "generation_rules": {
            "pricingPolicy": {
                "smartstore": _smartstore_pricing_policy(),
                "coupang": _coupang_pricing_policy(),
            }
        },
    }


def _error_codes(result):
    return sorted(error["code"] for error in result.validation_result.get("errors", []))


def test_smartstore_adapter_builds_payload_and_pricing_snapshot():
    result = SmartstoreAdapter().generate_draft(_source_snapshot(), _settings())

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
    result = CoupangAdapter().generate_draft(_source_snapshot(), _settings())

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

    result = CoupangAdapter().generate_draft(snapshot, _settings())

    assert result.validation_result == {"status": "valid"}
    assert len(result.generated_payload["items"]) == 1
    assert result.generated_payload["items"][0]["itemName"] == "브랜드 무선 선풍기 저소음"
    assert result.generated_payload["items"][0]["attributes"] == []


def test_missing_category_and_image_are_blocking_for_both_adapters():
    snapshot = _source_snapshot()
    snapshot["market_categories"]["smartstore"] = {"category_id": None}
    snapshot["market_categories"]["coupang"] = {"category_id": None}
    snapshot["images"]["list"] = []

    smartstore_result = SmartstoreAdapter().generate_draft(snapshot, _settings())
    coupang_result = CoupangAdapter().generate_draft(snapshot, _settings())

    assert "SMARTSTORE_MISSING_CATEGORY" in _error_codes(smartstore_result)
    assert "SMARTSTORE_MISSING_PRIMARY_IMAGE" in _error_codes(smartstore_result)
    assert smartstore_result.validation_result["status"] == "blocked"

    assert "COUPANG_MISSING_CATEGORY" in _error_codes(coupang_result)
    assert "COUPANG_MISSING_PRIMARY_IMAGE" in _error_codes(coupang_result)
    assert coupang_result.validation_result["status"] == "blocked"


def test_missing_and_invalid_pricing_policy_are_market_specific_blocks():
    settings_without_pricing = {
        "listing_defaults": _settings()["listing_defaults"],
        "generation_rules": {},
    }
    missing_policy_smartstore = SmartstoreAdapter().generate_draft(
        _source_snapshot(), settings_without_pricing
    )
    missing_policy_coupang = CoupangAdapter().generate_draft(
        _source_snapshot(), settings_without_pricing
    )
    assert _error_codes(missing_policy_smartstore) == [
        "SMARTSTORE_MISSING_PRICING_POLICY",
        "SMARTSTORE_MISSING_SALE_PRICE",
    ]
    assert _error_codes(missing_policy_coupang) == [
        "COUPANG_MISSING_PRICING_POLICY",
        "COUPANG_MISSING_SALE_PRICE",
    ]

    invalid_settings = _settings()
    invalid_settings["generation_rules"]["pricingPolicy"]["smartstore"] = {"version": "broken"}
    invalid_settings["generation_rules"]["pricingPolicy"]["coupang"] = {"version": "broken"}

    invalid_policy_smartstore = SmartstoreAdapter().generate_draft(_source_snapshot(), invalid_settings)
    invalid_policy_coupang = CoupangAdapter().generate_draft(_source_snapshot(), invalid_settings)
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
    settings_without_pricing = {
        "listing_defaults": _settings()["listing_defaults"],
        "generation_rules": {},
    }

    smartstore_result = SmartstoreAdapter().generate_draft(snapshot, settings_without_pricing)
    coupang_result = CoupangAdapter().generate_draft(snapshot, settings_without_pricing)

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
