from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.pricing import PricingPolicyError, calculate_proposed_price

from adapters.base import MarketplaceAdapter, build_validation_result
from schemas import DraftResult


class CoupangAdapter(MarketplaceAdapter):
    market_code = "coupang"
    adapter_version = "coupang-adapter:v1"
    title_recipe_version = "coupang-title:v1"

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
                "COUPANG_INVALID_PRICING_POLICY"
                if pricing_invalid
                else "COUPANG_MISSING_PRICING_POLICY"
            )
        else:
            try:
                pricing_output = calculate_proposed_price(cost_price=cost_price, policy=pricing)
            except PricingPolicyError:
                pricing_error_code = "COUPANG_INVALID_PRICING_POLICY"

        sale_price = pricing_output["proposedSalePrice"] if pricing_output else None
        expected_profit = pricing_output["expectedProfit"] if pricing_output else None
        expected_margin_rate = pricing_output["expectedMarginRate"] if pricing_output else None

        image_payload = []
        if primary_image_url:
            image_payload.append(
                {
                    "imageType": "REPRESENTATION",
                    "vendorPath": primary_image_url,
                    "imageOrder": 0,
                }
            )
        for index, optional_image_url in enumerate(optional_images, start=1):
            image_payload.append(
                {
                    "imageType": "DETAIL",
                    "vendorPath": optional_image_url,
                    "imageOrder": index,
                }
            )

        option_items = options or [{"name": title}]
        items = []
        for option in option_items:
            item_name = self._clean_str(option.get("name")) if isinstance(option, Mapping) else title
            if not item_name:
                item_name = title
            item = {
                "itemName": item_name,
                "salePrice": sale_price,
                "images": image_payload,
                "attributes": (
                    [{"attributeTypeName": "옵션", "attributeValueName": item_name}] if options else []
                ),
                "contents": [
                    {
                        "contentsType": "HTML",
                        "contentDetails": [{"detailType": "TEXT", "content": detail_content}],
                    }
                ],
                "origin": origin,
            }
            items.append(item)

        payload = {
            "displayCategoryCode": category_id,
            "displayProductName": title,
            "sellerProductName": title,
            "items": items,
            "coupangProduct": listing_defaults,
            "pricing": pricing_output,
        }

        errors: list[dict[str, str]] = []
        if not category_id:
            errors.append(
                {"code": "COUPANG_MISSING_CATEGORY", "message": "Coupang category_id is required."}
            )
        if not title:
            errors.append({"code": "COUPANG_MISSING_TITLE", "message": "Coupang title is required."})
        if not primary_image_url:
            errors.append(
                {
                    "code": "COUPANG_MISSING_PRIMARY_IMAGE",
                    "message": "Coupang primary image is required.",
                }
            )
        if sale_price is None:
            errors.append(
                {"code": "COUPANG_MISSING_SALE_PRICE", "message": "Coupang sale price is required."}
            )
        if not origin:
            errors.append({"code": "COUPANG_MISSING_ORIGIN", "message": "Coupang origin is required."})
        if not detail_content:
            errors.append(
                {
                    "code": "COUPANG_MISSING_DETAIL_CONTENT",
                    "message": "Coupang detail content is required.",
                }
            )
        if pricing_error_code:
            errors.append(
                {
                    "code": pricing_error_code,
                    "message": "Coupang pricing policy is missing or invalid.",
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
