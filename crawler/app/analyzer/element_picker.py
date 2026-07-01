from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any



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
    elif field_path == "adapter.product.extra_image_urls":
        result["attribute"] = "src" if attrs.get("src") else "data-src" if attrs.get("data-src") else "src"
        result["multiple"] = True
        result["observed_value"] = attrs.get("src") or attrs.get("data-src") or result["observed_value"]
    elif field_path == "adapter.product.detail_content":
        result["attribute"] = "src" if attrs.get("src") else "data-src" if attrs.get("data-src") else "src"
        result["multiple"] = True
        result["html"] = False
        result["observed_value"] = attrs.get("src") or attrs.get("data-src") or picked.text
    elif field_path == "adapter.product.supply_price":
        result["transform"] = "extract_number"
    elif field_path == "adapter.options.groups.0.values_selector":
        result["observed_value"] = picked.text or picked.selector
    elif field_path == "adapter.options.option_price_delta":
        result["transform"] = "extract_number"
        result["multiple"] = True
        result["observed_value"] = picked.text or picked.selector
    elif field_path == "adapter.categories.all_products.url":
        result["attribute"] = "href"
        result["observed_value"] = attrs.get("href", "")
        result["selector"] = attrs.get("href", picked.selector)
    elif field_path == "adapter.categories.navigation.menu_selector":
        result["observed_value"] = picked.text or picked.selector
    return result




# Installed once per document via BrowserContext.add_init_script(), *before* any
# page script runs. Some shopping-mall pages register their own window-level
# capture-phase click/mousedown listeners (e.g. dropdown-close-on-outside-click)
# that call stopImmediatePropagation() and silently swallow the click before an
# on-demand-injected picker (running after the page loaded) ever sees it — hover
# still worked because those pages rarely intercept mouseover. Listeners are
# dormant (no-op) until armed, so this is safe to leave installed on every page.
# The selector-building code also avoids Array.from/Set: old malls ship broken
# polyfills for them that return [] and would leave every element unpickable.
PICKER_INSTALL_SCRIPT = r"""
(() => {
  if (window.__pickerInstalled) return;
  window.__pickerInstalled = true;
  window.__pickerArmed = false;
  window.__pickerDone = false;
  window.__pickerResult = null;
  window.__pickerCancelled = false;

  const safeAttrs = ['href', 'src', 'data-src', 'value', 'alt', 'title'];
  const sensitiveRe = /csrf|token|secret|key|password|session|auth/i;
  const oldOutline = new WeakMap();
  let tip = null;
  const cssEscape = (window.CSS && CSS.escape) ? CSS.escape : (s) => String(s).replace(/[^a-zA-Z0-9_-]/g, '\\$&');

  // Old malls (e.g. MakeShop) ship broken Array.from / Set polyfills that return
  // [] for iterables. We run in the page context, so never rely on those globals.
  function _toArr(x) {
    const a = [];
    if (!x) return a;
    if (typeof x.length === 'number') { for (let i = 0; i < x.length; i++) a.push(x[i]); return a; }
    if (typeof x.forEach === 'function') { x.forEach((v) => a.push(v)); return a; }
    return a;
  }
  function _uniq(arr) {
    const seen = {}; const o = [];
    for (let i = 0; i < arr.length; i++) { const s = arr[i]; if (s && !seen[s]) { seen[s] = 1; o.push(s); } }
    return o;
  }

  function ensureTip() {
    if (tip && tip.isConnected) return tip;
    tip = document.createElement('div');
    tip.id = '__picker-tip';
    tip.style.cssText = 'position:fixed;z-index:2147483646;padding:4px 8px;background:rgba(20,20,20,0.92);color:#fff;font:11px/1.3 monospace;border-radius:4px;pointer-events:none;display:none;max-width:320px;word-break:break-all';
    document.body.appendChild(tip);
    return tip;
  }
  function nthPath(el) {
    const parts = [];
    for (let node = el; node && node.nodeType === 1 && parts.length < 6; node = node.parentElement) {
      const tag = node.tagName.toLowerCase();
      const siblings = _toArr(node.parentElement ? node.parentElement.children : []).filter(x => x.tagName === node.tagName);
      const idx = siblings.indexOf(node) + 1;
      parts.unshift(`${tag}:nth-of-type(${idx})`);
    }
    return parts.join(' > ');
  }
  function candidates(el) {
    const tag = el.tagName.toLowerCase();
    const out = [];
    if (el.id) { out.push(`#${cssEscape(el.id)}`); out.push(`${tag}#${cssEscape(el.id)}`); }
    const classes = _toArr(el.classList).slice(0, 3).filter(Boolean);
    if (classes.length) out.push(`${tag}.${classes.map(cssEscape).join('.')}`);
    for (const attr of ['href', 'src', 'name', 'alt', 'title']) {
      const val = el.getAttribute(attr);
      if (val && val.length < 180 && !/password|token|secret|key/i.test(val)) out.push(`${tag}[${attr}="${val.replace(/"/g, '\\"')}"]`);
    }
    out.push(nthPath(el));
    return _uniq(out);
  }
  function removeConfirm() {
    const existing = document.getElementById('__picker-confirm');
    if (existing && existing.parentNode) existing.parentNode.removeChild(existing);
  }
  function isOverlayEl(el) {
    return !!el && (el.id === '__picker-overlay' || (typeof el.closest === 'function' && el.closest('#__picker-overlay')));
  }
  function isPickerUi(el) {
    return !!el && typeof el.closest === 'function' && (el.closest('#__picker-overlay') || el.closest('#__picker-confirm'));
  }
  function cleanupUi() {
    if (tip && tip.parentNode) tip.parentNode.removeChild(tip);
    tip = null;
    const ov = document.getElementById('__picker-overlay');
    if (ov && ov.parentNode) ov.parentNode.removeChild(ov);
    removeConfirm();
  }
  function finish(result) {
    if (!window.__pickerArmed) return;
    window.__pickerArmed = false;
    window.__pickerDone = true;
    window.__pickerResult = result;
    cleanupUi();
  }
  function cancelPicker() {
    if (!window.__pickerArmed) return;
    window.__pickerCancelled = true;
    finish(null);
  }
  function over(e) {
    if (!window.__pickerArmed) return;
    const el = e.target;
    if (isPickerUi(el) || !el || el.nodeType !== 1 || !el.tagName) return;
    if (!oldOutline.has(el)) oldOutline.set(el, el.style.outline || '');
    el.style.outline = '2px solid #2f80ed';
    const t = ensureTip();
    const tag = el.tagName.toLowerCase();
    const cls = (el.classList && el.classList[0]) ? '.' + el.classList[0] : '';
    const id = el.id ? '#' + el.id : '';
    t.textContent = tag + id + cls + ' — 클릭해서 지정';
    t.style.left = Math.min(e.clientX + 12, window.innerWidth - 200) + 'px';
    t.style.top = Math.max(e.clientY - 28, 32) + 'px';
    t.style.display = 'block';
  }
  function out(e) {
    if (!window.__pickerArmed) return;
    const el = e.target;
    if (isPickerUi(el)) return;
    if (el && oldOutline.has(el)) el.style.outline = oldOutline.get(el);
    if (tip) tip.style.display = 'none';
  }
  function click(e) {
    if (!window.__pickerArmed) return;
    const el = e.target;
    if (window.__pickerCancelled) { e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation(); cancelPicker(); return; }
    if (isOverlayEl(el)) { e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation(); cancelPicker(); return; }
    if (isPickerUi(el)) return;
    if (document.getElementById('__picker-confirm')) { e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation(); return; }
    e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
    if (!el || el.nodeType !== 1 || !el.tagName) return;
    const cand = candidates(el);
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
      classes: _toArr(el.classList).slice(0, 10),
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
    yes.onclick = (ev) => { ev.preventDefault(); ev.stopPropagation(); finish(picked); };
    buttons.appendChild(no);
    buttons.appendChild(yes);
    document.body.appendChild(box);
  }

  window.__pickerArm = function () {
    window.__pickerArmed = true;
    window.__pickerDone = false;
    window.__pickerResult = null;
    window.__pickerCancelled = false;
  };
  window.__pickerCancelPicker = cancelPicker;
  document.addEventListener('mouseover', over, true);
  document.addEventListener('mouseout', out, true);
  document.addEventListener('click', click, true);
  document.addEventListener('mousedown', click, true);
  window.addEventListener('click', click, true);
  window.addEventListener('mousedown', click, true);
})();
"""


