from __future__ import annotations

from typing import Literal

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


class CategoriesConfig(BaseModel):
    mode: Literal["all_products", "tree", "hybrid"] = "tree"
    all_products: AllProductsConfig = Field(default_factory=AllProductsConfig)
    navigation: NavigationConfig | None = None
    url_template: str | None = None
    store_category_path: bool = True


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
    optional: bool = False
    fallback: str | None = None
    fallback_from: Literal["url", "cart_button", "maxq", "none"] = "none"


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
    "supplier_product_id": "도매처 상품 ID",
    "supplier_product_code": "상품코드",
    "raw_product_name": "상품명",
    "supplier_status": "판매 상태",
    "supply_price": "공급가",
    "origin": "원산지",
    "main_image_url": "대표 이미지",
    "detail_content": "상세 페이지",
    "extra_image_urls": "추가 이미지",
    "brand_name": "브랜드명",
    "manufacturer": "제조사",
    "model_name": "모델명",
}


def get_product_field_mappings(adapter: "Adapter") -> list[dict[str, str]]:
    """Extract product field mappings for display in a table.

    Returns a list of dicts with keys: key, label, selector, attribute, transform, status
    where status is one of: 'ok', 'missing', 'empty'
    """
    product = adapter.adapter.product
    rows = []
    for field_name, label in FIELD_LABELS_KO.items():
        extractor = getattr(product, field_name, None)
        if extractor is None:
            rows.append({
                "key": field_name,
                "label": label,
                "selector": "",
                "attribute": "",
                "transform": "",
                "status": "missing",
            })
        elif not extractor.selector or not extractor.selector.strip():
            rows.append({
                "key": field_name,
                "label": label,
                "selector": "",
                "attribute": "",
                "transform": "",
                "status": "empty",
            })
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
            rows.append({
                "key": field_name,
                "label": label,
                "selector": desc,
                "attribute": extractor.attribute or "",
                "transform": extractor.transform or "",
                "status": "ok",
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
