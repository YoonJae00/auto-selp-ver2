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
        options = self._extract_options(source_snapshot)
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
            "optionInfo": {"optionCombinations": options},
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
