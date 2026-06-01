from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
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
        standard_options = self._extract_standard_options(source_snapshot)
        options = standard_options or self._extract_options(source_snapshot)
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

        image_payload_template = []
        if primary_image_url:
            image_payload_template.append(
                {
                    "imageType": "REPRESENTATION",
                    "vendorPath": primary_image_url,
                    "imageOrder": 0,
                }
            )
        for index, optional_image_url in enumerate(optional_images, start=1):
            image_payload_template.append(
                {
                    "imageType": "DETAIL",
                    "vendorPath": optional_image_url,
                    "imageOrder": index,
                }
            )
        content_payload_template = [
            {
                "contentsType": "HTML",
                "contentDetails": [{"detailType": "TEXT", "content": detail_content}],
            }
        ]

        option_items = options or [{"name": title}]
        items = []
        for option in option_items:
            item_name = self._option_item_name(option) if isinstance(option, Mapping) else title
            if not item_name:
                item_name = title
            item_images = (
                self._build_standard_option_images(option, image_payload_template)
                if standard_options and isinstance(option, Mapping)
                else deepcopy(image_payload_template)
            )
            item_attributes = (
                self._build_standard_option_attributes(option)
                if standard_options and isinstance(option, Mapping)
                else ([{"attributeTypeName": "옵션", "attributeValueName": item_name}] if options else [])
            )
            item = {
                "itemName": item_name,
                "salePrice": self._option_sale_price(option, sale_price) if isinstance(option, Mapping) else sale_price,
                "images": item_images,
                "attributes": item_attributes,
                "contents": deepcopy(content_payload_template),
                "origin": origin,
            }
            if standard_options and isinstance(option, Mapping):
                option_sku = self._clean_str(option.get("option_sku"))
                if option_sku:
                    item["externalVendorSku"] = option_sku
                option_stock_quantity = option.get("option_stock_quantity")
                if isinstance(option_stock_quantity, int):
                    item["maximumBuyCount"] = option_stock_quantity
            items.append(item)

        payload = {
            "displayCategoryCode": category_id,
            "displayProductName": title,
            "sellerProductName": title,
            "items": items,
            "coupangProduct": listing_defaults,
            "pricing": pricing_output,
        }

        # Add product level and item level attributes consumption
        coupang_category = source_snapshot.get("market_categories", {}).get("coupang", {})
        mapped_attrs = coupang_category.get("mapped_attributes", {}) if coupang_category else {}
        
        if mapped_attrs and mapped_attrs.get("coupang_attributes"):
            payload["attributes"] = mapped_attrs["coupang_attributes"].get("product_attributes", [])
            
            item_attrs = mapped_attrs["coupang_attributes"].get("item_attributes", [])
            if item_attrs:
                for item in payload["items"]:
                    if "attributes" not in item:
                        item["attributes"] = []
                    item["attributes"].extend(item_attrs)

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

    def _option_item_name(self, option: Mapping[str, Any]) -> str:
        standard_name = self._clean_str(option.get("option_display_name"))
        if standard_name:
            return standard_name
        legacy_name = self._clean_str(option.get("name"))
        if legacy_name:
            return legacy_name
        option_sku = self._clean_str(option.get("option_sku"))
        return option_sku

    def _option_sale_price(self, option: Mapping[str, Any], fallback_sale_price: int | None) -> int | None:
        option_sale_price = option.get("option_sale_price")
        if isinstance(option_sale_price, int) and option_sale_price > 0:
            return option_sale_price
        return fallback_sale_price

    def _build_standard_option_images(
        self,
        option: Mapping[str, Any],
        fallback_images: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        option_images: list[dict[str, Any]] = []
        main_image = self._clean_str(option.get("option_main_image_url"))
        if main_image:
            option_images.append(
                {
                    "imageType": "REPRESENTATION",
                    "vendorPath": main_image,
                    "imageOrder": 0,
                }
            )

        extra_images = option.get("option_extra_image_urls")
        if isinstance(extra_images, list):
            for index, image_url_value in enumerate(extra_images, start=len(option_images)):
                image_url = self._clean_str(image_url_value)
                if image_url:
                    option_images.append(
                        {
                            "imageType": "DETAIL",
                            "vendorPath": image_url,
                            "imageOrder": index,
                        }
                    )

        return option_images or deepcopy(fallback_images)

    def _build_standard_option_attributes(self, option: Mapping[str, Any]) -> list[dict[str, str]]:
        attributes: list[dict[str, str]] = []
        for index in range(1, 4):
            group_name = self._clean_str(option.get(f"option_group_{index}"))
            option_value = self._clean_str(option.get(f"option_value_{index}"))
            if group_name and option_value:
                attributes.append(
                    {
                        "attributeTypeName": group_name,
                        "attributeValueName": option_value,
                    }
                )
        return attributes
