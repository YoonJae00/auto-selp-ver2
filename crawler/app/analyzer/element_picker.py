from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

from app.analyzer.login_helper import perform_login as _perform_login_shared
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
    container_links: list[dict] = field(default_factory=list)


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
    elif field_path == "adapter.categories.navigation.menu_selector":
        result["observed_value"] = picked.text or picked.selector
    return result


PICKER_SCRIPT = r"""
() => new Promise((resolve) => {
  const safeAttrs = ['href', 'src', 'data-src', 'value', 'alt', 'title'];
  const sensitiveRe = /csrf|token|secret|key|password|session|auth/i;
  const oldOutline = new WeakMap();
  const tip = document.createElement('div');
  tip.id = '__picker-tip';
  tip.style.cssText = 'position:fixed;z-index:2147483646;padding:4px 8px;background:rgba(20,20,20,0.92);color:#fff;font:11px/1.3 monospace;border-radius:4px;pointer-events:none;display:none;max-width:320px;word-break:break-all';
  document.body.appendChild(tip);
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
    if (tip.parentNode) tip.parentNode.removeChild(tip);
    const ov = document.getElementById('__picker-overlay');
    if (ov && ov.parentNode) ov.parentNode.removeChild(ov);
  }
  function isOverlayEl(el) {
    return !!el && (el.id === '__picker-overlay' || (typeof el.closest === 'function' && el.closest('#__picker-overlay')));
  }
  function removeConfirm() {
    const existing = document.getElementById('__picker-confirm');
    if (existing && existing.parentNode) existing.parentNode.removeChild(existing);
  }
  function isPickerUi(el) {
    return !!el && typeof el.closest === 'function' && (el.closest('#__picker-overlay') || el.closest('#__picker-confirm'));
  }
  function over(e) {
    const el = e.target;
    if (isPickerUi(el) || !el || el.nodeType !== 1 || !el.tagName) return;
    if (!oldOutline.has(el)) oldOutline.set(el, el.style.outline || '');
    el.style.outline = '2px solid #2f80ed';
    const tag = el.tagName.toLowerCase();
    const cls = (el.classList && el.classList[0]) ? '.' + el.classList[0] : '';
    const id = el.id ? '#' + el.id : '';
    tip.textContent = tag + id + cls + ' — 클릭해서 지정';
    tip.style.left = Math.min(e.clientX + 12, window.innerWidth - 200) + 'px';
    tip.style.top = Math.max(e.clientY - 28, 32) + 'px';
    tip.style.display = 'block';
  }
  function out(e) {
    const el = e.target;
    if (isPickerUi(el)) return;
    if (el && oldOutline.has(el)) el.style.outline = oldOutline.get(el);
    tip.style.display = 'none';
  }
  function click(e) {
    const el = e.target;
    if (isPickerUi(el)) return;
    e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
    if (window.__pickerCancelled) { cleanup(); resolve(null); return; }
    // Clicking the instruction overlay (incl. the cancel button) cancels the picker.
    if (isOverlayEl(el)) { cleanup(); resolve(null); return; }
    // Ignore clicks on non-element targets (e.g., the document) — keep the picker alive.
    if (!el || el.nodeType !== 1 || !el.tagName) return;
    const cand = candidates(el);
    // Ignore clicks that yield no usable selector — keep the picker alive.
    if (!cand.length) return;
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
    const picked = {
      url: location.href,
      selectorCandidates: cand,
      matchCounts: counts,
      text: el.innerText || el.textContent || '',
      htmlPreview: el.innerHTML || '',
      attributeValues: attrs,
      tagName: el.tagName.toLowerCase(),
      elementId: el.id || '',
      classes: Array.from(el.classList || []).slice(0, 10),
    };
    removeConfirm();
    const box = document.createElement('div');
    box.id = '__picker-confirm';
    box.style.cssText = [
      'position:fixed','left:50%','top:72px','transform:translateX(-50%)','z-index:2147483647',
      'width:min(420px,calc(100vw - 32px))','padding:14px','border-radius:10px',
      'background:#111827','color:#fff','box-shadow:0 12px 32px rgba(0,0,0,0.35)',
      'font:13px/1.45 -apple-system,system-ui,sans-serif'
    ].join(';');
    const preview = (picked.text || picked.attributeValues.href || picked.attributeValues.src || cand[0] || '').trim().slice(0, 140);
    box.innerHTML = '<div style="font-weight:700;margin-bottom:6px">이 요소가 맞나요?</div>'
      + '<div style="opacity:.82;word-break:break-all;margin-bottom:12px"></div>'
      + '<div style="display:flex;gap:8px;justify-content:flex-end"></div>';
    box.children[1].textContent = preview || cand[0];
    const buttons = box.children[2];
    const no = document.createElement('button');
    no.textContent = 'No';
    no.style.cssText = 'padding:6px 14px;border:0;border-radius:7px;background:#374151;color:#fff;font-weight:700;cursor:pointer';
    no.onclick = (ev) => { ev.preventDefault(); ev.stopPropagation(); removeConfirm(); };
    const yes = document.createElement('button');
    yes.textContent = 'Yes';
    yes.style.cssText = 'padding:6px 14px;border:0;border-radius:7px;background:#2f80ed;color:#fff;font-weight:700;cursor:pointer';
    yes.onclick = (ev) => { ev.preventDefault(); ev.stopPropagation(); cleanup(); resolve(picked); };
    buttons.appendChild(no);
    buttons.appendChild(yes);
    document.body.appendChild(box);
  }
  window.__pickerCancelled = false;
  document.addEventListener('mouseover', over, true);
  document.addEventListener('mouseout', out, true);
  document.addEventListener('click', click, true);
})
"""


INSTRUCTION_OVERLAY_SCRIPT = r"""
([fieldLabel, fieldHint]) => {
  if (document.getElementById('__picker-overlay')) return;
  const bar = document.createElement('div');
  bar.id = '__picker-overlay';
  bar.style.cssText = [
    'position:fixed','top:0','left:0','right:0','z-index:2147483647',
    'display:flex','align-items:center','justify-content:space-between',
    'padding:10px 16px','font:13px/1.4 -apple-system,system-ui,sans-serif',
    'color:#fff','background:#2f80ed','box-shadow:0 2px 8px rgba(0,0,0,0.25)',
    'pointer-events:none'
  ].join(';');
  const left = document.createElement('span');
  left.textContent = '📋 「' + fieldLabel + '」 선택중 — ' + fieldHint;
  left.style.cssText = 'flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
  const btn = document.createElement('button');
  btn.textContent = '취소';
  btn.style.cssText = 'margin-left:12px;padding:4px 12px;border:0;border-radius:6px;background:rgba(255,255,255,0.25);color:#fff;font:600 13px/1 system-ui,sans-serif;cursor:pointer;pointer-events:auto';
  btn.onclick = () => { window.__pickerCancelled = true; };
  bar.appendChild(left);
  bar.appendChild(btn);
  document.body.appendChild(bar);
}
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


async def _perform_login(page, login_url: str, username: str, password: str, login_config: dict[str, str] | None = None) -> bool:
    """Shared login via the robust login_helper.  Preserved as a thin wrapper for callers."""
    return await _perform_login_shared(page, login_url, username, password, login_config=login_config)


async def pick_element(url: str, login_url: str | None = None, username: str | None = None, password: str | None = None, login_config: dict[str, str] | None = None, timeout_ms: int = 60_000) -> PickedElement:
    async with create_engine(headless=False) as engine:
        page = await engine.new_page()
        try:
            if login_url and username and password:
                await _perform_login(page, login_url, username, password, login_config)
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
