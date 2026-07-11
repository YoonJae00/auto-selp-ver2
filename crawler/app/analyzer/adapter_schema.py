from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, Field


class BrowserConfig(BaseModel):
    channel: Literal["msedge", "chrome", "chromium"] = "msedge"
    user_agent: str | None = None
    wait_until: Literal["networkidle", "domcontentloaded", "load"] = "networkidle"
    navigation_timeout: int = Field(default=30_000, ge=1_000, le=120_000)


class LoginField(BaseModel):
    id: str
    password: str


class LoginConfig(BaseModel):
    required: bool = False
    login_url: str | None = None
    fields: LoginField | None = None
    submit: str | None = None
    success_indicator: str | None = None
    failure_indicator: str | None = None


class AllProductsConfig(BaseModel):
    available: bool = False
    url: str | None = None


class SubmenuConfig(BaseModel):
    selector: str
    expand_trigger: Literal["hover", "click", "static"] = "static"


class NavigationConfig(BaseModel):
    menu_selector: str | None = None
    link_selector: str = "a"
    name_source: Literal["text", "attribute"] = "text"
    url_attribute: str = "href"
    max_depth: int = Field(default=3, ge=1, le=3)
    submenu: SubmenuConfig | None = None


class CategoryItem(BaseModel):
    """마법사가 확정한 카테고리 하나. 저장해 두면 crawl이 menu_selector로 매번
    다시 걷지 않고 이 목록을 그대로 사용한다."""
    name: str = ""
    url: str


class CategoriesConfig(BaseModel):
    mode: Literal["all_products", "tree", "hybrid"] = "tree"
    all_products: AllProductsConfig = Field(default_factory=AllProductsConfig)
    navigation: NavigationConfig | None = None
    url_template: str | None = None
    store_category_path: bool = True
    entries: list[CategoryItem] = Field(default_factory=list)


class PaginationConfig(BaseModel):
    type: Literal["page_number", "next_button", "infinite_scroll"] = "page_number"
    page_param: str = "page"
    start: int = Field(default=1, ge=1)
    max_pages: int = Field(default=200, ge=1, le=10_000)
    stop_indicator: str | None = None


class ProductLinkConfig(BaseModel):
    selector: str
    attribute: str = "href"
    base: Literal["relative", "absolute"] = "relative"


class ListingConfig(BaseModel):
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)
    product_link: ProductLinkConfig = Field(default_factory=lambda: ProductLinkConfig(selector="a[href*='goods']"))


class FieldExtractor(BaseModel):
    selector: str = ""
    attribute: str | None = None
    fallback_attribute: str | None = None
    transform: Literal["strip", "extract_number", "extract_signed_number", "none"] = "strip"
    html: bool = False
    multiple: bool = False
    skip_first: int = 0  # multiple 수집 시 앞에서 N개 제외 (대표이미지가 갤러리 맨 앞에 섞이는 경우)
    optional: bool = False
    fallback: str | None = None
    fallback_from: Literal["url", "cart_button", "maxq", "none"] = "none"
    url_param: str | None = None  # 쿼리 파라미터 이름. fallback_from="url"일 때 url_pattern보다 우선
    url_pattern: str | None = None  # regex; group 1이 추출값. fallback_from="url"일 때 사용


def extract_url_value(url: str, extractor: "FieldExtractor") -> str | None:
    """fallback_from="url"일 때 URL에서 값 추출. url_param(쿼리 파라미터) 우선, 없으면 url_pattern(정규식)."""
    if extractor.url_param:
        return parse_qs(urlparse(url).query).get(extractor.url_param, [None])[0]
    if extractor.url_pattern:
        m = re.search(extractor.url_pattern, url)
        return m.group(1) if m and m.lastindex else None
    return None


class StatusMapping(BaseModel):
    mapping: dict[str, str] = Field(default_factory=dict)
    default: str = "available"


class DependentOptionsConfig(BaseModel):
    enabled: bool = False
    level_1_group: str | None = None
    level_2_group: str | None = None
    level_2_trigger: Literal["click", "select"] = "click"
    level_2_load_indicator: str | None = None
    level_2_values_selector: str | None = None


