from __future__ import annotations

import pytest

from app.analyzer.adapter_schema import FieldExtractor
from app.analyzer.site_probe import normalize_sample_products
from app.crawlers.yaml_adapter import YAMLAdapter, _image_csv, _map_supplier_status, _status_from_maxq_value, _supported_image_url


class _FakeElement:
    def __init__(self, text: str = "", attrs: dict[str, str] | None = None) -> None:
        self.text = text
        self.attrs = attrs or {}

    async def inner_text(self) -> str:
        return self.text

    async def inner_html(self) -> str:
        return self.text

    async def get_attribute(self, name: str) -> str | None:
        return self.attrs.get(name)


class _FakePage:
    def __init__(self, elements: dict[str, _FakeElement | None]) -> None:
        self.elements = elements

    async def query_selector(self, selector: str):
        return self.elements.get(selector)

    async def query_selector_all(self, selector: str):
        value = self.elements.get(selector)
        return [value] if value else []


def test_status_from_maxq_value() -> None:
    assert _status_from_maxq_value("0") == "sold_out"
    assert _status_from_maxq_value("12") == "available"
    assert _status_from_maxq_value("") is None
    assert _status_from_maxq_value(None) is None


def test_status_default_avoids_false_available_when_default_not_available() -> None:
    assert _map_supplier_status(None, {}, "available") == "available"
    assert _map_supplier_status(None, {}, "sold_out") == "unknown"
    assert _map_supplier_status("품절", {"품절": "sold_out"}, "available") == "sold_out"


def test_canonical_status_passes_through_before_mapping_or_default() -> None:
    assert _map_supplier_status("sold_out", {}, "available") == "sold_out"
    assert _map_supplier_status("available", {}, "sold_out") == "available"
    assert _map_supplier_status("unknown", {"unknown": "available"}, "sold_out") == "unknown"
    assert _map_supplier_status(" stopped ", {}, "available") == "stopped"


def test_supported_image_url_allows_selected_formats_with_query() -> None:
    assert _supported_image_url("https://img.test/a.JPG?x=1") == "https://img.test/a.JPG?x=1"
    assert _supported_image_url("/img/a.jpeg#v") == "/img/a.jpeg#v"
    assert _supported_image_url("/img/a.png") == "/img/a.png"
    assert _supported_image_url("/img/a.webp") == "/img/a.webp"
    assert _supported_image_url("/img/a.gif") is None
    assert _supported_image_url("/img/no-extension") is None


def test_image_csv_filters_and_joins_supported_images() -> None:
    assert _image_csv(["/d/1.jpg", "/d/2.webp?x=1", "/d/3.gif", None]) == "/d/1.jpg,/d/2.webp?x=1"
    assert _image_csv("/d/one.png") == "/d/one.png"
    assert _image_csv(["/d/no-extension"]) is None


@pytest.mark.asyncio
async def test_extract_field_prefers_selector_before_fallback_from() -> None:
    adapter = YAMLAdapter.__new__(YAMLAdapter)
    page = _FakePage({".status": _FakeElement("판매중"), "input[name='maxq']": _FakeElement(attrs={"value": "0"})})
    extractor = FieldExtractor(selector=".status", fallback_from="maxq")

    assert await adapter._extract_field(page, extractor) == "판매중"


@pytest.mark.asyncio
async def test_extract_field_uses_fallback_from_when_selector_empty() -> None:
    adapter = YAMLAdapter.__new__(YAMLAdapter)
    page = _FakePage({".status": _FakeElement(""), "input[name='maxq']": _FakeElement(attrs={"value": "0"})})
    extractor = FieldExtractor(selector=".status", fallback_from="maxq")

    assert await adapter._extract_field(page, extractor) == "sold_out"


def test_normalize_sample_products_deduplicates_and_prefers_quality() -> None:
    products = [
        {"url": "/p/1", "name": "", "image_url": ""},
        {"url": "/p/2", "name": "좋은상품", "image_url": "/img.jpg"},
        {"url": "https://example.com/p/1", "name": "중복상품", "image_url": "/a.jpg"},
    ]
    normalized, links = normalize_sample_products("https://example.com/list", products, ["/p/2", "/p/3"])

    assert links == [
        "https://example.com/p/2",
        "https://example.com/p/1",
        "https://example.com/p/3",
    ]
    assert normalized[0]["name"] == "좋은상품"
    assert normalized[0]["image_url"] == "https://example.com/img.jpg"
