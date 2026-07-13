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


# ── 라벨 오염 자동 정리 (사람처럼 라벨을 떼고 값만 취함) ─────────────────────
# origin: "브랜드 : VIGA\n원산지 : 중국(외 아시아)" → "중국(외 아시아)". 라벨 뒤 콜론 값을
# 구분자(개행, /, |, ,) 전까지 취한다.
_ORIGIN_LABEL_RE = re.compile(r"(?:원산지|제조국가|제조국)\s*[:：]\s*([^\n/|,]+)")
# 라벨 없이 통째로 "라벨 : 값" 꼴이면 콜론 뒤만 (짧은 선두 라벨 + 구분자 없는 단일 값일 때만).
_ORIGIN_GENERIC_RE = re.compile(r"^\s*[^\n:：]{1,20}[:：]\s*([^\n/|,]+?)\s*$")
# 이름/코드/브랜드/제조사/모델명: 선두 라벨 접두만 제거, 값 중간 콜론은 보존.
_FIELD_LABEL_RE: dict[str, "re.Pattern[str]"] = {
    "raw_product_name": re.compile(r"^\s*(?:상품명|제품명|상품이름)\s*[:：]\s*(.+)$", re.DOTALL),
    "supplier_product_code": re.compile(r"^\s*(?:상품코드|제품코드|상품번호|코드)\s*[:：]\s*(.+)$", re.DOTALL),
    "brand_name": re.compile(r"^\s*(?:브랜드|brand)\s*[:：]\s*(.+)$", re.DOTALL | re.IGNORECASE),
    "manufacturer": re.compile(r"^\s*(?:제조사|제조원|manufacturer)\s*[:：]\s*(.+)$", re.DOTALL | re.IGNORECASE),
    "model_name": re.compile(r"^\s*(?:모델명|모델|model)\s*[:：]\s*(.+)$", re.DOTALL | re.IGNORECASE),
}

# supply_price: 상품정보 패널을 통째로 잡으면 소비자가(취소선)가 맨 앞이라 extract_number가 오추출.
# 가격 라벨이 2개 이상 섞였으면 진짜 공급가 라벨 값만 남긴다. (판매가는 판매가격의 부분문자열이라
# 개수 셀 때 부정 lookahead로 이중집계 방지 — 라벨 1개짜리는 무변형이어야 함.)
_PRICE_LABEL_COUNT_RE = re.compile(r"소비자가|판매가격|판매가(?!격)|공급가|도매가|정가|시중가")
_PRICE_PRIORITY_LABELS = ("공급가", "도매가", "판매가격", "판매가", "소비자가", "정가", "시중가")


def _supply_price_from_labels(value: str) -> str | None:
    """가격 라벨이 여럿이면 우선순위 라벨(공급가/도매가/판매가격/판매가 우선) 뒤 값만 취한다."""
    if len(_PRICE_LABEL_COUNT_RE.findall(value)) < 2:
        return None
    for label in _PRICE_PRIORITY_LABELS:
        m = re.search(re.escape(label) + r"\s*[:：]\s*([\d][\d,]*\s*원?)", value)
        if m:
            return m.group(1).strip()
    return None


def clean_field_value(field_name: str, value: str | None) -> str | None:
    """추출값에서 라벨 오염을 사람처럼 제거. transform(extract_number 등)보다 먼저 적용.

    origin은 '원산지 :' 라벨 뒤 값만, 이름/코드/브랜드/제조사/모델명은 선두 라벨 접두만 제거한다.
    그 외 필드/None/빈값은 그대로 반환.
    """
    if not value or not value.strip():
        return value
    if field_name == "origin":
        m = _ORIGIN_LABEL_RE.search(value)
        if m:
            return m.group(1).strip()
        m = _ORIGIN_GENERIC_RE.match(value)
        if m:
            return m.group(1).strip()
        return value
    if field_name == "supply_price":
        picked = _supply_price_from_labels(value)
        return picked if picked is not None else value
    pattern = _FIELD_LABEL_RE.get(field_name)
    if pattern:
        m = pattern.match(value)
        if m:
            return m.group(1).strip()
    return value


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
    where status is one of: 'ok', 'missing', 'empty', 'optional'
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
        "status": "ok" if option_group and option_group.values_selector.strip() else "optional",
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