class AjaxOptionConfig(BaseModel):
    enabled: bool = False
    endpoint_pattern: str | None = None
    response_path: str | None = None


class OptionTextParserConfig(BaseModel):
    enabled: bool = False
    pattern: str = ""
    price_kind: Literal["delta", "supply"] = "delta"
    confidence: Literal["high", "medium", "low"] = "low"
    examples: list[str] = Field(default_factory=list)


class OptionGroupConfig(BaseModel):
    name: str
    group_label_selector: str | None = None
    values_selector: str
    value_text: Literal["text", "value", "attribute"] = "text"
    value_attribute: str | None = None


class OptionsConfig(BaseModel):
    detection: Literal["dom", "ajax", "none"] = "dom"
    type: Literal["combination", "single", "custom"] = "combination"
    groups: list[OptionGroupConfig] = Field(default_factory=list)
    dependent_options: DependentOptionsConfig = Field(default_factory=DependentOptionsConfig)
    option_image_url: FieldExtractor | None = None
    option_price_delta: FieldExtractor | None = None
    option_stock_quantity: FieldExtractor | None = None
    ajax_option: AjaxOptionConfig = Field(default_factory=AjaxOptionConfig)
    option_text_parser: OptionTextParserConfig = Field(default_factory=OptionTextParserConfig)


class ProductConfig(BaseModel):
    supplier_product_id: FieldExtractor | None = None
    supplier_product_code: FieldExtractor | None = None
    raw_product_name: FieldExtractor | None = None
    supplier_status: FieldExtractor | None = None
    status_mapping: StatusMapping = Field(default_factory=StatusMapping)
    supply_price: FieldExtractor | None = None
    origin: FieldExtractor | None = None
    main_image_url: FieldExtractor | None = None
    detail_content: FieldExtractor | None = None
    extra_image_urls: FieldExtractor | None = None
    brand_name: FieldExtractor | None = None
    manufacturer: FieldExtractor | None = None
    model_name: FieldExtractor | None = None


class DelaysConfig(BaseModel):
    between_pages: int | None = Field(default=None, ge=0, le=60)
    between_products: int | None = Field(default=None, ge=0, le=60)


class AdapterData(BaseModel):
    name: str
    base_url: str
    encoding: Literal["utf-8", "euc-kr"] = "utf-8"
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    login: LoginConfig = Field(default_factory=LoginConfig)
    categories: CategoriesConfig = Field(default_factory=CategoriesConfig)
    listing: ListingConfig = Field(default_factory=ListingConfig)
    product: ProductConfig = Field(default_factory=ProductConfig)
    options: OptionsConfig = Field(default_factory=OptionsConfig)
    delays: DelaysConfig = Field(default_factory=DelaysConfig)


class Adapter(BaseModel):
    adapter: AdapterData


# ===== Mapping Table Helpers =====

FIELD_LABELS_KO: dict[str, str] = {
    "supplier_product_code": "상품코드",
    "raw_product_name": "상품명",
    "supplier_status": "판매 상태",
    "supply_price": "공급가",
    "origin": "원산지",
    "main_image_url": "대표 이미지",
    "detail_content": "상세 페이지",
    "extra_image_urls": "추가 이미지",
}

OPTION_VALUES_FIELD_PATH = "adapter.options.groups.0.values_selector"
OPTION_VALUES_ROW_KEY = "option_values"
OPTION_PRICES_FIELD_PATH = "adapter.options.option_price_delta"
OPTION_PRICES_ROW_KEY = "option_prices"


