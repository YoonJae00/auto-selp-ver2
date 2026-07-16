from __future__ import annotations

import re
import time
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from app.analyzer.adapter_schema import clean_field_value, extract_url_value
from app.analyzer.element_picker import (
    INSTRUCTION_OVERLAY_SCRIPT,
    MAPPING_PREVIEW_SCRIPT,
    PICKER_INSTALL_SCRIPT,
    PickedElement,
    choose_best_selector,
    resolve_login_selectors,
    sanitize_attrs,
    sanitize_html_preview,
    sanitize_value,
)
from app.analyzer.option_text_parser import parse_option_text, format_option_group
from app.crawlers.yaml_adapter import is_soldout_text
from app.config import load_config


def _sync_option_soldout(element, text: str) -> bool:
    """옵션 요소 품절 판정 (sync). yaml_adapter.option_is_soldout의 sync 최소판."""
    if is_soldout_text(text):
        return True
    try:
        if element.get_attribute("disabled") is not None:
            return True
        cls = (element.get_attribute("class") or "").lower()
        return "soldout" in cls or "sold_out" in cls or "품절" in cls
    except Exception:
        return False


def _apply_preview_transform(value: str | None, transform: str | None) -> str | None:
    if not value:
        return None
    if transform == "extract_number":
        match = re.search(r"-?\d[\d,]*", value)
        return match.group().replace(",", "") if match else value.strip()
    if transform == "extract_signed_number":
        match = re.search(r"([+-]?)\s*([\d,]+)", value)
        if not match:
            return value.strip()
        sign = "-" if match.group(1) == "-" else ""
        return sign + match.group(2).replace(",", "")
    return value.strip()[:100]


def _safe_goto(page: Page, url: str, wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] = "domcontentloaded") -> bool:
    """Safely navigate to a URL with fallback.  Sync version of login_helper._safe_goto."""
    try:
        page.goto(url, wait_until=wait_until, timeout=15_000)
        page.wait_for_timeout(1500)
        return True
    except Exception:
        try:
            page.goto(url, wait_until="commit", timeout=10_000)
            page.wait_for_timeout(2000)
            return True
        except Exception:
            return False


def _try_submit_selectors(page: Page, selectors: list[str]) -> bool:
    """Sync version of login_helper._try_submit_selectors."""
    for sel in selectors:
        try:
            btn = page.query_selector(sel)
            if btn:
                btn.click()
                return True
        except Exception:
            continue
    return False


MODAL_TRIGGER_SELECTORS = [
    "button:has-text('로그인')",
    "a:has-text('로그인')",
    "button:has-text('LOGIN')",
    "a:has-text('LOGIN')",
    "button:has-text('Log in')",
    "a:has-text('Log in')",
    "button:has-text('Sign in')",
    "a:has-text('Sign in')",
    "button:has-text('로그인하기')",
    "a:has-text('로그인하기')",
    "[data-modal*='login']",
    "[data-bs-toggle='modal']",
    "[data-toggle='modal']",
    "[aria-haspopup='dialog']",
    "[data-bs-target*='login']",
    "[data-target*='login']",
]


def _open_login_modal(page: Page) -> bool:
    """Sync: password 필드 invisible일 때 모달 트리거 클릭 시도."""
    for sel in MODAL_TRIGGER_SELECTORS:
        try:
            el = page.query_selector(sel)
            if el:
                try:
                    visible = el.is_visible()
                except Exception:
                    visible = False
                if visible:
                    el.click()
                    page.wait_for_timeout(800)
                    return True
        except Exception:
            continue
    return False


def _ensure_password_visible(page: Page) -> bool:
    """Sync: password 필드 visible해질 때까지 모달 트리거 시도."""
    try:
        pw = page.query_selector("input[type='password']")
        if pw is not None:
            try:
                if pw.is_visible():
                    return True
            except Exception:
                pass
    except Exception:
        pass
    for _ in range(3):
        if _open_login_modal(page):
            try:
                page.wait_for_selector("input[type='password']", state="visible", timeout=3000)
                return True
            except Exception:
                continue
        else:
            break
    return False


