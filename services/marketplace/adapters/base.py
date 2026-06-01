from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from schemas import DraftResult


def build_validation_result(
    *, errors: list[dict[str, str]] | None = None, warnings: list[dict[str, str]] | None = None
) -> dict[str, Any]:
    if errors:
        return {"status": "blocked", "errors": errors}
    if warnings:
        return {"status": "warning", "warnings": warnings}
    return {"status": "valid"}


class MarketplaceAdapter(ABC):
    market_code: str
    adapter_version: str
    title_recipe_version: str

    @abstractmethod
    def generate_draft(
        self, source_snapshot: Mapping[str, Any], account_settings: Mapping[str, Any] | None
    ) -> DraftResult:
        raise NotImplementedError

    def build_draft(
        self,
        *,
        source_snapshot: Mapping[str, Any],
        account_settings: Mapping[str, Any] | None,
    ) -> DraftResult:
        return self.generate_draft(source_snapshot, account_settings)

    def _compose_title(self, source_snapshot: Mapping[str, Any]) -> str:
        brand_name = self._clean_str(source_snapshot.get("brand_name"))
        refined_name = self._clean_str(source_snapshot.get("refined_name"))
        keywords = source_snapshot.get("keywords")
        first_keyword = ""
        if isinstance(keywords, list):
            for raw_keyword in keywords:
                keyword = self._clean_str(raw_keyword)
                if keyword:
                    first_keyword = keyword
                    break

        parts: list[str] = []
        if brand_name and refined_name:
            if brand_name in refined_name:
                parts.append(refined_name)
            else:
                parts.extend([brand_name, refined_name])
        elif brand_name:
            parts.append(brand_name)
        elif refined_name:
            parts.append(refined_name)

        if first_keyword:
            current_title = " ".join(parts)
            if first_keyword not in current_title:
                parts.append(first_keyword)
        return " ".join(part for part in parts if part).strip()

    def _extract_category_id(self, source_snapshot: Mapping[str, Any]) -> str | None:
        market_categories = source_snapshot.get("market_categories")
        if not isinstance(market_categories, Mapping):
            return None
        category_info = market_categories.get(self.market_code)
        if not isinstance(category_info, Mapping):
            return None
        category_id = category_info.get("category_id")
        category = self._clean_str(category_id)
        return category or None

    def _extract_primary_image(self, source_snapshot: Mapping[str, Any]) -> str | None:
        normalized_urls = self._extract_normalized_image_urls(source_snapshot)
        return normalized_urls[0] if normalized_urls else None

    def _extract_optional_images(self, source_snapshot: Mapping[str, Any]) -> list[str]:
        normalized_urls = self._extract_normalized_image_urls(source_snapshot)
        return normalized_urls[1:]

    def _extract_normalized_image_urls(self, source_snapshot: Mapping[str, Any]) -> list[str]:
        images = source_snapshot.get("images")
        if not isinstance(images, Mapping):
            return []
        image_list = images.get("list")
        if not isinstance(image_list, list):
            return []
        urls: list[str] = []
        for image in image_list:
            image_url = self._clean_str(image)
            if image_url:
                urls.append(image_url)
        return urls

    def _extract_detail_content(self, source_snapshot: Mapping[str, Any]) -> str | None:
        images = source_snapshot.get("images")
        if not isinstance(images, Mapping):
            return None
        detail_content = self._clean_str(images.get("detail_content"))
        return detail_content or None

    def _extract_origin(self, source_snapshot: Mapping[str, Any]) -> str | None:
        origin = self._clean_str(source_snapshot.get("origin"))
        return origin or None

    def _extract_options(self, source_snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
        options = source_snapshot.get("options")
        if not isinstance(options, list):
            return []
        return [deepcopy(dict(option)) for option in options if isinstance(option, Mapping)]

    def _extract_standard_options(self, source_snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
        standard_options = source_snapshot.get("standard_options")
        if not isinstance(standard_options, list):
            return []
        return [
            deepcopy(dict(option))
            for option in standard_options
            if isinstance(option, Mapping) and option.get("option_usable", True) is not False
        ]

    def _extract_cost_price(self, source_snapshot: Mapping[str, Any]) -> int | None:
        price = source_snapshot.get("price")
        if not isinstance(price, Mapping):
            return None
        wholesale = price.get("wholesale")
        if isinstance(wholesale, int) and wholesale > 0:
            return wholesale
        return None

    def _extract_listing_defaults(self, account_settings: Mapping[str, Any] | None) -> dict[str, Any]:
        if not isinstance(account_settings, Mapping):
            return {}
        listing_defaults = account_settings.get("listing_defaults")
        if not isinstance(listing_defaults, Mapping):
            return {}
        return deepcopy(dict(listing_defaults))

    def _resolve_pricing_policy(
        self,
        account_settings: Mapping[str, Any] | None,
    ) -> tuple[dict[str, Any] | None, bool]:
        if not isinstance(account_settings, Mapping):
            return None, False
        generation_rules = account_settings.get("generation_rules")
        if not isinstance(generation_rules, Mapping):
            return None, False
        pricing_policy = generation_rules.get("pricingPolicy")
        if pricing_policy is None:
            return None, False
        if not isinstance(pricing_policy, Mapping):
            return None, True

        if self._has_unscoped_pricing_keys(pricing_policy):
            return deepcopy(dict(pricing_policy)), False

        if self._values_are_all_mappings(pricing_policy):
            return None, False

        if pricing_policy:
            return None, True
        return None, False

    @staticmethod
    def _values_are_all_mappings(values_map: Mapping[str, Any]) -> bool:
        values = list(values_map.values())
        return bool(values) and all(isinstance(value, Mapping) for value in values)

    @staticmethod
    def _has_unscoped_pricing_keys(pricing_policy: Mapping[str, Any]) -> bool:
        computational_keys = {"shippingCost", "marketplaceFee", "targetMargin", "rounding"}
        return any(key in pricing_policy for key in computational_keys)

    @staticmethod
    def _clean_str(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        return ""