def get_product_field_mappings(adapter: "Adapter") -> list[dict[str, Any]]:
    """Extract product field mappings for display in a table.

    Returns a list of dicts with keys: key, label, selector, attribute, transform, status, urlPattern
    where status is one of: 'ok', 'missing', 'empty'
    """
    product = adapter.adapter.product
    rows = []
    for field_name, label in FIELD_LABELS_KO.items():
        extractor = getattr(product, field_name, None)
        base = {
            "key": field_name,
            "label": label,
            "fieldPath": f"adapter.product.{field_name}",
            "urlAllowed": field_name == "supplier_product_code",
            "testable": True,
            "extraEnabled": field_name != "extra_image_urls" or extractor is not None,
            "skipFirst": int(extractor.skip_first) if extractor else 0,
        }
        if extractor is None:
            rows.append({
                **base,
                "selector": "", "attribute": "", "transform": "",
                "status": "missing", "urlPattern": "", "urlParam": "",
            })
        elif (
            not extractor.selector.strip()
            and not extractor.url_pattern
            and not extractor.url_param
            and extractor.fallback_from in (None, "", "none")
        ):
            rows.append({
                **base,
                "selector": "", "attribute": "", "transform": "",
                "status": "empty", "urlPattern": "", "urlParam": "",
            })
        else:
            url_pat = extractor.url_pattern or ""
            url_param = extractor.url_param or ""
            if url_param or url_pat:
                desc = ""
                status = "ok"
            elif extractor.fallback_from not in (None, "", "none") and not extractor.selector.strip():
                desc = f"자동 판정: {extractor.fallback_from}"
                status = "ok"
            else:
                desc = extractor.selector
                if extractor.attribute:
                    desc += f" ({extractor.attribute} 속성)"
                if extractor.transform and extractor.transform != "strip":
                    desc += f" [{extractor.transform}]"
                if extractor.fallback:
                    desc += f" (기본값: {extractor.fallback})"
                if extractor.html:
                    desc += " [HTML]"
                if extractor.multiple:
                    desc += " [다중]"
                status = "ok"
            rows.append({
                **base,
                "selector": desc, "attribute": extractor.attribute or "",
                "transform": extractor.transform or "",
                "status": status, "urlPattern": url_pat, "urlParam": url_param,
            })
    option_group = adapter.adapter.options.groups[0] if adapter.adapter.options.groups else None
    option_text_parser = adapter.adapter.options.option_text_parser
    option_selector = option_group.values_selector if option_group else ""
    if option_selector and option_text_parser.enabled:
        option_selector = f"{option_selector} (AI 옵션 파서)"
    rows.append({
        "key": OPTION_VALUES_ROW_KEY,
        "label": "옵션값/가격",
        "fieldPath": OPTION_VALUES_FIELD_PATH,
        "selector": option_selector,
        "attribute": "",
        "transform": "",
        "status": "ok" if option_group and option_group.values_selector.strip() else "missing",
        "urlPattern": "", "urlParam": "",
        "urlAllowed": False,
        "testable": True,
        "extraEnabled": True,
        "skipFirst": 0,
    })
    return rows


def get_category_summary(adapter: "Adapter") -> dict[str, str]:
    """Extract category config summary for display."""
    cat = adapter.adapter.categories
    nav = cat.navigation
    return {
        "mode": cat.mode,
        "menu_selector": (nav.menu_selector if nav and nav.menu_selector else "(미설정)"),
        "url_template": cat.url_template or "(미설정)",
        "max_depth": str(nav.max_depth) if nav else "0",
        "has_all_products": "있음" if cat.all_products.available else "없음",
        "all_products_url": cat.all_products.url or "",
    }


def get_pagination_summary(adapter: "Adapter") -> dict[str, str]:
    """Extract pagination config summary for display."""
    pag = adapter.adapter.listing.pagination
    return {
        "type": pag.type,
        "page_param": pag.page_param,
        "max_pages": str(pag.max_pages),
        "stop_indicator": pag.stop_indicator or "(미설정)",
    }


def get_login_summary(adapter: "Adapter") -> dict[str, str]:
    """Extract login config summary for display."""
    login = adapter.adapter.login
    return {
        "required": "필요" if login.required else "불필요",
        "login_url": login.login_url or "",
        "has_fields": "예" if login.fields else "아니오",
        "submit": login.submit or "",
        "success_indicator": login.success_indicator or "",
    }


def get_options_summary(adapter: "Adapter") -> dict[str, str]:
    """Extract options config summary for display."""
    opt = adapter.adapter.options
    return {
        "detection": opt.detection,
        "type": opt.type,
        "groups_count": str(len(opt.groups)),
        "dependent_enabled": "사용" if opt.dependent_options.enabled else "미사용",
    }
