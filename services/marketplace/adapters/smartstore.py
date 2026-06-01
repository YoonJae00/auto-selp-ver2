from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.pricing import PricingPolicyError, calculate_proposed_price

from adapters.base import MarketplaceAdapter, build_validation_result
from schemas import DraftResult


class SmartstoreAdapter(MarketplaceAdapter):
    market_code = "smartstore"
    adapter_version = "smartstore-adapter:v1"
    title_recipe_version = "smartstore-title:v1"

    def generate_draft(
        self, source_snapshot: Mapping[str, Any], account_settings: Mapping[str, Any] | None
    ) -> DraftResult:
        title = self._compose_title(source_snapshot)
        category_id = self._extract_category_id(source_snapshot)
        primary_image_url = self._extract_primary_image(source_snapshot)
        optional_images = self._extract_optional_images(source_snapshot)
        detail_content = self._extract_detail_content(source_snapshot)
        origin = self._extract_origin(source_snapshot)
        standard_options = self._extract_standard_options(source_snapshot)
        option_info = (
            self._build_standard_option_info(standard_options)
            if standard_options
            else {"optionCombinations": self._extract_options(source_snapshot)}
        )
        cost_price = self._extract_cost_price(source_snapshot)
        listing_defaults = self._extract_listing_defaults(account_settings)

        pricing, pricing_invalid = self._resolve_pricing_policy(account_settings)
        pricing_output: dict[str, Any] | None = None
        pricing_error_code: str | None = None
        if pricing is None:
            pricing_error_code = (
                "SMARTSTORE_INVALID_PRICING_POLICY"
                if pricing_invalid
                else "SMARTSTORE_MISSING_PRICING_POLICY"
            )
        else:
            try:
                pricing_output = calculate_proposed_price(cost_price=cost_price, policy=pricing)
            except PricingPolicyError:
                pricing_error_code = "SMARTSTORE_INVALID_PRICING_POLICY"

        sale_price = pricing_output["proposedSalePrice"] if pricing_output else None
        expected_profit = pricing_output["expectedProfit"] if pricing_output else None
        expected_margin_rate = pricing_output["expectedMarginRate"] if pricing_output else None

        # Add attribute mapping consumption
        smartstore_category = source_snapshot.get("market_categories", {}).get("smartstore", {})
        mapped_attrs = smartstore_category.get("mapped_attributes", {}) if smartstore_category else {}
        
        detail_attribute = {
            "originAreaInfo": {"rawOrigin": origin},
            "optionInfo": option_info,
        }
        if mapped_attrs and mapped_attrs.get("naver_attributes"):
            detail_attribute["productAttributes"] = mapped_attrs["naver_attributes"]

        payload = {
            "originProduct": {
                "name": title,
                "leafCategoryId": category_id,
                "salePrice": sale_price,
                "images": {
                    "representativeImage": {"url": primary_image_url},
                    "optionalImages": [{"url": image_url} for image_url in optional_images],
                },
                "detailContent": detail_content,
                "detailAttribute": detail_attribute,
            },
            "smartstoreChannelProduct": listing_defaults,
            "pricing": pricing_output,
        }

        errors: list[dict[str, str]] = []
        if not category_id:
            errors.append(
                {
                    "code": "SMARTSTORE_MISSING_CATEGORY",
                    "message": "Smartstore category_id is required.",
                }
            )
        if not title:
            errors.append(
                {"code": "SMARTSTORE_MISSING_TITLE", "message": "Smartstore title is required."}
            )
        if not primary_image_url:
            errors.append(
                {
                    "code": "SMARTSTORE_MISSING_PRIMARY_IMAGE",
                    "message": "Smartstore primary image is required.",
                }
            )
        if sale_price is None:
            errors.append(
                {
                    "code": "SMARTSTORE_MISSING_SALE_PRICE",
                    "message": "Smartstore sale price is required.",
                }
            )
        if not origin:
            errors.append(
                {"code": "SMARTSTORE_MISSING_ORIGIN", "message": "Smartstore origin is required."}
            )
        if not detail_content:
            errors.append(
                {
                    "code": "SMARTSTORE_MISSING_DETAIL_CONTENT",
                    "message": "Smartstore detail content is required.",
                }
            )
        if pricing_error_code:
            errors.append(
                {
                    "code": pricing_error_code,
                    "message": "Smartstore pricing policy is missing or invalid.",
                }
            )

        return DraftResult(
            display_title=title or None,
            category_id=category_id,
            sale_price=sale_price,
            cost_price=cost_price,
            expected_profit=expected_profit,
            expected_margin_rate=expected_margin_rate,
            primary_image_url=primary_image_url,
            generated_payload=payload,
            validation_result=build_validation_result(errors=errors),
            adapter_version=self.adapter_version,
            recipe_versions={"title": self.title_recipe_version},
        )

    def _build_standard_option_info(self, standard_options: list[dict[str, Any]]) -> dict[str, Any]:
        group_names: list[str] = []
        combinations: list[dict[str, Any]] = []

        for option in standard_options:
            for index in range(1, 4):
                group_name = self._clean_str(option.get(f"option_group_{index}"))
                option_value = self._clean_str(option.get(f"option_value_{index}"))
                if group_name and option_value and group_name not in group_names:
                    group_names.append(group_name)

            combination: dict[str, Any] = {}
            for index in range(1, 4):
                option_value = self._clean_str(option.get(f"option_value_{index}"))
                if option_value:
                    combination[f"optionName{index}"] = option_value

            option_stock_quantity = option.get("option_stock_quantity")
            if isinstance(option_stock_quantity, int):
                combination["stockQuantity"] = option_stock_quantity

            option_price_delta = option.get("option_price_delta")
            if isinstance(option_price_delta, int):
                combination["price"] = option_price_delta

            combination["usable"] = option.get("option_usable", True) is not False

            option_sku = self._clean_str(option.get("option_sku"))
            if option_sku:
                combination["sellerManagerCode"] = option_sku

            combinations.append(combination)

        option_info: dict[str, Any] = {"optionCombinations": combinations}
        if group_names:
            option_info["optionCombinationGroupNames"] = group_names
        return option_info
