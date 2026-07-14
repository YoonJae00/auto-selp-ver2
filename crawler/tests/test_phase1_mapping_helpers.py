from __future__ import annotations

import pytest

from app.analyzer.adapter_schema import FieldExtractor, OptionGroupConfig, OptionsConfig, get_product_field_mappings
from app.analyzer.site_probe import _capture_detail_screenshot, normalize_sample_products
from app.crawlers.yaml_adapter import (
    YAMLAdapter,
    _image_csv,
    _image_values,
    _map_supplier_status,
    _split_option_text_price,
    _status_from_maxq_value,
    _supported_image_url,
    _without_images,
    is_soldout_text,
    option_is_soldout,
    status_from_cart_button,
    SOLDOUT_MARKER_SELECTOR,
)
from app.analyzer.option_text_parser import parse_option_text
from app.workers.adapter import AdapterTestWorker, _status_suggestion_from_snapshots


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
        if isinstance(value, list):
            return value
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


def test_status_mapping_allows_keyword_inside_image_src() -> None:
    assert _map_supplier_status("/images/btn_soldout.gif", {"soldout": "sold_out"}, "available") == "sold_out"


def test_supported_image_url_allows_selected_formats_with_query() -> None:
    assert _supported_image_url("https://img.test/a.JPG?x=1") == "https://img.test/a.JPG?x=1"
    assert _supported_image_url("/img/a.jpeg#v") == "/img/a.jpeg#v"
    assert _supported_image_url("/img/a.png") == "/img/a.png"
    assert _supported_image_url("/img/a.webp") == "/img/a.webp"
    assert _supported_image_url("/img/a.gif") is None  # gif excluded (banners/spacers)
    assert _supported_image_url("/img/no-extension") == "/img/no-extension"  # CDN/resizer now accepted


def test_image_csv_filters_and_joins_supported_images() -> None:
    assert _image_csv(["/d/1.jpg", "/d/2.webp?x=1", "/d/3.gif", None]) == "/d/1.jpg,/d/2.webp?x=1"
    assert _image_csv("/d/one.png") == "/d/one.png"
    assert _image_csv(["/d/no-extension"]) == "/d/no-extension"


def test_without_images_removes_main_image_with_relative_or_absolute_url() -> None:
    images = _image_values(["/img/main.jpg", "https://shop.test/img/detail.jpg", "/img/banner.gif"])

    assert _without_images(images, "https://shop.test/img/main.jpg", "https://shop.test/p/1") == [
        "https://shop.test/img/detail.jpg"
    ]


def test_split_option_text_price_legacy_fallback_reads_trailing_signed_price() -> None:
    assert _split_option_text_price("M (+5000원)") == ("M", 5000)
    assert _split_option_text_price("L(+10,000)") == ("L", 10000)
    assert _split_option_text_price("XL (-1,000원)") == ("XL", -1000)
    assert _split_option_text_price("100ml (+500원)") == ("100ml", 500)
    assert _split_option_text_price("브라운 + 0원") == ("브라운", 0)
    assert _split_option_text_price("아이보리 + 1000원") == ("아이보리", 1000)
    assert _split_option_text_price("블랙 - 500원") == ("블랙", -500)
    assert _split_option_text_price("아이폰 15") == ("아이폰 15", None)
    assert _split_option_text_price("블랙 (추가금 없음)") == ("블랙 (추가금 없음)", None)


def test_option_text_parser_reads_delta_rule() -> None:
    parser = {
        "enabled": True,
        "pattern": r"^(?P<value>.*?)\s*\((?P<sign>[+-])(?P<price>[\d,]+)원?\)$",
        "price_kind": "delta",
        "confidence": "high",
    }

    parsed = parse_option_text("M (+5000원)", parser, 12000)

    assert parsed.value == "M"
    assert parsed.price_delta == 5000
    assert parsed.supply_price == 17000


