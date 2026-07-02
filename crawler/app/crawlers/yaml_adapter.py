from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, AsyncIterator
from urllib.parse import urljoin

from app.analyzer.adapter_schema import (
    Adapter,
    CategoriesConfig,
    FieldExtractor,
    OptionsConfig,
    extract_url_value,
)
from app.credentials.store import load_supplier_credentials
from app.crawlers.base import BaseAdapter, CategoryEntry, CrawlResult, StockSnapshotData
from app.crawlers.engine import PlaywrightEngine
from app.diagnostics import log_exception
from app.schema.standard import (
    StandardOption,
    StandardProduct,
    build_option_display_name,
    derive_option_price_delta,
)


logger = logging.getLogger(__name__)


def _extract_number(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"-?\d[\d,]*", text)
    if not match:
        return None
    cleaned = match.group().replace(",", "")
    try:
        return int(cleaned)
    except ValueError:
        return None


def _extract_signed_number(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"([+-]?)\s*([\d,]+)", text)
    if not match:
        return None
    sign = -1 if match.group(1) == "-" else 1
    cleaned = match.group(2).replace(",", "")
    try:
        return sign * int(cleaned)
    except ValueError:
        return None


def _split_option_text_price(text: str | None) -> tuple[str | None, int | None]:
    if not text:
        return None, None
    cleaned = re.sub(r"\s+", " ", text).strip()
    for pattern in (
        r"\s*[\(\[]\s*(?P<sign>[+-])\s*(?P<amount>[\d,]+)\s*원?\s*[\)\]]\s*$",
        r"\s*(?:[/|:]\s*)?(?P<sign>[+-])\s*(?P<amount>[\d,]+)\s*원?\s*$",
    ):
        match = re.search(pattern, cleaned)
        if not match:
            continue
        name = cleaned[:match.start()].strip()
        if not name:
            return cleaned, None
        sign = -1 if match.group("sign") == "-" else 1
        return name, sign * int(match.group("amount").replace(",", ""))
    return cleaned or None, None


def _apply_transform(value: str | None, transform: str) -> str | int | None:
    if value is None:
        return None
    if transform == "extract_number":
        return _extract_number(value)
    if transform == "extract_signed_number":
        return _extract_signed_number(value)
    return value.strip() if transform == "strip" else value


def _status_from_maxq_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return "sold_out" if cleaned == "0" else "available"


def _map_supplier_status(status_value: Any, mapping: dict[str, str], default: str) -> str:
    if status_value:
        cleaned = str(status_value).strip()
        if cleaned in {"available", "sold_out", "stopped", "unknown"}:
            return cleaned
        return mapping.get(cleaned, default)
    return default if default == "available" else "unknown"


def _supported_image_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    url = value.strip()
    if not url:
        return None
    path = url.split("?", 1)[0].split("#", 1)[0].lower()
    return url if path.endswith((".jpg", ".jpeg", ".png", ".webp")) else None


def _image_values(value: Any) -> list[str]:
    values = value if isinstance(value, list) else ([value] if value else [])
    return [img for img in (_supported_image_url(item) for item in values) if img]


def _without_images(images: list[str], excluded: str | None, base_url: str = "") -> list[str]:
    if not excluded:
        return images
    excluded_key = urljoin(base_url, excluded)
    return [img for img in images if urljoin(base_url, img) != excluded_key]


def _image_csv(value: Any) -> str | None:
    images = _image_values(value)
    return ",".join(images) or None


