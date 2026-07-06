from __future__ import annotations

import asyncio

from app.analyzer.adapter_schema import FieldExtractor
from app.crawlers.yaml_adapter import YAMLAdapter


class _El:
    def __init__(self, attrs: dict[str, str]) -> None:
        self._attrs = attrs

    async def get_attribute(self, name: str) -> str | None:
        return self._attrs.get(name)


class _Page:
    def __init__(self, mapping: dict[str, list[_El]]) -> None:
        self._mapping = mapping

    async def query_selector_all(self, selector: str) -> list[_El]:
        return self._mapping.get(selector, [])

    async def query_selector(self, selector: str) -> _El | None:
        found = self._mapping.get(selector, [])
        return found[0] if found else None


def test_container_selector_falls_back_to_inner_imgs() -> None:
    # 사용자가 상세 이미지 영역 박스(div)를 선택한 경우: div에는 src가 없고 내부 img에 있음.
    page = _Page({
        "div.detail": [_El({})],
        "div.detail img": [
            _El({"src": "https://x.com/d1.jpg"}),
            _El({"data-src": "https://x.com/d2.jpg"}),
        ],
    })
    extractor = FieldExtractor(selector="div.detail", attribute="src", fallback_attribute="data-src", multiple=True)
    adapter = YAMLAdapter.__new__(YAMLAdapter)
    values = asyncio.run(adapter._extract_field(page, extractor))
    assert values == ["https://x.com/d1.jpg", "https://x.com/d2.jpg"]


def test_skip_first_drops_leading_images() -> None:
    # skip_first=1: 갤러리 맨 앞의 대표이미지 제외
    page = _Page({
        "img.gallery": [
            _El({"src": "https://x.com/main.jpg"}),
            _El({"src": "https://x.com/e1.jpg"}),
            _El({"src": "https://x.com/e2.jpg"}),
        ],
    })
    extractor = FieldExtractor(selector="img.gallery", attribute="src", multiple=True, skip_first=1)
    adapter = YAMLAdapter.__new__(YAMLAdapter)
    values = asyncio.run(adapter._extract_field(page, extractor))
    assert values == ["https://x.com/e1.jpg", "https://x.com/e2.jpg"]


def test_direct_img_selector_unchanged() -> None:
    page = _Page({"img.detail": [_El({"src": "https://x.com/d1.jpg"})]})
    extractor = FieldExtractor(selector="img.detail", attribute="src", multiple=True)
    adapter = YAMLAdapter.__new__(YAMLAdapter)
    values = asyncio.run(adapter._extract_field(page, extractor))
    assert values == ["https://x.com/d1.jpg"]