def test_option_text_parser_reads_supply_rule() -> None:
    parser = {
        "enabled": True,
        "pattern": r"^(?P<value>.*?)\s*/\s*(?P<price>[\d,]+)원?$",
        "price_kind": "supply",
        "confidence": "medium",
    }

    parsed = parse_option_text("블랙 / 13,900원", parser, 12000)

    assert parsed.value == "블랙"
    assert parsed.supply_price == 13900
    assert parsed.price_delta == 1900


def test_option_text_parser_low_confidence_falls_back_to_legacy() -> None:
    parser = {
        "enabled": True,
        "pattern": r"^(?P<value>.*?) / (?P<price>\d+)$",
        "price_kind": "supply",
        "confidence": "low",
    }

    parsed = parse_option_text("M (+5000원)", parser, 12000)

    assert parsed.value == "M"
    assert parsed.price_delta == 5000
    assert parsed.supply_price == 17000


def test_mapping_rows_show_combined_option_row_when_option_text_parser_enabled() -> None:
    adapter = type("Adapter", (), {
        "adapter": type("AdapterData", (), {
            "product": type("Product", (), {
                "supplier_product_code": None,
                "raw_product_name": None,
                "supplier_status": None,
                "supply_price": None,
                "origin": None,
                "main_image_url": None,
                "detail_content": None,
                "extra_image_urls": None,
            })(),
            "options": OptionsConfig(
                groups=[OptionGroupConfig(name="색상", values_selector=".option")],
                option_text_parser={
                    "enabled": True,
                    "pattern": r"^(?P<value>.*?) / (?P<price>[\d,]+)원?$",
                    "price_kind": "supply",
                    "confidence": "high",
                },
            )
        })()
    })()

    rows = get_product_field_mappings(adapter)
    option_row = next(row for row in rows if row["key"] == "option_values")

    assert "option_prices" not in [row["key"] for row in rows]
    assert option_row["label"] == "옵션값/가격"
    assert option_row["status"] == "ok"
    assert option_row["selector"] == ".option (AI 옵션 파서)"


def test_option_text_parser_skips_placeholder_options() -> None:
    assert parse_option_text("-[필수] 옵션을 선택해주세요-").value is None
    assert parse_option_text("옵션을 선택해 주세요").value is None
    assert parse_option_text("M (+5000원)").value == "M"


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


@pytest.mark.asyncio
async def test_extract_options_matches_option_prices_by_index() -> None:
    adapter = YAMLAdapter.__new__(YAMLAdapter)
    adapter.adapter = type("Adapter", (), {
        "adapter": type("AdapterData", (), {
            "options": OptionsConfig(
                groups=[OptionGroupConfig(name="색상", values_selector=".option")],
                option_price_delta=FieldExtractor(selector=".price", multiple=True, transform="extract_number"),
            )
        })()
    })()
    page = _FakePage({
        ".option": [_FakeElement("블랙"), _FakeElement("화이트"), _FakeElement("그레이")],
        ".price": [_FakeElement("12900"), _FakeElement("13900"), _FakeElement("14900")],
    })

    options = await adapter._extract_options(page, "P1", 12000)

    assert [opt.option_value_1 for opt in options] == ["블랙", "화이트", "그레이"]
    assert [opt.option_supply_price for opt in options] == [12900, 13900, 14900]
    assert [opt.option_price_delta for opt in options] == [900, 1900, 2900]


@pytest.mark.asyncio
async def test_extract_options_skips_placeholder_and_keeps_price_index_aligned() -> None:
    adapter = YAMLAdapter.__new__(YAMLAdapter)
    adapter.adapter = type("Adapter", (), {
        "adapter": type("AdapterData", (), {
            "options": OptionsConfig(
                groups=[OptionGroupConfig(name="색상", values_selector=".option")],
                option_price_delta=FieldExtractor(selector=".price", multiple=True, transform="extract_number"),
            )
        })()
    })()
    page = _FakePage({
        ".option": [_FakeElement("-[필수] 옵션을 선택해주세요-"), _FakeElement("블랙"), _FakeElement("화이트")],
        ".price": [_FakeElement("12900"), _FakeElement("13900")],
    })

    options = await adapter._extract_options(page, "P1", 12000)

    assert [opt.option_value_1 for opt in options] == ["블랙", "화이트"]
    assert [opt.option_supply_price for opt in options] == [12900, 13900]
    assert [opt.option_position for opt in options] == [1, 2]