MAPPING_PREVIEW_SCRIPT = r"""
(fields) => {
  document.querySelectorAll('[data-__preview]').forEach(el => el.remove());
  fields.forEach(({label, selector}) => {
    let el;
    try { el = document.querySelector(selector); } catch (_) { return; }
    if (!el) return;
    const r = el.getBoundingClientRect();
    const sx = window.scrollX, sy = window.scrollY;
    const box = document.createElement('div');
    box.setAttribute('data-__preview', '1');
    box.style.cssText = [
      'position:absolute','pointer-events:none','z-index:2147483645',
      'border:2px solid #2f80ed','border-radius:3px','background:rgba(47,128,237,0.08)',
      'left:' + (r.left + sx) + 'px','top:' + (r.top + sy) + 'px',
      'width:' + r.width + 'px','height:' + r.height + 'px'
    ].join(';');
    const tag = document.createElement('span');
    tag.style.cssText = [
      'position:absolute','top:-20px','left:0','background:#2f80ed','color:#fff',
      'font:bold 10px monospace','padding:2px 5px','border-radius:3px','white-space:nowrap'
    ].join(';');
    tag.textContent = label;
    box.appendChild(tag);
    document.body.appendChild(box);
  });
}
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
  btn.onclick = () => {
    window.__pickerCancelled = true;
    if (typeof window.__pickerCancelPicker === 'function') window.__pickerCancelPicker();
  };
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
