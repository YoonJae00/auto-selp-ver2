from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

from app.crawlers.engine import create_engine


SAFE_ATTRS = ("href", "src", "data-src", "value", "alt", "title")
MAX_TEXT = 300
MAX_HTML = 500
MAX_ATTR = 300


@dataclass
class PickedElement:
    url: str
    selector: str
    selector_candidates: list[str] = field(default_factory=list)
    text: str = ""
    html_preview: str = ""
    attribute_values: dict[str, str] = field(default_factory=dict)
    tag_name: str = ""
    element_id: str = ""
    classes: list[str] = field(default_factory=list)
    match_counts: dict[str, int] = field(default_factory=dict)


def sanitize_value(value: Any, limit: int = MAX_TEXT) -> str:
    text = "" if value is None else str(value)
    text = text.replace("```", " ").replace("`", " ")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


SENSITIVE_RE = re.compile(r"csrf|token|secret|key|password|session|auth", re.I)


def sanitize_html_preview(value: Any, limit: int = MAX_HTML) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"<\s*(script|style|input|textarea|select)\b.*?<\s*/\s*\1\s*>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<\s*(input|textarea|select)\b[^>]*>", " ", text, flags=re.I | re.S)
    text = re.sub(r"\b(value|content)\s*=\s*(['\"]).*?\2", " ", text, flags=re.I | re.S)
    text = re.sub(r"\b(csrf|token|secret|key|password|session|auth)[\w-]*\s*=\s*(['\"]).*?\2", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return sanitize_value(text, limit)


def _is_safe_value_attr(attrs: dict[str, Any]) -> bool:
    haystack = " ".join(str(attrs.get(k, "")) for k in ("name", "id", "type"))
    return not SENSITIVE_RE.search(haystack) and str(attrs.get("type", "")).lower() not in {"password", "hidden"}


def sanitize_attrs(attrs: dict[str, Any] | None) -> dict[str, str]:
    safe: dict[str, str] = {}
    source = attrs or {}
    for key in SAFE_ATTRS:
        if key == "value" and not _is_safe_value_attr(source):
            continue
        value = source.get(key)
        cleaned = sanitize_value(value, MAX_ATTR)
        if cleaned and not SENSITIVE_RE.search(cleaned):
            safe[key] = cleaned
    return safe


def choose_best_selector(candidates: list[str], match_counts: dict[str, int]) -> str:
    for selector in candidates:
        count = match_counts.get(selector)
        if count == 1:
            return selector
    for selector in candidates:
        count = match_counts.get(selector, 9999)
        if 0 < count <= 5:
            return selector
    return candidates[0] if candidates else ""


def suggest_defaults_for_field(field_path: str, picked: PickedElement) -> dict[str, Any]:
    attrs = picked.attribute_values
    result: dict[str, Any] = {"selector": picked.selector, "observed_value": picked.text or attrs.get("alt") or attrs.get("title") or ""}
    if field_path == "adapter.listing.product_link":
        result["attribute"] = "href"
        result["observed_value"] = attrs.get("href") or result["observed_value"]
    elif field_path == "adapter.product.main_image_url":
        result["attribute"] = "src" if attrs.get("src") else "data-src" if attrs.get("data-src") else "src"
        result["observed_value"] = attrs.get("src") or attrs.get("data-src") or result["observed_value"]
    elif field_path == "adapter.product.detail_content":
        result["html"] = True
        result["observed_value"] = picked.text
    elif field_path == "adapter.product.supply_price":
        result["transform"] = "extract_number"
    elif field_path == "adapter.categories.all_products.url":
        result["attribute"] = "href"
        result["observed_value"] = attrs.get("href", "")
        result["selector"] = attrs.get("href", picked.selector)
    return result


PICKER_SCRIPT = r"""
() => new Promise((resolve) => {
  const safeAttrs = ['href', 'src', 'data-src', 'value', 'alt', 'title'];
  const sensitiveRe = /csrf|token|secret|key|password|session|auth/i;
  const oldOutline = new WeakMap();
  const cssEscape = (window.CSS && CSS.escape) ? CSS.escape : (s) => String(s).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
  function nthPath(el) {
    const parts = [];
    for (let node = el; node && node.nodeType === 1 && parts.length < 6; node = node.parentElement) {
      const tag = node.tagName.toLowerCase();
      const siblings = Array.from(node.parentElement ? node.parentElement.children : []).filter(x => x.tagName === node.tagName);
      const idx = siblings.indexOf(node) + 1;
      parts.unshift(`${tag}:nth-of-type(${idx})`);
    }
    return parts.join(' > ');
  }
  function candidates(el) {
    const tag = el.tagName.toLowerCase();
    const out = [];
    if (el.id) { out.push(`#${cssEscape(el.id)}`); out.push(`${tag}#${cssEscape(el.id)}`); }
    const classes = Array.from(el.classList || []).slice(0, 3).filter(Boolean);
    if (classes.length) out.push(`${tag}.${classes.map(cssEscape).join('.')}`);
    for (const attr of ['href', 'src', 'name', 'alt', 'title']) {
      const val = el.getAttribute(attr);
      if (val && val.length < 180 && !/password|token|secret|key/i.test(val)) out.push(`${tag}[${attr}="${val.replace(/"/g, '\\"')}"]`);
    }
    out.push(nthPath(el));
    return Array.from(new Set(out)).filter(Boolean);
  }
  function cleanup() {
    document.removeEventListener('mouseover', over, true);
    document.removeEventListener('mouseout', out, true);
    document.removeEventListener('click', click, true);
  }
  function over(e) { if (!oldOutline.has(e.target)) oldOutline.set(e.target, e.target.style.outline || ''); e.target.style.outline = '3px solid #2f80ed'; }
  function out(e) { if (oldOutline.has(e.target)) e.target.style.outline = oldOutline.get(e.target); }
  function click(e) {
    e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation(); cleanup();
    const el = e.target;
    const cand = candidates(el);
    const counts = {};
    for (const sel of cand) { try { counts[sel] = document.querySelectorAll(sel).length; } catch (_) { counts[sel] = 9999; } }
    const attrs = {};
    const attrHaystack = `${el.getAttribute('name') || ''} ${el.id || ''} ${el.getAttribute('type') || ''}`;
    const safeValue = !sensitiveRe.test(attrHaystack) && !['password', 'hidden'].includes((el.getAttribute('type') || '').toLowerCase());
    for (const attr of safeAttrs) {
      if (attr === 'value' && !safeValue) continue;
      const v = el.getAttribute(attr);
      if (v && !sensitiveRe.test(v)) attrs[attr] = v;
    }
    attrs.name = el.getAttribute('name') || '';
    attrs.id = el.id || '';
    attrs.type = el.getAttribute('type') || '';
    resolve({
      url: location.href,
      selectorCandidates: cand,
      matchCounts: counts,
      text: el.innerText || el.textContent || '',
      htmlPreview: el.innerHTML || '',
      attributeValues: attrs,
      tagName: el.tagName.toLowerCase(),
      elementId: el.id || '',
      classes: Array.from(el.classList || []).slice(0, 10),
    });
  }
  document.addEventListener('mouseover', over, true);
  document.addEventListener('mouseout', out, true);
  document.addEventListener('click', click, true);
})
"""


ID_SELECTOR_CANDIDATES = [
    "input[name='id']",
    "input[name='user']",
    "input[name='userid']",
    "input[name='username']",
    "input[name='loginId']",
    "input[name='memberId']",
    "input[type='text']",
    "input[type='email']",
]

PASSWORD_SELECTOR_CANDIDATES = [
    "input[name='passwd']",
    "input[name='password']",
    "input[name='pwd']",
    "input[name='userpw']",
    "input[type='password']",
]

SUBMIT_SELECTOR_CANDIDATES = [
    "input[type='image'][src*='login']",
    "img[src*='login']",
    "input[type='image'][src*='LogIn']",
    "img[src*='LogIn']",
    "button[type='submit']",
    "input[type='submit']",
    "input[type='image']",
    "a[href*='login']",
]

DEFAULT_LOGIN_CONFIG: dict[str, str] = {}


def resolve_login_selectors(login_config: dict[str, str] | None) -> dict[str, Any]:
    """Return concrete selector choices, preferring config-provided over defaults."""
    cfg = login_config or {}
    return {
        "id_selector": cfg.get("id_selector") or "",
        "id_candidates": (cfg.get("id_selector") and [cfg["id_selector"]]) or list(ID_SELECTOR_CANDIDATES),
        "password_selector": cfg.get("password_selector") or "",
        "password_candidates": (cfg.get("password_selector") and [cfg["password_selector"]]) or list(PASSWORD_SELECTOR_CANDIDATES),
        "submit_selector": cfg.get("submit_selector") or "",
        "submit_candidates": (cfg.get("submit_selector") and [cfg["submit_selector"]]) or list(SUBMIT_SELECTOR_CANDIDATES),
        "success_indicator": cfg.get("success_indicator") or "",
    }


async def _perform_login(page, login_url: str, username: str, password: str, selectors: dict[str, str]) -> None:
    await page.goto(login_url, wait_until="domcontentloaded", timeout=15000)
    await page.wait_for_timeout(1000)

    # Fill username
    for sel in selectors["id_candidates"]:
        try:
            el = await page.wait_for_selector(sel, state="visible", timeout=5000)
            if el:
                await el.fill(username)
                break
        except Exception:
            continue

    # Fill password
    for sel in selectors["password_candidates"]:
        try:
            el = await page.wait_for_selector(sel, state="visible", timeout=5000)
            if el:
                await el.fill(password)
                break
        except Exception:
            continue

    # Click submit
    submitted = False
    for sel in selectors["submit_candidates"]:
        try:
            btn = await page.wait_for_selector(sel, state="visible", timeout=5000)
            if btn:
                await btn.click()
                submitted = True
                break
        except Exception:
            continue

    if not submitted:
        return

    try:
        await page.wait_for_load_state("domcontentloaded", timeout=10000)
    except Exception:
        await page.wait_for_timeout(3000)

    # Verify login (optional)
    if selectors["success_indicator"]:
        try:
            await page.wait_for_selector(selectors["success_indicator"], state="visible", timeout=5000)
        except Exception:
            pass


async def pick_element(url: str, login_url: str | None = None, username: str | None = None, password: str | None = None, login_config: dict[str, str] | None = None, timeout_ms: int = 60_000) -> PickedElement:
    async with create_engine(headless=False) as engine:
        page = await engine.new_page()
        try:
            if login_url and username and password:
                selectors = resolve_login_selectors(login_config)
                await _perform_login(page, login_url, username, password, selectors)
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(1000)
            raw = await asyncio.wait_for(page.evaluate(PICKER_SCRIPT), timeout=timeout_ms / 1000)
            candidates = [sanitize_value(v, 220) for v in raw.get("selectorCandidates", []) if sanitize_value(v, 220)]
            counts = {str(k): int(v) for k, v in (raw.get("matchCounts") or {}).items() if str(k) in candidates}
            return PickedElement(
                url=sanitize_value(raw.get("url"), 300),
                selector=choose_best_selector(candidates, counts),
                selector_candidates=candidates,
                text=sanitize_value(raw.get("text"), MAX_TEXT),
                html_preview=sanitize_html_preview(raw.get("htmlPreview"), MAX_HTML),
                attribute_values=sanitize_attrs(raw.get("attributeValues")),
                tag_name=sanitize_value(raw.get("tagName"), 40),
                element_id=sanitize_value(raw.get("elementId"), 120),
                classes=[sanitize_value(c, 80) for c in raw.get("classes", [])[:10]],
                match_counts=counts,
            )
        finally:
            await page.close()