@pytest.mark.asyncio
async def test_extract_options_splits_price_from_option_text() -> None:
    adapter = YAMLAdapter.__new__(YAMLAdapter)
    adapter.adapter = type("Adapter", (), {
        "adapter": type("AdapterData", (), {
            "options": OptionsConfig(groups=[OptionGroupConfig(name="사이즈", values_selector=".option")])
        })()
    })()
    page = _FakePage({
        ".option": [_FakeElement("M (+5000원)"), _FakeElement("L (+10,000원)"), _FakeElement("아이폰 15")],
    })

    options = await adapter._extract_options(page, "P1", 12000)

    assert [opt.option_value_1 for opt in options] == ["M", "L", "아이폰 15"]
    assert [opt.option_price_delta for opt in options] == [5000, 10000, None]
    assert [opt.option_supply_price for opt in options] == [17000, 22000, None]
    assert [opt.raw_option_text for opt in options] == ["M (+5000원)", "L (+10,000원)", "아이폰 15"]


@pytest.mark.asyncio
async def test_extract_options_uses_configured_option_text_parser() -> None:
    adapter = YAMLAdapter.__new__(YAMLAdapter)
    adapter.adapter = type("Adapter", (), {
        "adapter": type("AdapterData", (), {
            "options": OptionsConfig(
                groups=[OptionGroupConfig(name="색상", values_selector=".option")],
                option_text_parser={
                    "enabled": True,
                    "pattern": r"^(?P<value>.*?)\s*/\s*(?P<price>[\d,]+)원?$",
                    "price_kind": "supply",
                    "confidence": "high",
                },
            )
        })()
    })()
    page = _FakePage({
        ".option": [_FakeElement("블랙 / 13,900원"), _FakeElement("화이트 / 14,900원")],
    })

    options = await adapter._extract_options(page, "P1", 12000)

    assert [opt.option_value_1 for opt in options] == ["블랙", "화이트"]
    assert [opt.option_supply_price for opt in options] == [13900, 14900]
    assert [opt.option_price_delta for opt in options] == [1900, 2900]


@pytest.mark.asyncio
async def test_adapter_test_worker_previews_embedded_option_prices() -> None:
    worker = AdapterTestWorker.__new__(AdapterTestWorker)
    adapter = type("Adapter", (), {
        "adapter": type("AdapterData", (), {
            "options": OptionsConfig(groups=[OptionGroupConfig(name="색상", values_selector=".option")])
        })()
    })()
    page = _FakePage({
        ".option": [_FakeElement("옵션을 선택해 주세요"), _FakeElement("브라운 + 0원"), _FakeElement("아이보리 + 1000원")],
    })

    # 병합 행: 값 묶음 / 가격 묶음, 개수 동일
    assert await worker._extract_test_option(page, adapter, "option_values") == "2개 · 브라운, 아이보리 / +0원, +1,000원"
    assert await worker._extract_test_option(page, adapter, "option_prices") == "2개 · 0, 1000"


@pytest.mark.asyncio
async def test_adapter_test_worker_flags_soldout_options() -> None:
    worker = AdapterTestWorker.__new__(AdapterTestWorker)
    adapter = type("Adapter", (), {
        "adapter": type("AdapterData", (), {
            "options": OptionsConfig(groups=[OptionGroupConfig(name="색상", values_selector=".option")])
        })()
    })()
    page = _FakePage({
        ".option": [
            _FakeElement("옵션을 선택해 주세요"),   # placeholder → 제외
            _FakeElement("블랙"),
            _FakeElement("화이트 (품절)"),           # 텍스트 품절
            _FakeElement("레드", attrs={"disabled": ""}),  # disabled 품절
        ],
    })
    summary = await worker._extract_test_option(page, adapter, "option_values")
    assert summary.endswith("(품절 2)")


