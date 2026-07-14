from __future__ import annotations

import asyncio

import pytest

from app.analyzer.adapter_schema import FieldExtractor
from app.crawlers.yaml_adapter import YAMLAdapter, collect_detail_images


# 상세 이미지 수집은 <img>의 렌더 크기를 브라우저에서 재서 버튼/아이콘을 거르므로 실제 브라우저가 필요.
# 앱과 동일하게 시스템 Chrome(channel="chrome") 사용, 없으면 skip.
async def _run_on_html(html: str, fn):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(channel="chrome")
        except Exception:
            try:
                browser = await p.chromium.launch()
            except Exception as exc:  # noqa: BLE001
                pytest.skip(f"no browser available: {exc}")
        page = await browser.new_page()
        try:
            await page.set_content(f"<!doctype html><html><body>{html}</body></html>")
            return await fn(page)
        finally:
            await browser.close()


def _extract(html: str, extractor: FieldExtractor):
    adapter = YAMLAdapter.__new__(YAMLAdapter)
    return asyncio.run(_run_on_html(html, lambda page: adapter._extract_field(page, extractor)))


def test_container_selector_falls_back_to_inner_imgs() -> None:
    # 사용자가 상세 이미지 영역 박스(div)를 선택: div엔 src 없고 내부 큰 img에 있음.
    html = """
      <div class="detail">
        <img src="/d1.jpg" width="600" height="800">
        <img data-src="/d2.jpg" width="700" height="900">
      </div>
    """
    extractor = FieldExtractor(selector="div.detail", attribute="src", fallback_attribute="data-src", multiple=True)
    assert _extract(html, extractor) == ["/d1.jpg", "/d2.jpg"]


def test_buttons_and_icons_dropped_by_size() -> None:
    # 핵심: 큰 상세 이미지만 남고 확대보기/PREV/NEXT 버튼·화살표(작은 img)는 제외.
    html = """
      <div class="detail">
        <img src="/big1.jpg" width="600" height="800">
        <a href="#"><img src="/prev.gif" width="30" height="20"></a>
        <a href="#"><img src="/next.gif" width="30" height="20"></a>
        <img src="/zoom_btn.jpg" width="50" height="18">
        <img src="/big2.jpg" width="700" height="900">
      </div>
    """
    extractor = FieldExtractor(selector="div.detail", attribute="src", multiple=True)
    assert _extract(html, extractor) == ["/big1.jpg", "/big2.jpg"]


def test_quickmenu_icons_dropped_by_src_token() -> None:
    # 사이드바 퀵메뉴 아이콘/버튼(품절리스트·엑셀주문·적립금충전 등)은 세로로 길어 크기 필터를
    # 통과할 수 있으나 파일명 토큰(btn_/quick/icon)으로 제외되고, 진짜 상세 이미지만 남아야 한다.
    html = """
      <div class="detail">
        <img src="/big1.jpg" width="600" height="800">
        <img src="/btn_excel_order.png" width="120" height="400">
        <img src="/quick_soldout.png" width="90" height="400">
        <img src="/sidebar/icon_cash.png" width="80" height="400">
        <img src="/big2.jpg" width="700" height="900">
      </div>
    """
    extractor = FieldExtractor(selector="div.detail", attribute="src", multiple=True)
    assert _extract(html, extractor) == ["/big1.jpg", "/big2.jpg"]


def test_unknown_size_lazy_image_preserved() -> None:
    # 회귀 방지: 크기 불명(로드 전 lazy, natural=0/속성없음)은 버리지 않고 보존.
    html = '<div class="detail"><img src="/lazy_detail.jpg"></div>'
    extractor = FieldExtractor(selector="div.detail", attribute="src", multiple=True)
    assert _extract(html, extractor) == ["/lazy_detail.jpg"]


def test_skip_first_drops_leading_images() -> None:
    # skip_first=1: 갤러리 맨 앞의 대표이미지 제외 (전부 큰 이미지)
    html = """
      <img class="gallery" src="/main.jpg" width="600" height="600">
      <img class="gallery" src="/e1.jpg" width="600" height="600">
      <img class="gallery" src="/e2.jpg" width="600" height="600">
    """
    extractor = FieldExtractor(selector="img.gallery", attribute="src", multiple=True, skip_first=1)
    assert _extract(html, extractor) == ["/e1.jpg", "/e2.jpg"]


def test_direct_img_selector_unchanged() -> None:
    html = '<img class="detail" src="/d1.jpg" width="600" height="800">'
    extractor = FieldExtractor(selector="img.detail", attribute="src", multiple=True)
    assert _extract(html, extractor) == ["/d1.jpg"]