class YAMLAdapter(BaseAdapter):
    def __init__(
        self,
        adapter: Adapter,
        engine: PlaywrightEngine,
        supplier_name: str,
        delay_seconds: int = 0,
        supplier_slug: str | None = None,
    ) -> None:
        self.adapter = adapter
        self.engine = engine
        self.supplier_name = supplier_name
        self.supplier_slug = supplier_slug
        self.delay_seconds = delay_seconds

    async def _perform_login(self, page) -> bool:
        """Perform login if the adapter requires it. Returns True if login succeeded or not needed."""
        login_config = self.adapter.adapter.login
        if not login_config.required or not login_config.login_url:
            return True

        # Try to load credentials from keyring
        if not self.supplier_slug:
            logger.warning("login skipped: missing supplier credential key supplier=%s", self.supplier_name)
            return False
        creds = load_supplier_credentials(self.supplier_slug)
        if not creds:
            logger.warning("login skipped: missing credentials supplier=%s", self.supplier_name)
            return False
        username, password = creds

        try:
            logger.info("login started supplier=%s url=%s", self.supplier_name, login_config.login_url)
            await page.goto(login_config.login_url, wait_until="domcontentloaded", timeout=15_000)
            await page.wait_for_timeout(1500)

            # Use configured selectors if available, otherwise auto-detect
            if login_config.fields and login_config.fields.id and login_config.fields.password:
                id_selector = login_config.fields.id
                pw_selector = login_config.fields.password
            else:
                # Auto-detect
                pw_input = await page.query_selector("input[type='password']")
                if not pw_input:
                    return False
                id_input = await page.query_selector("input[type='text'], input[type='email'], input[name*='id'], input[name*='user']")
                if not id_input:
                    return False
                id_selector = "input[type='text'], input[type='email'], input[name*='id']"
                pw_selector = "input[type='password']"

            # Fill credentials
            id_el = await page.query_selector(id_selector)
            pw_el = await page.query_selector(pw_selector)
            if not id_el or not pw_el:
                return False
            await id_el.fill(username)
            await pw_el.fill(password)

            # Submit
            if login_config.submit:
                submit_el = await page.query_selector(login_config.submit)
                if submit_el:
                    await submit_el.click()
                else:
                    await pw_el.press("Enter")
            else:
                # Try common submit selectors
                for sel in ["button[type='submit']", "input[type='submit']", "input[type='image']", "button:has-text('로그인')"]:
                    try:
                        btn = await page.query_selector(sel)
                        if btn:
                            await btn.click()
                            break
                    except Exception:
                        continue
                else:
                    await pw_el.press("Enter")

            await page.wait_for_timeout(3000)

            # Check success
            if login_config.success_indicator:
                success_el = await page.query_selector(login_config.success_indicator)
                logger.info("login finished supplier=%s success=%s", self.supplier_name, success_el is not None)
                return success_el is not None

            # Check common logout indicators
            for sel in ["a[href*='logout']", "img[src*='logout']", "a:has-text('로그아웃')"]:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        return True
                except Exception:
                    continue

            # If no failure indicator found, assume success
            if login_config.failure_indicator:
                fail_el = await page.query_selector(login_config.failure_indicator)
                if fail_el:
                    logger.info("login finished supplier=%s success=False", self.supplier_name)
                    return False

            logger.info("login finished supplier=%s success=True", self.supplier_name)
            return True
        except Exception as exc:
            log_exception(logger, f"login failed supplier={self.supplier_name}", exc)
            return False

    async def discover_categories(self) -> list[CategoryEntry]:
        config = self.adapter.adapter.categories
        if config.mode == "all_products" or (config.mode == "hybrid" and config.all_products.available):
            if config.all_products.url:
                return [CategoryEntry(
                    category_id="__all__",
                    name="전체 상품",
                    path="전체 상품",
                    url=config.all_products.url,
                )]

        nav = config.navigation
        if not nav:
            return []

        page = await self.engine.new_page()
        try:
            await page.goto(self.adapter.adapter.base_url, wait_until=self.adapter.adapter.browser.wait_until)
            return await self._walk_menu(page, nav.menu_selector, nav, depth=1, parent_path="")
        finally:
            await page.close()

    async def _walk_menu(self, page, selector: str, nav, depth: int, parent_path: str) -> list[CategoryEntry]:
        entries: list[CategoryEntry] = []
        items = await page.query_selector_all(selector)
        for item in items:
            link = await item.query_selector(nav.link_selector)
            if not link:
                continue
            name_text = await link.get_attribute(nav.url_attribute) if nav.name_source == "attribute" else await link.inner_text()
            if not name_text:
                continue
            name = name_text.strip()
            href = await link.get_attribute(nav.url_attribute)
            if not href:
                continue
            url = urljoin(self.adapter.adapter.base_url, href)
            cat_id = href.split("=")[-1].split("/")[-1] or name
            path = f"{parent_path} > {name}" if parent_path else name

            entry = CategoryEntry(category_id=cat_id, name=name, path=path, url=url)

            if depth < nav.max_depth and nav.submenu:
                try:
                    if nav.submenu.expand_trigger == "hover":
                        await item.hover()
                        await page.wait_for_timeout(500)
                    elif nav.submenu.expand_trigger == "click":
                        await link.click()
                        await page.wait_for_timeout(500)
                    sub_items = await item.query_selector_all(nav.submenu.selector)
                    if sub_items:
                        children = await self._walk_subitems(page, sub_items, nav, depth + 1, path)
                        entry.children = children
                except Exception:
                    pass

            entries.append(entry)
        return entries

    async def _walk_subitems(self, page, subitems, nav, depth: int, parent_path: str) -> list[CategoryEntry]:
        entries: list[CategoryEntry] = []
        for sub in subitems:
            name_text = await sub.inner_text()
            if not name_text:
                continue
            name = name_text.strip()
            href = await sub.get_attribute(nav.url_attribute)
            if not href:
                continue
            url = urljoin(self.adapter.adapter.base_url, href)
            cat_id = href.split("=")[-1].split("/")[-1] or name
            path = f"{parent_path} > {name}"
            entries.append(CategoryEntry(category_id=cat_id, name=name, path=path, url=url))
        return entries

    async def crawl_category(
        self,
        category_id: str,
        max_pages: int,
    ) -> AsyncIterator[CrawlResult]:
        config = self.adapter.adapter
        pagination = config.listing.pagination
        url_template = config.categories.url_template

        # Perform login if needed
        login_config = self.adapter.adapter.login
        if login_config.required:
            login_page = await self.engine.new_page()
            try:
                login_ok = await self._perform_login(login_page)
                if not login_ok:
                    raise RuntimeError("도매처 로그인에 실패했습니다. 도매처 관리 탭에서 계정 정보를 확인하세요.")
            finally:
                await login_page.close()

        page_num = pagination.start
        while page_num <= max_pages:
            if url_template:
                list_url = url_template.format(category_id=category_id, page=page_num)
            else:
                list_url = category_id

            page = await self.engine.new_page()
            try:
                logger.info("crawl list page supplier=%s category=%s page=%d url=%s", self.supplier_name, category_id, page_num, list_url)
                await page.goto(list_url, wait_until=config.browser.wait_until)
                if pagination.stop_indicator:
                    stop = await page.query_selector(pagination.stop_indicator)
                    if stop:
                        break

                product_links = await self._extract_product_links(page)
                logger.info("crawl list links supplier=%s category=%s page=%d links=%d", self.supplier_name, category_id, page_num, len(product_links))
                if not product_links:
                    break

                for link_url in product_links:
                    result = await self._crawl_product(link_url, category_path=category_id)
                    if result:
                        yield result
                    if self.delay_seconds > 0:
                        await asyncio.sleep(self.delay_seconds)
            finally:
                await page.close()

            if self.delay_seconds > 0:
                await asyncio.sleep(self.delay_seconds)
            page_num += 1

    async def _extract_product_links(self, page) -> list[str]:
        link_config = self.adapter.adapter.listing.product_link
        elements = await page.query_selector_all(link_config.selector)
        links: list[str] = []
        for el in elements:
            href = await el.get_attribute(link_config.attribute)
            if not href:
                continue
            url = urljoin(self.adapter.adapter.base_url, href)
            links.append(url)
        return links

    async def _crawl_product(self, url: str, category_path: str) -> CrawlResult | None:
        page = await self.engine.new_page()
        try:
            logger.info("crawl product supplier=%s url=%s", self.supplier_name, url)
            await page.goto(url, wait_until=self.adapter.adapter.browser.wait_until)
            product_config = self.adapter.adapter.product

            fields: dict[str, Any] = {}
            for field_name in ("supplier_product_id", "supplier_product_code", "raw_product_name",
                               "supply_price", "origin", "main_image_url", "detail_content",
                               "extra_image_urls", "brand_name", "manufacturer", "model_name"):
                extractor: FieldExtractor | None = getattr(product_config, field_name, None)
                if extractor is None or extractor.optional is False and not extractor.selector:
                    fields[field_name] = None
                    continue
                fields[field_name] = await self._extract_field(page, extractor)

            status_value = None
            if product_config.supplier_status:
                status_value = await self._extract_field(page, product_config.supplier_status)
            status_mapping = product_config.status_mapping.mapping
            mapped_status = _map_supplier_status(status_value, status_mapping, product_config.status_mapping.default)

            supply_price_raw = fields.get("supply_price")
            supply_price = _extract_number(str(supply_price_raw)) if isinstance(supply_price_raw, str) else supply_price_raw

            main_image = fields.get("main_image_url")
            main_image = _supported_image_url(main_image)

            detail_images = _without_images(_image_values(fields.get("detail_content")), main_image, page.url)
            detail = ",".join(detail_images) or None

            extra_images = _without_images(_image_values(fields.get("extra_image_urls")), main_image, page.url)

            raw_meta: dict[str, Any] = {
                "url": url,
                "supplier_product_id": fields.get("supplier_product_id"),
                "supplier_product_code": fields.get("supplier_product_code"),
                "raw_product_name": fields.get("raw_product_name"),
                "supply_price_raw": fields.get("supply_price"),
                "status_raw": status_value,
            }

            product = StandardProduct(
                supplier_name=self.supplier_name,
                supplier_product_id=str(fields.get("supplier_product_id") or "").strip() or None,
                supplier_product_code=str(fields.get("supplier_product_code") or "").strip() or url,
                supplier_status=mapped_status,
                raw_product_name=str(fields.get("raw_product_name") or "").strip() or "이름 없음",
                origin=str(fields.get("origin") or "").strip() or None if isinstance(fields.get("origin"), str) else fields.get("origin"),
                supply_price=supply_price,
                main_image_url=main_image if isinstance(main_image, str) else None,
                detail_content=detail,
                supplier_category=category_path,
                extra_image_urls=extra_images,
                brand_name=str(fields.get("brand_name")).strip() if fields.get("brand_name") else None,
                manufacturer=str(fields.get("manufacturer")).strip() if fields.get("manufacturer") else None,
                model_name=str(fields.get("model_name")).strip() if fields.get("model_name") else None,
                raw_metadata=raw_meta,
            )

            options = await self._extract_options(page, product.supplier_product_code, supply_price)
            logger.info(
                "crawl product extracted supplier=%s code=%s options=%d",
                self.supplier_name,
                product.supplier_product_code,
                len(options),
            )
            return CrawlResult(product=product, options=options)
        except Exception as exc:
            log_exception(logger, f"crawl product failed supplier={self.supplier_name} url={url}", exc)
            raise
        finally:
            await page.close()

    async def _extract_field(self, page, extractor: FieldExtractor) -> Any:
        try:
            if extractor.selector:
                if extractor.multiple:
                    elements = await page.query_selector_all(extractor.selector)
                    values: list[str] = []
                    for el in elements:
                        val = await self._read_element(el, extractor)
                        if val:
                            values.append(val)
                    if values:
                        return values
                else:
                    element = await page.query_selector(extractor.selector)
                    if element:
                        raw = await self._read_element(element, extractor)
                        if raw:
                            return _apply_transform(raw, extractor.transform)

            fallback_value = await self._extract_field_fallback_from(page, extractor)
            if fallback_value is not None:
                return _apply_transform(fallback_value, extractor.transform)
            if extractor.fallback:
                return _apply_transform(extractor.fallback, extractor.transform)
            return None
        except Exception as exc:
            logger.warning("field extraction failed selector=%s: %s", extractor.selector, exc)
            if extractor.fallback:
                return _apply_transform(extractor.fallback, extractor.transform)
            return None

    async def _extract_field_fallback_from(self, page, extractor: FieldExtractor) -> str | None:
        if extractor.fallback_from == "url":
            return extract_url_value(page.url, extractor)

        if extractor.fallback_from == "maxq":
            maxq = await page.query_selector("input[name='maxq']")
            if not maxq:
                return None
            return _status_from_maxq_value(await maxq.get_attribute("value"))

        if extractor.fallback_from == "cart_button":
            soldout = await page.query_selector(
                "img[src*='soldout'], img[src*='sold_out'], img[alt*='품절'], "
                "img[alt*='soldout'], :text('품절'), :text('soldout'), :text('완판')"
            )
            if soldout:
                return "sold_out"
            cart = await page.query_selector(
                "button:has-text('장바구니'), button:has-text('구매'), button:has-text('주문'), "
                "button:has-text('Buy'), button:has-text('Cart'), "
                "input[type='button'][value*='구매'], input[type='submit'][value*='구매'], "
                "input[type='image'][src*='cart'], input[type='image'][src*='buy'], "
                "img[src*='cart'], img[src*='buy'], img[src*='order'], img[src*='purchase']"
            )
            return "available" if cart else None

        return None

    async def _read_element(self, element, extractor: FieldExtractor) -> str | None:
        if extractor.html:
            return await element.inner_html()
        if extractor.attribute:
            value = await element.get_attribute(extractor.attribute)
            if not value and extractor.fallback_attribute:
                value = await element.get_attribute(extractor.fallback_attribute)
            return value
        return await element.inner_text()

    async def _extract_options(self, page, product_code: str, base_price: int | None) -> list[StandardOption]:
        config = self.adapter.adapter.options
        if config.detection == "none" or not config.groups:
            return []

        if config.dependent_options.enabled:
            return await self._extract_dependent_options(page, config, product_code, base_price)

        options: list[StandardOption] = []
        price_values: list[int | None] = []
        if config.option_price_delta and config.option_price_delta.multiple:
            price_raw = await self._extract_field(page, config.option_price_delta)
            if isinstance(price_raw, list):
                price_values = [
                    _extract_number(str(item)) if not isinstance(item, int) else item
                    for item in price_raw
                ]
        for group_config in config.groups:
            values = await page.query_selector_all(group_config.values_selector)
            for index, el in enumerate(values):
                raw_value_text = await self._read_option_value(el, group_config)
                value_text, text_price_delta = _split_option_text_price(raw_value_text)
                if not value_text:
                    continue
                option_data = {
                    "option_group_1": group_config.name,
                    "option_value_1": value_text,
                    "option_value_2": None,
                    "option_value_3": None,
                }
                price_delta = None
                option_supply = None
                if price_values:
                    option_supply = price_values[index] if index < len(price_values) else None
                    price_delta = derive_option_price_delta(option_supply, base_price)
                elif config.option_price_delta:
                    price_delta_raw = await self._extract_field(page, config.option_price_delta)
                    price_delta = _extract_signed_number(str(price_delta_raw)) if isinstance(price_delta_raw, str) else price_delta_raw
                    option_supply = (base_price or 0) + (price_delta or 0) if base_price else None
                elif text_price_delta is not None:
                    price_delta = text_price_delta
                    option_supply = base_price + price_delta if base_price is not None else None
                image_url = None
                if config.option_image_url:
                    image_url = await self._extract_field(page, config.option_image_url)

                stock = None
                if config.option_stock_quantity:
                    stock_raw = await self._extract_field(page, config.option_stock_quantity)
                    stock = _extract_number(str(stock_raw)) if isinstance(stock_raw, str) else stock_raw

                options.append(StandardOption(
                    supplier_product_code=product_code,
                    option_sku=f"{product_code}-{index + 1}" if product_code else None,
                    option_type=config.type,
                    option_group_1=group_config.name,
                    option_value_1=value_text,
                    option_group_2=None,
                    option_value_2=None,
                    option_group_3=None,
                    option_value_3=None,
                    option_display_name=build_option_display_name(option_data),
                    option_supply_price=option_supply,
                    option_sale_price=None,
                    option_price_delta=price_delta,
                    option_stock_quantity=stock,
                    option_status=None,
                    option_usable=True,
                    option_main_image_url=image_url if isinstance(image_url, str) else None,
                    option_extra_image_urls=[],
                    option_position=index + 1,
                    raw_option_text=raw_value_text,
                    raw_option_metadata={"group": group_config.name, "value": value_text},
                ))
        return options

    async def _extract_dependent_options(
        self, page, config: OptionsConfig, product_code: str, base_price: int | None
    ) -> list[StandardOption]:
        dep = config.dependent_options
        if not config.groups or not dep.level_2_values_selector:
            return []

        level1_config = config.groups[0]
        level1_elements = await page.query_selector_all(level1_config.values_selector)
        level1_values: list[str] = []
        for el in level1_elements:
            value_text = await self._read_option_value(el, level1_config)
            if value_text:
                level1_values.append(value_text)

        options: list[StandardOption] = []
        position = 1
        for l1_value in level1_values:
            try:
                level1_el = await page.query_selector(f"{level1_config.values_selector}:has-text('{l1_value}')")
                if level1_el:
                    if dep.level_2_trigger == "click":
                        await level1_el.click()
                    elif dep.level_2_trigger == "select":
                        await level1_el.select_option(label=l1_value)
                    if dep.level_2_load_indicator:
                        try:
                            await page.wait_for_selector(dep.level_2_load_indicator, timeout=5000)
                            await page.wait_for_selector(dep.level_2_load_indicator, state="detached", timeout=5000)
                        except Exception:
                            pass
                    else:
                        await page.wait_for_timeout(800)
                level2_elements = await page.query_selector_all(dep.level_2_values_selector)
                for l2_el in level2_elements:
                    l2_value = await l2_el.inner_text()
                    if not l2_value.strip():
                        continue
                    l2_value = l2_value.strip()
                    option_data = {
                        "option_group_1": dep.level_1_group or level1_config.name,
                        "option_value_1": l1_value,
                        "option_group_2": dep.level_2_group,
                        "option_value_2": l2_value,
                        "option_value_3": None,
                    }
                    options.append(StandardOption(
                        supplier_product_code=product_code,
                        option_sku=f"{product_code}-{position}" if product_code else None,
                        option_type="combination",
                        option_group_1=dep.level_1_group or level1_config.name,
                        option_value_1=l1_value,
                        option_group_2=dep.level_2_group,
                        option_value_2=l2_value,
                        option_group_3=None,
                        option_value_3=None,
                        option_display_name=build_option_display_name(option_data),
                        option_supply_price=base_price,
                        option_sale_price=None,
                        option_price_delta=derive_option_price_delta(base_price, base_price),
                        option_stock_quantity=None,
                        option_status=None,
                        option_usable=True,
                        option_main_image_url=None,
                        option_extra_image_urls=[],
                        option_position=position,
                        raw_option_text=f"{l1_value} / {l2_value}",
                        raw_option_metadata={"level1": l1_value, "level2": l2_value},
                    ))
                    position += 1
            except Exception:
                continue
        return options

    async def _read_option_value(self, element, group_config) -> str | None:
        if group_config.value_text == "value":
            return await element.get_attribute("value")
        if group_config.value_text == "attribute" and group_config.value_attribute:
            return await element.get_attribute(group_config.value_attribute)
        return await element.inner_text()

    async def stock_check(
        self,
        category_id: str | None = None,
    ) -> AsyncIterator[StockSnapshotData]:
        config = self.adapter.adapter
        pagination = config.listing.pagination
        url_template = config.categories.url_template

        # Perform login if needed
        login_config = self.adapter.adapter.login
        if login_config.required:
            login_page = await self.engine.new_page()
            try:
                login_ok = await self._perform_login(login_page)
                if not login_ok:
                    raise RuntimeError("도매처 로그인에 실패했습니다. 도매처 관리 탭에서 계정 정보를 확인하세요.")
            finally:
                await login_page.close()

        page_num = pagination.start
        while page_num <= pagination.max_pages:
            if url_template and category_id:
                list_url = url_template.format(category_id=category_id, page=page_num)
            else:
                list_url = category_id or ""

            page = await self.engine.new_page()
            try:
                await page.goto(list_url, wait_until=config.browser.wait_until)
                product_links = await self._extract_product_links(page)
                if not product_links:
                    break

                for link_url in product_links:
                    snapshot = await self._stock_check_product(link_url)
                    if snapshot:
                        yield snapshot
                    if self.delay_seconds > 0:
                        await asyncio.sleep(self.delay_seconds)
            finally:
                await page.close()
            page_num += 1

    async def _stock_check_product(self, url: str) -> StockSnapshotData | None:
        page = await self.engine.new_page()
        try:
            await page.goto(url, wait_until=self.adapter.adapter.browser.wait_until)
            product_config = self.adapter.adapter.product

            status_value = None
            if product_config.supplier_status:
                status_value = await self._extract_field(page, product_config.supplier_status)
            status_mapping = product_config.status_mapping.mapping
            mapped_status = _map_supplier_status(status_value, status_mapping, product_config.status_mapping.default)

            price = None
            if product_config.supply_price:
                price_raw = await self._extract_field(page, product_config.supply_price)
                price = _extract_number(str(price_raw)) if isinstance(price_raw, str) else price_raw

            code = url
            if product_config.supplier_product_code:
                code_raw = await self._extract_field(page, product_config.supplier_product_code)
                if code_raw and isinstance(code_raw, str):
                    code = code_raw.strip()

            return StockSnapshotData(
                supplier_product_code=code,
                supplier_status=mapped_status,
                supply_price=price,
            )
        except Exception as exc:
            logger.warning("stock product failed supplier=%s url=%s: %s", self.supplier_name, url, exc)
            return None
        finally:
            await page.close()

    async def close(self) -> None:
        pass