@pytest.mark.asyncio
async def test_adapter_test_worker_previews_configured_option_text_parser() -> None:
    worker = AdapterTestWorker.__new__(AdapterTestWorker)
    adapter = type("Adapter", (), {
        "adapter": type("AdapterData", (), {
            "options": OptionsConfig(
                groups=[OptionGroupConfig(name="색상", values_selector=".option")],
                option_text_parser={
                    "enabled": True,
                    "pattern": r"^(?P<value>.*?)\s*/\s*(?P<price>[\d,]+)원?$",
                    "price_kind": "supply",
                    "confidence": "high",
                },
            )
        })()
    })()
    page = _FakePage({
        ".option": [_FakeElement("블랙 / 13,900원"), _FakeElement("화이트 / 14,900원")],
    })

    # base_price 미상 → 공급가로 표시
    assert await worker._extract_test_option(page, adapter, "option_values") == "2개 · 블랙, 화이트 / +13,900원, +14,900원"
    assert await worker._extract_test_option(page, adapter, "option_prices") == "2개 · 13900, 14900"


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


def test_normalize_sample_products_reference_keeps_only_products() -> None:
    base = "https://shop.com"
    products = [
        {"url": "/shop/shopdetail.html?branduid=1", "name": "상품1", "image_url": ""},
        {"url": "/shop/shopdetail.html?branduid=2", "name": "상품2", "image_url": ""},
        {"url": "/shop/shopdetail.html?branduid=3", "name": "상품3", "image_url": ""},
        {"url": "/shop/shopdetail.html?branduid=4", "name": "상품4", "image_url": ""},
        {"url": "/shop/shopdetail.html?branduid=5", "name": "상품5", "image_url": ""},
        {"url": "/shop/shopbrand.html?xcode=001", "name": "카테고리A", "image_url": ""},
        {"url": "/shop/shopbrand.html?xcode=002", "name": "카테고리B", "image_url": ""},
        {"url": "/member/mileage_charge.html", "name": "적립금충전", "image_url": ""},
        {"url": "/board/notice.html", "name": "공지", "image_url": ""},
    ]
    ref = "https://shop.com/shop/shopdetail.html?branduid=999"
    normalized, links = normalize_sample_products(base, products, reference_url=ref)

    assert len(links) == 5
    assert all("shopdetail" in u and "shopbrand" not in u for u in links)


def test_normalize_sample_products_reference_relaxes_via_code_param() -> None:
    base = "https://shop.com"
    products = [
        {"url": "/view.php?goodsno=100", "name": "정확일치", "image_url": ""},
        {"url": "/detail/goods?goodsno=200", "name": "다른경로1", "image_url": ""},
        {"url": "/detail/goods?goodsno=300", "name": "다른경로2", "image_url": ""},
    ]
    ref = "https://shop.com/view.php?goodsno=100"
    normalized, links = normalize_sample_products(base, products, reference_url=ref)

    # 경로 일치는 1개뿐 → goodsno 공유 후보까지 완화되어 3개 모두 생존
    assert len(links) == 3
    assert set(links) == {
        "https://shop.com/view.php?goodsno=100",
        "https://shop.com/detail/goods?goodsno=200",
        "https://shop.com/detail/goods?goodsno=300",
    }


