from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence

from PySide6.QtCore import QThread, Signal

from app.analyzer.adapter_generator import generate_adapter_yaml
from app.analyzer.element_picker import pick_element
from app.analyzer.site_probe import probe_site
from app.crawlers.yaml_adapter import _status_from_maxq_value


class PickerWorker(QThread):
    finished = Signal(object, str)
    error = Signal(str)

    def __init__(self, field_path: str, target_url: str, login_url: str | None,
                 username: str | None, password: str | None,
                 login_config: dict[str, str] | None = None) -> None:
        super().__init__()
        self.field_path = field_path
        self.target_url = target_url
        self.login_url = login_url
        self.username = username
        self.password = password
        self.login_config = login_config

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(pick_element(
                self.target_url, login_url=self.login_url, username=self.username,
                password=self.password, login_config=self.login_config,
            ))
            self.finished.emit(result, self.field_path)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.password = None
            loop.close()


class ProbeWorker(QThread):
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, main_url: str, listing_url: str | None = None,
                 detail_url: str | None = None, login_url: str | None = None,
                 username: str | None = None, password: str | None = None) -> None:
        super().__init__()
        self.main_url = main_url
        self.listing_url = listing_url
        self.detail_url = detail_url
        self.login_url = login_url
        self.username = username
        self.password = password

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(probe_site(
                self.main_url, self.listing_url, self.detail_url, headless=True,
                on_progress=self.progress.emit, login_url=self.login_url,
                username=self.username, password=self.password,
            ))
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.password = None
            loop.close()


class GenerateWorker(QThread):
    finished = Signal(str, str, int)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, probe_result, supplier_name: str, provider: str = "gemini",
                 mapping_hints: list | None = None) -> None:
        super().__init__()
        self.probe_result = probe_result
        self.supplier_name = supplier_name
        self.provider = provider
        self.mapping_hints = list(mapping_hints or [])

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(generate_adapter_yaml(
                self.probe_result, self.supplier_name, llm_provider=self.provider,
                on_progress=self.progress.emit, mapping_hints=self.mapping_hints,
            ))
            self.finished.emit(result.yaml_text, result.provider_used, result.retries)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            loop.close()


class AdapterTestWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)
    progress = Signal(str)

    FIELD_NAMES = (
        "supplier_product_id", "supplier_product_code", "raw_product_name",
        "supplier_status", "supply_price", "origin", "main_image_url",
        "detail_content", "extra_image_urls", "brand_name",
    )

    def __init__(self, adapter_yaml: str, test_url: str | Sequence[str],
                 tested_yaml_hash: str, login_url: str | None,
                 username: str | None, password: str | None,
                 fields: Sequence[str] | None = None) -> None:
        super().__init__()
        self.adapter_yaml = adapter_yaml
        self.test_urls = [test_url] if isinstance(test_url, str) else list(test_url)
        self.tested_yaml_hash = tested_yaml_hash
        self.login_url = login_url
        self.username = username
        self.password = password
        self.fields = tuple(fields or self.FIELD_NAMES)
        self.raw_results: dict[str, list[dict]] = {}

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        try:
            self.finished.emit(loop.run_until_complete(self._run_test()))
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.password = None
            loop.close()

    async def _run_test(self) -> dict:
        from app.crawlers.engine import create_engine
        from app.crawlers.registry import load_adapter_from_text

        adapter = load_adapter_from_text(self.adapter_yaml)
        aggregate: dict[str, list[dict]] = {name: [] for name in self.fields}
        async with create_engine(headless=True) as engine:
            page = await engine.new_page()
            if self.login_url and self.username and self.password:
                await self._login(page)
            product = adapter.adapter.product
            for url in self.test_urls:
                self.progress.emit(f"테스트 페이지 접속: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(1500)
                for field_name in self.fields:
                    extractor = getattr(product, field_name, None)
                    value = error = None
                    if extractor:
                        self.progress.emit(f"테스트 중: {field_name}")
                        try:
                            value = await self._extract_test_field(page, extractor)
                        except Exception as exc:
                            error = str(exc)
                    aggregate[field_name].append(
                        {"url": url, "value": value, "ok": bool(value), "error": error}
                    )
            await page.close()
        self.raw_results = aggregate
        results: dict = {"__raw_results__": aggregate}
        for field_name, entries in aggregate.items():
            hits = [entry["value"] for entry in entries if entry["value"]]
            results[field_name] = (hits[0] if hits else None) if len(self.test_urls) == 1 else (
                f"{len(hits)}/{len(entries)} 성공 · {str(hits[0])[:60] if hits else '실패'}"
            )
        return results

    async def _login(self, page) -> None:
        self.progress.emit("로그인 중...")
        await page.goto(self.login_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(1500)
        try:
            pw = await page.query_selector("input[type='password']")
            if not pw:
                return
            user = await page.query_selector("input[type='text'], input[type='email'], input[name*='id']")
            if user:
                await user.fill(self.username)
                await pw.fill(self.password)
                for selector in ("button[type='submit']", "input[type='submit']", "input[type='image']"):
                    button = await page.query_selector(selector)
                    if button:
                        await button.click()
                        break
                await page.wait_for_timeout(3000)
        except Exception:
            pass

    async def _extract_test_field(self, page, extractor) -> str | None:
        if extractor.selector:
            if extractor.multiple:
                elements = await page.query_selector_all(extractor.selector)
                values = [await self._read_test_element(el, extractor) or "" for el in elements[:5]]
                value = ", ".join(item[:50] for item in values if item) or None
                if value:
                    return value
            else:
                element = await page.query_selector(extractor.selector)
                if element:
                    value = await self._read_test_element(element, extractor)
                    if value:
                        if extractor.transform == "extract_number":
                            match = re.search(r"-?\d[\d,]*", value)
                            value = match.group().replace(",", "") if match else value
                        return value.strip()[:100]
        value = await self._extract_test_fallback_from(page, extractor)
        if value is None:
            value = extractor.fallback or None
        if value and extractor.transform == "extract_number":
            match = re.search(r"-?\d[\d,]*", value)
            value = match.group().replace(",", "") if match else value
        return value.strip()[:100] if value else None

    async def _read_test_element(self, element, extractor) -> str | None:
        if extractor.html:
            return await element.inner_html()
        if extractor.attribute:
            value = await element.get_attribute(extractor.attribute)
            return value or (await element.get_attribute(extractor.fallback_attribute) if extractor.fallback_attribute else None)
        return await element.inner_text()

    async def _extract_test_fallback_from(self, page, extractor) -> str | None:
        if extractor.fallback_from == "maxq":
            maxq = await page.query_selector("input[name='maxq']")
            return _status_from_maxq_value(await maxq.get_attribute("value")) if maxq else None
        if extractor.fallback_from == "cart_button":
            soldout = await page.query_selector("img[src*='soldout'], img[src*='sold_out'], img[alt*='품절'], img[alt*='soldout'], :text('품절'), :text('soldout'), :text('완판')")
            if soldout:
                return "sold_out"
            cart = await page.query_selector("button:has-text('장바구니'), button:has-text('구매'), button:has-text('주문'), input[type='image'][src*='cart'], input[type='image'][src*='buy'], img[src*='cart'], img[src*='buy'], img[src*='order'], img[src*='purchase']")
            return "available" if cart else None
        return None


TestWorker = AdapterTestWorker