def _check_logout_indicators(page: Page) -> bool:
    """Sync version of login_helper._check_logout_indicators."""
    logout_indicators = [
        "a[href*='logout']",
        "img[src*='logout']",
        "a:has-text('로그아웃')",
        "a:has-text('LOGOUT')",
    ]
    try:
        for sel in logout_indicators:
            el = page.query_selector(sel)
            if el:
                return True
    except Exception:
        pass
    return False


def _try_fill_field(page: Page, candidates: list[str], value: str) -> bool:
    """Try to find and fill an input using candidate selectors.  Sync version."""
    for sel in candidates:
        try:
            el = page.wait_for_selector(sel, state="visible", timeout=5000)
            if el:
                el.fill(value)
                return True
        except Exception:
            continue
    return False


class PickerSession:
    """Persistent browser session for the element picker.

    Uses Playwright's **sync API** so it can live across multiple QThread
    invocations without being tied to an asyncio event loop.
    """

    def __init__(self, headless: bool = False) -> None:
        self._headless = headless
        self._playwright = None
        self._browser: BrowserContext | None = None
        self._page: Page | None = None
        self._logged_in = False
        self._login_url: str | None = None
        self._current_url: str | None = None
        self._temp_dir: Path | None = None

    @property
    def is_open(self) -> bool:
        try:
            if self._browser is None or self._page is None or self._page.is_closed():
                return False
            return any(not page.is_closed() for page in self._browser.pages)
        except Exception:
            return False

    @property
    def is_logged_in(self) -> bool:
        return self._logged_in

    def open(self, storage_state: dict | None = None) -> None:
        """Start the browser. storage_state가 있으면 쿠키+localStorage 주입.

        Reuses the temp-profile + channel-fallback pattern from PlaywrightEngine.
        """
        if self._browser is not None:
            return

        config = load_config()
        requested_channel = config.browser_channel
        self._playwright = sync_playwright().start()

        self._temp_dir = Path(tempfile.mkdtemp(prefix="picker_session_"))
        profile_dir = self._temp_dir

        launch_kwargs: dict[str, Any] = {
            "headless": self._headless,
            "user_data_dir": str(profile_dir),
        }
        if requested_channel and requested_channel != "chromium":
            launch_kwargs["channel"] = requested_channel

        raw: BrowserContext | Browser | None = None
        try:
            raw = self._playwright.chromium.launch_persistent_context(**launch_kwargs)
        except Exception:
            if requested_channel != "chromium":
                launch_kwargs.pop("channel", None)
                try:
                    raw = self._playwright.chromium.launch_persistent_context(**launch_kwargs)
                except Exception:
                    launch_kwargs.pop("user_data_dir", None)
                    raw = self._playwright.chromium.launch(**launch_kwargs)
            else:
                raise

        assert raw is not None

        # Normalise to BrowserContext: launch() returns Browser, convert it
        if isinstance(raw, Browser):
            self._browser = raw.new_context()
        else:
            self._browser = raw

        self._browser.set_default_navigation_timeout(20_000)
        self._browser.set_default_timeout(20_000)

        # Install the picker listeners before any page script runs on every future
        # navigation/frame, so we win the capture-phase race against sites that
        # register their own window/document click blockers on load.
        try:
            self._browser.add_init_script(PICKER_INSTALL_SCRIPT)
        except Exception:
            pass

        # storage_state 주입 (1단계 probe에서 추출한 세션)
        if storage_state:
            try:
                self._browser.add_cookies(storage_state.get("cookies", []))
                origins = storage_state.get("origins", [])
                if origins:
                    import json as _json
                    script_parts = []
                    for origin in origins:
                        ls = origin.get("localStorage", [])
                        if ls:
                            # Playwright localStorage entry: {"name": "...", "value": "..."}
                            entries = []
                            for item in ls:
                                if isinstance(item, dict) and "name" in item and "value" in item:
                                    entries.append({"name": item["name"], "value": item["value"]})
                            if entries:
                                script_parts.append(
                                    f"if(location.origin==={_json.dumps(origin.get('origin',''))}){{"
                                    f"try{{var ls=window.localStorage;"
                                    f"var d={_json.dumps(entries)};"
                                    f"d.forEach(function(e){{ls.setItem(e.name,e.value);}});"
                                    f"}}catch(e){{}}}}"
                                )
                    if script_parts:
                        self._browser.add_init_script("(() => {" + "".join(script_parts) + "})()")
            except Exception:
                pass

        # Use the first page if one was auto-created, otherwise make one
        if self._browser.pages:
            self._page = self._browser.pages[0]
        else:
            self._page = self._browser.new_page()

    def _ensure_page(self) -> Page:
        """Return a live page, re-creating if needed (e.g. user closed the tab or browser)."""
        if self._page is None or self._page.is_closed():
            try:
                if self._browser is not None:
                    if self._browser.pages:
                        self._page = self._browser.pages[0]
                    else:
                        self._page = self._browser.new_page()
                else:
                    self.open()
                    assert self._page is not None
            except Exception:
                # 브라우저 프로세스 자체가 죽었을 때 → 완전 재시작
                self.close()
                self.open()
                assert self._page is not None
        return self._page

    def _verify_logged_in(self, page: Page) -> bool:
        """Check whether the browser is actually authenticated after a login attempt.

        Returns True only when there is evidence of a logged-in session:
        a logout link/text is present, OR the password input has disappeared.
        """
        if _check_logout_indicators(page):
            return True
        # If a password field is still visible, we're still on the login page → failed.
        try:
            still_has_password = page.query_selector("input[type='password']")
        except Exception:
            still_has_password = None
        return still_has_password is None

    def get_storage_state(self) -> dict | None:
        """현재 브라우저 컨텍스트의 storage_state 추출 (로그인 후 세션 공유용)."""
        if self._browser is None:
            return None
        try:
            return dict(self._browser.storage_state())  # type: ignore[return-value]
        except Exception:
            return None

    def login(
        self,
        login_url: str,
        username: str,
        password: str,
        login_config: dict[str, str] | None = None,
    ) -> bool:
        """Login using the shared login logic, adapted to the sync Playwright API.

        Replicates the behaviour of login_helper.perform_login but with sync API calls.
        """
        page = self._ensure_page()

        if not _safe_goto(page, login_url):
            return False

        # If login_config provides any explicit selectors, use selector-based approach
        if login_config and (
            login_config.get("id_selector")
            or login_config.get("password_selector")
            or login_config.get("submit_selector")
        ):
            return self._login_via_selectors(page, username, password, login_config)

        # Otherwise, use the robust form-based approach
        return self._login_via_form_heuristics(page, username, password)

    def get_login_page_html(self) -> str:
        """Return the current page's HTML for LLM analysis, including iframe content."""
        page = self._ensure_page()
        parts: list[str] = []
        try:
            parts.append(page.content())
        except Exception:
            pass
        # Collect iframe content (MakeShop puts login form in iframe)
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            try:
                iframe_html = frame.content()
                if iframe_html and iframe_html.strip():
                    parts.append(f"\n<!-- IFRAME CONTENT -->\n{iframe_html}")
            except Exception:
                continue
        html = "\n".join(parts)
        # Limit to 20000 chars for LLM token budget
        return html[:20000]

    def _login_via_selectors(
        self, page: Page, username: str, password: str, login_config: dict[str, str]
    ) -> bool:
        """Login using explicit selectors resolved from login_config."""
        selectors = resolve_login_selectors(login_config)

        # 모달 로그인 처리: password 필드 invisible이면 모달 트리거
        _ensure_password_visible(page)

        # Fill username
        if not _try_fill_field(page, selectors["id_candidates"], username):
            return False

        # Fill password
        if not _try_fill_field(page, selectors["password_candidates"], password):
            return False

        # Click submit
        if not _try_submit_selectors(page, selectors["submit_candidates"]):
            return False

        # Wait for navigation
        page.wait_for_timeout(3000)

        # Check success indicator if provided
        if selectors["success_indicator"]:
            try:
                page.wait_for_selector(
                    selectors["success_indicator"], state="visible", timeout=5000
                )
                self._logged_in = True
                self._login_url = page.url
                self._current_url = page.url
                return True
            except Exception:
                pass

        # No explicit success indicator (or it failed): verify via logout/password-absence
        if self._verify_logged_in(page):
            self._logged_in = True
            self._login_url = page.url
            self._current_url = page.url
            return True
        # Login failed — do NOT mark as logged in
        return False

    def _find_login_inputs(self, page: Page):
        """Find (id_input, password_input) on the main page or any child frame.

        Returns a tuple of (id_element, password_element) or (None, None).
        """
        # 모달 로그인 처리: password 필드 invisible이면 모달 트리거
        _ensure_password_visible(page)
        # Try main page first — visible password handle만 반환
        password_input = page.query_selector("input[type='password']")
        if password_input is not None:
            try:
                if not password_input.is_visible():
                    password_input = None
            except Exception:
                password_input = None
        if password_input is not None:
            form = password_input.evaluate("el => el.closest('form')")
            if form:
                id_input = page.query_selector(
                    "form input[type='text'], form input[type='email'], "
                    "form input[name*='id'], form input[name*='user'], form input[name*='member']"
                )
            else:
                id_input = page.query_selector("input[type='text'], input[type='email']")
            return id_input, password_input

        # Search child frames (e.g. MakeShop login forms inside iframes).
        # Retry briefly because the iframe may not be ready immediately after navigation.
        for _ in range(6):
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                try:
                    pw = frame.query_selector("input[type='password']")
                    if pw is not None:
                        try:
                            if not pw.is_visible():
                                continue
                        except Exception:
                            continue
                        form = pw.evaluate("el => el.closest('form')")
                        if form:
                            id_input = frame.query_selector(
                                "form input[type='text'], form input[type='email'], "
                                "form input[name*='id'], form input[name*='user'], form input[name*='member']"
                            )
                        else:
                            id_input = frame.query_selector("input[type='text'], input[type='email']")
                        return id_input, pw
                except Exception:
                    continue
            # No password field in any frame yet — wait and retry
            page.wait_for_timeout(500)
        return None, None

    def _login_via_form_heuristics(
        self, page: Page, username: str, password: str
    ) -> bool:
        """Robust form-based login: find password input, find form, find id input."""

        # Find login inputs on main page or inside iframes (e.g. MakeShop)
        id_input, password_input = self._find_login_inputs(page)
        if not password_input:
            return False
        if not id_input:
            return False

        try:
            id_input.fill(username)
        except Exception as exc:
            return False
        try:
            password_input.fill(password)
        except Exception as exc:
            return False

        # Find and click submit button (includes MakeShop javascript:check() patterns)
        submit_selectors = [
            "form button[type='submit']",
            "form input[type='submit']",
            "form input[type='image']",
            "form button:has-text('로그인')",
            "form a:has-text('로그인')",
            "form img[src*='login']",
            "form a[href*='javascript:check']",
            "form a[href*='check()']",
            "a[href*='javascript:check']",
            "a[href*='check()']",
            "a:has(img[src*='login'])",
            "button[type='submit']",
            "input[type='submit']",
            "input[type='image']",
        ]

        submitted = _try_submit_selectors(page, submit_selectors)

        if not submitted:
            # MakeShop fallback: call check() directly in the frame holding the form.
            # MakeShop's login uses a javascript:check() link that validates + submits;
            # clicking the anchor via Playwright doesn't always fire the handler.
            try:
                frame = password_input.owner_frame()
                if frame is not None:
                    frame.evaluate("typeof check === 'function' ? check() : undefined")
                    submitted = True
            except Exception:
                pass

        if not submitted:
            # Try pressing Enter in the password field
            try:
                password_input.press("Enter")
                submitted = True
            except Exception:
                pass

        if not submitted:
            return False

        # Wait for navigation
        page.wait_for_timeout(3000)

        # Verify login actually succeeded
        if self._verify_logged_in(page):
            self._logged_in = True
            self._login_url = page.url
            self._current_url = page.url
            return True
        # Login failed — do NOT mark as logged in
        return False

    def pick(
        self,
        url: str,
        field_label: str = "",
        field_hint: str = "",
        timeout_ms: int = 60_000,
        field_path: str = "",
    ) -> PickedElement:
        """Navigate to *url* (if different from current) and run the picker script.

        Returns a PickedElement parsed from the user's click.
        """
        page = self._ensure_page()

        # Navigate only if the URL changed
        if url and url != self._current_url:
            page.goto(url, wait_until="domcontentloaded", timeout=20_000)
            page.wait_for_timeout(1000)
            self._current_url = url
            # Detect login redirect ONLY when the session is not yet authenticated.
            # Some sites (e.g. MakeShop) keep a login form in the page header even
            # after a successful login, so checking for a password field when
            # already logged in would false-positive and block the picker.
            if not self._logged_in:
                try:
                    pw = page.query_selector("input[type='password']")
                    if pw is not None and not _check_logout_indicators(page):
                        # 모달 트리거 시도 후에도 visible하지 않으면 에러
                        if not _ensure_password_visible(page):
                            raise RuntimeError(
                                "로그인이 필요한 페이지입니다. 로그인 정보를 확인한 뒤 다시 시도하세요."
                            )
                except RuntimeError:
                    raise
                except Exception:
                    pass

        # Inject instruction overlay before picker runs
        if field_label or field_hint:
            page.evaluate(INSTRUCTION_OVERLAY_SCRIPT, [field_label, field_hint])

        # Run the picker script; it returns a Promise that resolves on click.
        # ponytail: bump timeout to 120s only for this interactive evaluate — user may take >20s to find the element
        page.set_default_timeout(120_000)
        try:
            raw = self._evaluate_picker(page, timeout_ms)
            if raw is None:
                raise RuntimeError("picker cancelled")
        finally:
            page.set_default_timeout(20_000)
            try:
                page.evaluate("() => { const ov = document.getElementById('__picker-overlay'); if (ov && ov.parentNode) ov.parentNode.removeChild(ov); const tip = document.getElementById('__picker-tip'); if (tip && tip.parentNode) tip.parentNode.removeChild(tip); }")
            except Exception:
                pass

        candidates = [
            sanitize_value(v, 220)
            for v in raw.get("selectorCandidates", [])
            if sanitize_value(v, 220)
        ]
        counts = {
            str(k): int(v)
            for k, v in (raw.get("matchCounts") or {}).items()
            if str(k) in candidates
        }
        image_candidates: list[dict] = []
        image_default_selector = ""
        if field_path in {"adapter.product.detail_content", "adapter.product.extra_image_urls"}:
            detail_context = self._detail_image_context(page, candidates)
            detail_selectors = [
                sanitize_value(v, 220)
                for v in detail_context.get("selectors", [])
                if sanitize_value(v, 220)
            ]
            if detail_selectors:
                candidates = detail_selectors
                counts = {
                    str(k): int(v)
                    for k, v in (detail_context.get("matchCounts") or {}).items()
                    if str(k) in candidates
                }
                image_default_selector = sanitize_value(detail_context.get("defaultSelector"), 220)
            image_candidates = [
                {
                    "selector": sanitize_value(item.get("selector"), 220),
                    "src": sanitize_value(item.get("src"), 300),
                    "dataSrc": sanitize_value(item.get("dataSrc"), 300),
                    "alt": sanitize_value(item.get("alt"), 160),
                    "classes": sanitize_value(item.get("classes"), 160),
                }
                for item in list(detail_context.get("images") or [])[:20]
                if isinstance(item, dict)
            ]
        elif field_path in {"adapter.options.groups.0.values_selector", "adapter.options.option_price_delta"}:
            option_selector = self._similar_option_selector(page, candidates)
            if option_selector:
                candidates = [option_selector]
                counts = {option_selector: 1}

        return PickedElement(
            url=sanitize_value(raw.get("url"), 300),
            selector=image_default_selector or choose_best_selector(candidates, counts),
            selector_candidates=candidates,
            text=sanitize_value(raw.get("text"), 300),
            html_preview=sanitize_html_preview(raw.get("htmlPreview"), 500),
            attribute_values=sanitize_attrs(raw.get("attributeValues")),
            tag_name=sanitize_value(raw.get("tagName"), 40),
            element_id=sanitize_value(raw.get("elementId"), 120),
            classes=[sanitize_value(c, 80) for c in raw.get("classes", [])[:10]],
            match_counts=counts,
            container_links=list(raw.get("containerLinks") or []),
            image_candidates=image_candidates,
        )

    def _detail_image_context(self, page: Page, candidates: list[str]) -> dict:
        return dict(page.evaluate(
            r"""
            (candidates) => {
              const cssEscape = (window.CSS && CSS.escape)
                ? CSS.escape
                : (s) => String(s).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
              function uniq(arr) {
                const seen = {}, out = [];
                for (const item of arr) if (item && !seen[item]) { seen[item] = 1; out.push(item); }
                return out;
              }
              function nthPath(el) {
                const parts = [];
                for (let node = el; node && node.nodeType === 1 && parts.length < 6; node = node.parentElement) {
                  const tag = node.tagName.toLowerCase();
                  const siblings = Array.prototype.filter.call(
                    node.parentElement ? node.parentElement.children : [],
                    (x) => x.tagName === node.tagName
                  );
                  const idx = siblings.indexOf(node) + 1;
                  // idx=0 (parentElement 없음, 예: html) → :nth-of-type(0)은 아무것도 매칭 안 함
                  parts.unshift(idx > 0 ? `${tag}:nth-of-type(${idx})` : tag);
                }
                return parts.join(' > ');
              }
              function stable(el) {
                const tag = el.tagName.toLowerCase();
                if (el.id) return `#${cssEscape(el.id)}`;
                const classes = Array.prototype.slice.call(el.classList || []).slice(0, 2).filter(Boolean);
                if (classes.length) return `${tag}.${classes.map(cssEscape).join('.')}`;
                return nthPath(el);
              }
              function imgCount(el) {
                return el ? el.querySelectorAll('img[src],img[data-src]').length : 0;
              }
              function imageRows(box) {
                return Array.prototype.slice.call((box || document).querySelectorAll('img[src],img[data-src]'), 0, 20).map((img) => ({
                  selector: stable(img),
                  src: img.getAttribute('src') || '',
                  dataSrc: img.getAttribute('data-src') || '',
                  alt: img.getAttribute('alt') || '',
                  classes: Array.prototype.slice.call(img.classList || []).join(' '),
                }));
              }
              let picked = null;
              for (const sel of candidates || []) {
                try { picked = document.querySelector(sel); } catch (_) {}
                if (picked) break;
              }
              if (!picked || !picked.tagName) return {selectors: [], matchCounts: {}, images: [], defaultSelector: ''};
              const img = picked.tagName.toLowerCase() === 'img' ? picked : picked.querySelector('img[src],img[data-src]');
              if (!img) return {selectors: [stable(picked)], matchCounts: {}, images: [], defaultSelector: stable(picked)};

              const selectors = [stable(img)];
              const pickedImgs = imgCount(picked);
              if (pickedImgs > 0) selectors.push(`${stable(picked)} img`);
              if (img.parentElement && imgCount(img.parentElement) > 0) selectors.push(`${stable(img.parentElement)} img`);

              let group = img.parentElement || img;
              for (let node = group; node && node !== document.body; node = node.parentElement) {
                if (imgCount(node) >= 2) { group = node; break; }
              }
              if (group && group !== img && imgCount(group) > 0) selectors.push(`${stable(group)} img`);

              const finalSelectors = uniq(selectors);
              const counts = {};
              for (const sel of finalSelectors) {
                try { counts[sel] = document.querySelectorAll(sel).length; } catch (_) { counts[sel] = 9999; }
              }
              const defaultSelector = imgCount(group) >= 2 ? `${stable(group)} img` : stable(img);
              const imageBox = pickedImgs > 0 ? picked : group;
              return {selectors: finalSelectors, matchCounts: counts, images: imageRows(imageBox), defaultSelector};
            }
            """,
            candidates,
        ) or {})

    def _similar_option_selector(self, page: Page, candidates: list[str]) -> str:
        return str(page.evaluate(
            r"""
            (candidates) => {
              const cssEscape = (window.CSS && CSS.escape)
                ? CSS.escape
                : (s) => String(s).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
              function nthPath(el) {
                const parts = [];
                for (let node = el; node && node.nodeType === 1 && parts.length < 6; node = node.parentElement) {
                  const tag = node.tagName.toLowerCase();
                  const siblings = Array.prototype.filter.call(
                    node.parentElement ? node.parentElement.children : [],
                    (x) => x.tagName === node.tagName
                  );
                  const idx = siblings.indexOf(node) + 1;
                  // idx=0 (parentElement 없음, 예: html) → :nth-of-type(0)은 아무것도 매칭 안 함
                  parts.unshift(idx > 0 ? `${tag}:nth-of-type(${idx})` : tag);
                }
                return parts.join(' > ');
              }
              function stable(el) {
                const tag = el.tagName.toLowerCase();
                if (el.id) return `#${cssEscape(el.id)}`;
                const classes = Array.prototype.slice.call(el.classList || []).slice(0, 2).filter(Boolean);
                if (classes.length) return `${tag}.${classes.map(cssEscape).join('.')}`;
                return nthPath(el);
              }
              let picked = null;
              for (const sel of candidates || []) {
                try { picked = document.querySelector(sel); } catch (_) {}
                if (picked) break;
              }
              if (!picked || !picked.tagName) return '';
              const tag = picked.tagName.toLowerCase();
              if (tag === 'option' && picked.parentElement) return `${stable(picked.parentElement)} option`;
              if (tag === 'select') return `${stable(picked)} option`;
              const cls = Array.prototype.slice.call(picked.classList || []).filter(Boolean)[0] || '';
              if (cls) {
                const same = `${tag}.${cssEscape(cls)}`;
                try { if (document.querySelectorAll(same).length >= 2) return same; } catch (_) {}
              }
              const parent = picked.parentElement;
              if (!parent) return stable(picked);
              const scoped = `${stable(parent)} > ${tag}`;
              try { if (document.querySelectorAll(scoped).length >= 2) return scoped; } catch (_) {}
              return stable(picked);
            }
            """,
            candidates,
        ) or "")

    def _evaluate_picker(self, page: Page, timeout_ms: int) -> dict | None:
        # Listeners are normally already installed by PICKER_INSTALL_SCRIPT via
        # add_init_script (before any page script ran). Re-evaluate defensively
        # (idempotent, guarded by window.__pickerInstalled) in case this frame's
        # document existed before the init script was registered.
        for frame in list(page.frames):
            try:
                frame.evaluate(PICKER_INSTALL_SCRIPT)
                frame.evaluate("() => { if (window.__pickerArm) window.__pickerArm(); }")
            except Exception:
                continue

        deadline = time.monotonic() + (timeout_ms / 1000)
        try:
            while time.monotonic() < deadline:
                for frame in list(page.frames):
                    try:
                        state = frame.evaluate(
                            "() => (window.__pickerDone ? {done: true, result: window.__pickerResult ?? null} : {done: false})"
                        )
                    except Exception:
                        continue
                    if state and state.get("done"):
                        return state.get("result")
                page.wait_for_timeout(100)
        finally:
            for frame in list(page.frames):
                try:
                    frame.evaluate(
                        "() => { if (typeof window.__pickerCancelPicker === 'function') window.__pickerCancelPicker(); }"
                    )
                except Exception:
                    pass
        raise RuntimeError("picker timed out")

    def preview_mapping(self, url: str, fields: list[dict]) -> dict:
        """Navigate to url and draw overlay boxes for each mapped field.

        Returns {"found": [key, ...], "missing": [key, ...], "values": {key: value}}.
        """
        page = self._ensure_page()
        _safe_goto(page, url)
        found_keys = []
        values = {}
        for field in fields:
            key = field.get("key")
            if not key:
                continue
            value = self._preview_field_value(page, field)
            if value:
                values[key] = value
                found_keys.append(key)
                continue
            selector = str(field.get("selector") or "").strip()
            if selector:
                try:
                    if page.query_selector(selector):
                        found_keys.append(key)
                except Exception:
                    pass
        page.evaluate(MAPPING_PREVIEW_SCRIPT, fields)
        missing = [f["key"] for f in fields if f["key"] not in found_keys]
        return {"found": list(found_keys), "missing": missing, "values": values}

    def _preview_field_value(self, page: Page, field: dict) -> str | None:
        selector = str(field.get("selector") or "").strip()
        transform = field.get("transform") or "strip"
        if selector:
            try:
                if field.get("multiple"):
                    elements = page.query_selector_all(selector)
                    reads = [self._read_preview_element(el, field) or "" for el in elements]
                    # 옵션값 미리보기에 품절 개수 표기 (option_values만; placeholder 제외).
                    def _soldout_suffix() -> str:
                        if field.get("key") != "option_values":
                            return ""
                        n = sum(1 for el, t in zip(elements, reads) if t and _sync_option_soldout(el, t))
                        return f" (품절 {n})" if n else ""
                    parser = field.get("option_text_parser")
                    if parser:
                        parsed = [parse_option_text(item, parser) for item in reads if item]
                        if field.get("key") == "option_prices":
                            prices = [
                                item.price_delta if item.price_delta is not None else item.supply_price
                                for item in parsed
                                if item.price_delta is not None or item.supply_price is not None
                            ]
                            if prices:
                                preview = ", ".join(str(item) for item in prices[:5])
                                return f"{len(prices)}개 · {preview}"[:100]
                        else:
                            # 병합 표시: 값 묶음 / 가격 묶음 (엑셀 2열 구조와 동일)
                            summary = format_option_group(parsed)
                            if summary:
                                return f"{summary}{_soldout_suffix()}"[:200]
                    values = [
                        _apply_preview_transform(clean_field_value(field.get("key"), item), transform)
                        for item in reads if item
                    ]
                    values = [item for item in values if item]
                    if values:
                        preview = ", ".join(item[:50] for item in values[:5])
                        return f"{len(values)}개 · {preview}{_soldout_suffix()}"[:100]
                else:
                    element = page.query_selector(selector)
                    if element:
                        raw = clean_field_value(field.get("key"), self._read_preview_element(element, field))
                        return _apply_preview_transform(raw, transform)
            except Exception:
                pass
        if field.get("fallback_from") == "url":
            value = extract_url_value(
                page.url,
                SimpleNamespace(url_param=field.get("url_param"), url_pattern=field.get("url_pattern")),
            )
            return _apply_preview_transform(value, transform)
        fallback = field.get("fallback")
        return _apply_preview_transform(str(fallback), transform) if fallback else None

    def _read_preview_element(self, element, field: dict) -> str | None:
        if field.get("html"):
            return element.inner_html()
        attribute = field.get("attribute")
        if attribute:
            value = element.get_attribute(attribute)
            fallback_attribute = field.get("fallback_attribute")
            return value or (element.get_attribute(fallback_attribute) if fallback_attribute else None)
        return element.inner_text()

    def close(self) -> None:
        """Close page, browser, playwright, and clean up the temp profile."""
        if self._page is not None:
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None

        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

        if self._temp_dir and self._temp_dir.exists():
            try:
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            except Exception:
                pass
            self._temp_dir = None

        self._logged_in = False
        self._login_url = None
        self._current_url = None