def test_normalize_sample_products_no_reference_keeps_majority_path() -> None:
    base = "https://shop.com"
    products = [
        {"url": "/goods/view?no=1", "name": "상품1", "image_url": ""},
        {"url": "/goods/view?no=2", "name": "상품2", "image_url": ""},
        {"url": "/goods/view?no=3", "name": "상품3", "image_url": ""},
        {"url": "/goods/view?no=4", "name": "상품4", "image_url": ""},
        {"url": "/some/odd/link?x=1", "name": "이탈링크", "image_url": ""},
    ]
    normalized, links = normalize_sample_products(base, products)

    # /goods/view 최다 그룹(4/5, 과반)만 유지, 이탈 링크 제거
    assert len(links) == 4
    assert all("/goods/view" in u for u in links)


def test_normalize_sample_products_blacklist_only_fallback() -> None:
    base = "https://shop.com"
    products = [
        {"url": "/catalog/item?sku=1", "name": "상품1", "image_url": ""},
        {"url": "/catalog/item?sku=2", "name": "상품2", "image_url": ""},
        {"url": "/board/notice", "name": "공지", "image_url": ""},
    ]
    # reference 경로가 후보 중 어디에도 없고 코드 파라미터도 공유되지 않음 → 블랙리스트만 적용된 폴백
    ref = "https://shop.com/product/detail.html?pid=9"
    normalized, links = normalize_sample_products(base, products, reference_url=ref)

    assert set(links) == {
        "https://shop.com/catalog/item?sku=1",
        "https://shop.com/catalog/item?sku=2",
    }


@pytest.mark.asyncio
async def test_capture_detail_screenshot_returns_path() -> None:
    calls = []

    class _Page:
        async def screenshot(self, path, full_page=False):
            calls.append(full_page)
            with open(path, "wb") as f:
                f.write(b"png")

    path = await _capture_detail_screenshot(_Page())
    assert path.endswith("detail.png")
    assert calls == [True]  # full_page 우선 시도


@pytest.mark.asyncio
async def test_capture_detail_screenshot_falls_back_to_viewport() -> None:
    calls = []

    class _Page:
        async def screenshot(self, path, full_page=False):
            calls.append(full_page)
            if full_page:
                raise RuntimeError("full_page unsupported")
            with open(path, "wb") as f:
                f.write(b"png")

    path = await _capture_detail_screenshot(_Page())
    assert path.endswith("detail.png")
    assert calls == [True, False]  # full_page 실패 → viewport 폴백


@pytest.mark.asyncio
async def test_capture_detail_screenshot_swallows_all_failures() -> None:
    class _Page:
        async def screenshot(self, path, full_page=False):
            raise RuntimeError("boom")

    assert await _capture_detail_screenshot(_Page()) == ""  # 완전 실패 시 ""


def test_normalize_sample_products_excludes_reward_pseudo_product() -> None:
    # 정도매: 적립금 충전이 진짜 상품과 같은 goods_view.php 경로를 써 경로 필터를 통과 → 이름으로 제외.
    base = "https://jd.com"
    products = [
        {"url": "/goods/goods_view.php?goodsNo=1", "name": "예쁜 원피스", "image_url": "/a.jpg"},
        {"url": "/goods/goods_view.php?goodsNo=9", "name": "적립금 충전", "image_url": "/b.jpg"},
    ]
    ref = "https://jd.com/goods/goods_view.php?goodsNo=1"
    normalized, links = normalize_sample_products(base, products, reference_url=ref)

    assert links == ["https://jd.com/goods/goods_view.php?goodsNo=1"]  # 적립금 유사상품 제외
    assert all("적립금" not in p["name"] for p in normalized)


def test_normalize_sample_products_keeps_unnamed_candidate() -> None:
    # 이름이 비어 있으면 이름 블랙리스트를 통과(URL 필터만 적용).
    base = "https://jd.com"
    normalized, links = normalize_sample_products(
        base, [], links=["/goods/goods_view.php?goodsNo=5"],
        reference_url="https://jd.com/goods/goods_view.php?goodsNo=1",
    )
    assert links == ["https://jd.com/goods/goods_view.php?goodsNo=5"]


def test_status_snapshot_suggestion_prefers_maxq_difference() -> None:
    suggestion = _status_suggestion_from_snapshots(
        {"maxq_value": "12", "has_buy_button": True},
        {"maxq_value": "0", "has_buy_button": False},
    )

    assert suggestion is not None
    assert suggestion["fallback_from"] == "maxq"
    assert suggestion["confidence"] == "high"


def test_status_snapshot_suggestion_uses_cart_button_difference() -> None:
    suggestion = _status_suggestion_from_snapshots(
        {"maxq_value": "", "buy_buttons": [{"text": "장바구니", "html": "<button>장바구니</button>"}]},
        {"maxq_value": "", "buy_buttons": []},
    )

    assert suggestion is not None
    assert suggestion["fallback_from"] == "cart_button"


def test_status_snapshot_suggestion_ignores_shared_global_nav() -> None:
    # itopic 유형: 상단 전역 메뉴 주문/장바구니 이미지가 양쪽 페이지에 공통 존재하고,
    # 판매중에만 상품영역 장바구니 버튼(sang_btn_06cart)이 있다. 집합 차이로 전역 네비를
    # 상쇄하고 판별 버튼만 골라 구체 셀렉터를 만들어야 한다.
    nav = [
        {"text": "", "html": "<img src='/images/d2/10003/topmenu_04order.gif'>"},
        {"text": "", "html": "<img src='/images/d2/10003/topmenu_05cart.gif'>"},
    ]
    suggestion = _status_suggestion_from_snapshots(
        {"maxq_value": "", "buy_buttons": nav + [{"text": "", "html": "<img src='/images/d2/10003/sang_btn_06cart.gif' border='0'>"}]},
        {"maxq_value": "", "buy_buttons": nav},
    )

    assert suggestion is not None
    assert suggestion["fallback_from"] == "cart_button"
    assert suggestion["selector"] == "img[src*='sang_btn_06cart.gif']"
    assert suggestion["confidence"] == "high"


@pytest.mark.parametrize("text,expected", [
    ("빨강 (품절)", True),
    ("파랑 [매진]", True),
    ("Red SOLD OUT", True),
    ("재고 없음", True),
    ("빨강", False),
    ("", False),
    (None, False),
])
def test_is_soldout_text(text, expected) -> None:
    assert is_soldout_text(text) is expected


@pytest.mark.asyncio
async def test_option_is_soldout_from_disabled_attribute() -> None:
    assert await option_is_soldout(_FakeElement(attrs={"disabled": ""}), "빨강") is True
    assert await option_is_soldout(_FakeElement(attrs={"class": "opt soldout"}), "빨강") is True
    assert await option_is_soldout(_FakeElement(), "빨강") is False


@pytest.mark.asyncio
async def test_status_from_cart_button_uses_specific_selector() -> None:
    # 품절 마커 없음 + 구체 셀렉터가 있으면 그 존재/부재로만 판정(전역 네비 오탐 방지).
    present = _FakePage({SOLDOUT_MARKER_SELECTOR: None, "img[src*='sang_btn_06cart.gif']": _FakeElement()})
    assert await status_from_cart_button(present, "img[src*='sang_btn_06cart.gif']") == "available"
    absent = _FakePage({SOLDOUT_MARKER_SELECTOR: None, "img[src*='sang_btn_06cart.gif']": None})
    assert await status_from_cart_button(absent, "img[src*='sang_btn_06cart.gif']") == "sold_out"
    marked = _FakePage({SOLDOUT_MARKER_SELECTOR: _FakeElement()})
    assert await status_from_cart_button(marked, "img[src*='sang_btn_06cart.gif']") == "sold_out"


def test_status_snapshot_suggestion_returns_none_when_unclear() -> None:
    nav = [{"text": "", "html": "<img src='/topmenu_05cart.gif'>"}]
    assert _status_suggestion_from_snapshots(
        {"maxq_value": "", "buy_buttons": nav},
        {"maxq_value": "", "buy_buttons": nav},
    ) is None
