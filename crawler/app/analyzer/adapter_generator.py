from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import yaml
from bs4 import BeautifulSoup
from pydantic import ValidationError
from soupsieve import SelectorSyntaxError

from app.analyzer.adapter_schema import FieldExtractor

from app.analyzer.adapter_schema import Adapter, clean_field_value
from app.analyzer.llm_client import get_llm_client, QuotaExceededError
from app.analyzer.mapping_hints import MappingHint, PRODUCT_DEFAULTS, apply_locked_hints_to_yaml_dict, format_mapping_hints_for_prompt
from app.analyzer.platform_hints import platform_hint_block
from app.analyzer.site_probe import ProbeResult


SYSTEM_PROMPT = """당신은 웹 스크래핑 전문가입니다. 도매처 사이트 DOM을 분석하여
Auto-Selp 표준 상품 스키마로 매핑하는 YAML 어댑터를 생성하세요.

출력은 반드시 다음 YAML 스키마를 따르며, 다른 설명은 출력하지 마세요.

```yaml
adapter:
  name: string
  base_url: string
  encoding: utf-8 | euc-kr
  browser:
    channel: msedge | chrome | chromium
    wait_until: networkidle | domcontentloaded
    navigation_timeout: integer
  login:
    required: boolean
    login_url: string
    fields:
      id: CSS_selector
      password: CSS_selector
    submit: CSS_selector
    success_indicator: CSS_selector
  categories:
    mode: all_products | tree | hybrid
    all_products:
      available: boolean
      url: string
    navigation:
      menu_selector: CSS_selector
      link_selector: "a"
      name_source: text | attribute
      url_attribute: href
      max_depth: integer (1-3)
      submenu:
        selector: CSS_selector
        expand_trigger: hover | click | static
    url_template: "URL with {category_id} and {page}"
    store_category_path: boolean
  listing:
    pagination:
      type: page_number | next_button | infinite_scroll
      page_param: string
      start: integer
      max_pages: integer
      stop_indicator: CSS_selector
    product_link:
      selector: CSS_selector
      attribute: href
      base: relative | absolute
  product:
    supplier_product_code:
      selector: CSS_selector
    raw_product_name:
      selector: CSS_selector
    supply_price:
      selector: CSS_selector
      transform: extract_number
    origin:
      selector: CSS_selector
      fallback: "국산"
    main_image_url:
      selector: CSS_selector
      attribute: src
      fallback_attribute: data-src
  options:
    detection: none
    dependent_options:
      enabled: boolean
      level_1_group: string
      level_2_group: string
      level_2_trigger: click | select
      level_2_values_selector: CSS_selector
```

중요 규칙:
1. 위 DOM에서 각 필드에 대한 CSS 선택자를 추출하세요.
2. 대표 이미지는 src 또는 data-src 속성을 사용하고 jpg/jpeg/png/webp 형식만 대상으로 하세요 (lazy loading 대응).
   판매 상태(supplier_status), 상세 이미지(detail_content), 추가 이미지(extra_image_urls), 옵션값(groups), 옵션가격(option_price_delta)은 자동 생성하지 마세요.
   이 필드들과 옵션 텍스트 파서(option_text_parser)는 사용자가 3단계 매핑 화면에서 직접 선택/분석합니다.
3. 원산지(origin)는 "대한민국", "중국", "국산" 같은 값 텍스트만 추출하세요. 판매가/배송비/상품코드가 함께 나오는 상품정보 전체 컨테이너를 선택하지 마세요.
4. 선택자를 찾을 수 없는 필드는 해당 필드를 YAML에서 완전히 생략하세요. 빈 문자열("")을 선택자로 사용하지 마세요.
5. YAML만 출력하세요. 코드 블록이나 설명 없이 바로 YAML.
"""


# 전체 자동화 모드용 프롬프트 — SYSTEM_PROMPT의 "manual-only 필드는 생성하지 마세요" 지시만
# 치환해 재사용한다(복붙 금지 원칙). manual 지시 블록이 사라지면 replace가 no-op이 되므로
# 아래 assert로 드리프트를 즉시 잡는다.
_MANUAL_DIRECTIVE_BLOCK = (
    "   판매 상태(supplier_status), 상세 이미지(detail_content), 추가 이미지(extra_image_urls), 옵션값(groups), 옵션가격(option_price_delta)은 자동 생성하지 마세요.\n"
    "   이 필드들과 옵션 텍스트 파서(option_text_parser)는 사용자가 3단계 매핑 화면에서 직접 선택/분석합니다."
)
_AUTO_DIRECTIVE_BLOCK = (
    # supplier_status는 요청하지 않는다 — 라이브 검증 불가 필드라 LLM 추측만으로 받지 않고,
    # 오케스트레이터의 판매중/품절 실측 비교 경로로만 설정한다.
    "   아래 필드의 후보 CSS 선택자도 함께 생성하세요 (전체 자동화 모드, 확실하지 않으면 생략):\n"
    "   - product.detail_content: 상세 설명 이미지 컨테이너의 img (attribute: src, multiple: true)\n"
    "   - product.extra_image_urls: 상품 갤러리 추가 이미지 img (attribute: src, multiple: true)\n"
    "   - options.groups: [{name: 옵션, values_selector: CSS선택자}] 옵션값 요소\n"
    "   - options.option_price_delta: 옵션 추가금액 요소 (transform: extract_number)\n"
    "   후보를 찾을 수 없는 필드는 생략하세요. 이 후보들은 라이브 검증 후 자동 보정됩니다."
)
AUTO_SYSTEM_PROMPT = SYSTEM_PROMPT.replace(_MANUAL_DIRECTIVE_BLOCK, _AUTO_DIRECTIVE_BLOCK)
assert AUTO_SYSTEM_PROMPT != SYSTEM_PROMPT, "SYSTEM_PROMPT의 manual 지시 블록이 바뀌었습니다 — _MANUAL_DIRECTIVE_BLOCK 갱신 필요"


@dataclass
class GenerationResult:
    yaml_text: str
    adapter: Adapter
    provider_used: str
    retries: int
    verification: dict = field(default_factory=dict)


def _extract_yaml(raw: str) -> str:
    match = re.search(r"```yaml\s*(.*?)\s*```", raw, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r"```\s*(.*?)\s*```", raw, re.DOTALL)
    if match:
        return match.group(1).strip()
    return raw.strip()


def _validate_yaml(yaml_text: str | dict) -> Adapter:
    raw = yaml.safe_load(yaml_text) if isinstance(yaml_text, str) else yaml_text
    _strip_empty_selectors(raw)
    return Adapter.model_validate(raw)


# 의사요소(::before/::after 등)는 추출에 무의미하고 soupsieve는 이를 NotImplementedError로,
# Playwright query_selector는 런타임 에러로 던진다 → 소스에서 제거하는 게 근본 처리.
# 콜론 1개 Playwright 의사클래스(:has-text() 등)는 :: 가 아니라 안전.
_PSEUDO_ELEMENT_RE = re.compile(r"::[\w-]+(?:\([^)]*\))?")


def _strip_pseudo_elements(selector: str | None) -> str:
    if not selector:
        return selector or ""
    return _PSEUDO_ELEMENT_RE.sub("", str(selector)).strip()


def _sanitize_pseudo_elements(node: Any) -> None:
    """YAML dict 전체를 훑어 selector/values_selector 문자열에서 의사요소 접미 제거."""
    if isinstance(node, dict):
        for key, val in node.items():
            if key in ("selector", "values_selector") and isinstance(val, str):
                node[key] = _strip_pseudo_elements(val)
            else:
                _sanitize_pseudo_elements(val)
    elif isinstance(node, list):
        for item in node:
            _sanitize_pseudo_elements(item)


def _finalize_generated_yaml(
    raw_response: str,
    mapping_hints: list[MappingHint] | None = None,
    strip_manual: bool = True,
) -> tuple[str, Adapter]:
    raw = yaml.safe_load(_extract_yaml(raw_response))
    _strip_empty_selectors(raw)
    _sanitize_pseudo_elements(raw)  # LLM이 만든 ::before 등 의사요소 선택자 제거 (검증 크래시 방지)
    if strip_manual:  # 전체 자동화 모드(strip_manual=False)는 LLM이 만든 manual-only 후보를 남긴다
        _strip_auto_manual_fields(raw, mapping_hints)
    Adapter.model_validate(raw)
    apply_locked_hints_to_yaml_dict(raw, mapping_hints)
    _strip_empty_selectors(raw)
    adapter = Adapter.model_validate(raw)
    dumped = yaml.safe_dump(adapter.model_dump(mode="json", exclude_none=True), allow_unicode=True, sort_keys=False)
    return dumped, adapter


MANUAL_ONLY_PRODUCT_FIELDS = {"supplier_status", "detail_content", "extra_image_urls"}
MANUAL_ONLY_OPTION_FIELDS = {"groups", "option_price_delta", "option_text_parser"}


def _strip_auto_manual_fields(data: dict | None, mapping_hints: list[MappingHint] | None = None) -> None:
    if not isinstance(data, dict):
        return
    locked_paths = {hint.field_path for hint in mapping_hints or [] if hint.locked}
    adapter = data.get("adapter")
    if not isinstance(adapter, dict):
        return
    product = adapter.get("product")
    if isinstance(product, dict):
        for field in MANUAL_ONLY_PRODUCT_FIELDS:
            if f"adapter.product.{field}" not in locked_paths:
                product.pop(field, None)
    options = adapter.get("options")
    if isinstance(options, dict):
        if "adapter.options.groups.0.values_selector" not in locked_paths:
            options.pop("groups", None)
        if "adapter.options.option_price_delta" not in locked_paths:
            options.pop("option_price_delta", None)


def _strip_empty_selectors(data: dict | None) -> None:
    """Remove FieldExtractor entries with empty/None selectors so validation doesn't fail."""
    if not isinstance(data, dict):
        return
    adapter_data = data.get("adapter")
    if not isinstance(adapter_data, dict):
        return

    product = adapter_data.get("product")
    if isinstance(product, dict):
        for key in list(product.keys()):
            val = product[key]
            if isinstance(val, dict) and "selector" in val:
                sel = val["selector"]
                has_useful_fallback = bool(val.get("fallback")) or val.get("fallback_from") not in (None, "", "none")
                if (sel is None or not str(sel).strip()) and not has_useful_fallback:
                    product[key] = None

    # Handle categories.navigation.menu_selector
    categories = adapter_data.get("categories")
    if isinstance(categories, dict):
        nav = categories.get("navigation")
        if isinstance(nav, dict):
            ms = nav.get("menu_selector")
            if ms is None or (isinstance(ms, str) and not ms.strip()):
                categories["navigation"] = None

    options = adapter_data.get("options")
    if isinstance(options, dict):
        groups = options.get("groups")
        if isinstance(groups, list):
            for group in groups:
                if isinstance(group, dict) and "values_selector" in group:
                    vs = group["values_selector"]
                    if vs is None or (isinstance(vs, str) and not str(vs).strip()):
                        group["values_selector"] = ""

        dep = options.get("dependent_options")
        if isinstance(dep, dict):
            for key in ("level_2_values_selector", "level_2_load_indicator"):
                if key in dep and dep[key] is not None and not str(dep[key]).strip():
                    dep[key] = None

        for opt_key in ("option_image_url", "option_price_delta", "option_stock_quantity"):
            val = options.get(opt_key)
            if isinstance(val, dict) and "selector" in val:
                sel = val["selector"]
                if sel is None or not str(sel).strip():
                    options[opt_key] = None


def _build_user_prompt(probe_result: ProbeResult, supplier_name: str, mapping_hints: list[MappingHint] | None = None) -> str:
    parts: list[str] = [
        f"## 도매처 정보",
        f"- 이름: {supplier_name}",
        f"- 메인 URL: {probe_result.main_url}",
        f"- 최종 URL: {probe_result.final_url}",
        f"- 인코딩: {probe_result.encoding}",
        f"- 로그인 필요: {probe_result.needs_login}",
        f"- 전체상품 메뉴: {'있음' if probe_result.has_all_products else '없음'}",
    ]

    platform = getattr(probe_result, "platform", None)
    if platform:
        parts.append(f"- 감지된 쇼핑몰 솔루션: {platform}")
        hint_block = platform_hint_block(platform)
        if hint_block:
            parts.append(f"\n## 플랫폼 표준 선택자 힌트 ({platform})\n{hint_block}")

    # Add status indicators if available
    if hasattr(probe_result, 'status_indicators') and probe_result.status_indicators:
        si = probe_result.status_indicators
        parts.append(f"- 판매 상태 지표: cart_button={'있음' if si.get('has_cart_button') else '없음'}, "
                     f"soldout_image={'있음' if si.get('has_soldout_image') else '없음'}, "
                     f"maxq={si.get('maxq_value', '?')}, "
                     f"explicit_status={'있음' if si.get('has_explicit_status') else '없음'}")

    # Add total product count if available
    if hasattr(probe_result, 'total_product_count') and probe_result.total_product_count:
        parts.append(f"- 총 상품 수: {probe_result.total_product_count}개")
    if hasattr(probe_result, 'total_pages') and probe_result.total_pages:
        parts.append(f"- 총 페이지 수: {probe_result.total_pages}페이지")

    if probe_result.needs_login and probe_result.login_form_html:
        parts.append(f"\n## 로그인 폼 DOM\n{probe_result.login_form_html}")

    if probe_result.category_menu_html:
        parts.append(f"\n## 카테고리 네비게이션 DOM (축소됨)\n{probe_result.category_menu_html}")

    if probe_result.listing_html:
        listing_trimmed = probe_result.listing_html[:12000]
        parts.append(f"\n## 상품 목록 페이지 DOM (축소됨)\n{listing_trimmed}")

    if probe_result.detail_html:
        detail_trimmed = probe_result.detail_html[:12000]
        parts.append(f"\n## 상품 상세 페이지 DOM (축소됨)\n{detail_trimmed}")

    structured = getattr(probe_result, "structured_data", None)
    if structured:
        sd_lines = "\n".join(f"- {k}: {v}" for k, v in structured.items())
        parts.append(
            "\n## 구조화 데이터 (상세 페이지)\n"
            f"{sd_lines}\n"
            "위 값이 실제 상품과 일치하면, main_image_url은 selector \"meta[property='og:image']\" + "
            "attribute: content 를 우선 고려하세요 (런타임이 attribute 추출을 지원하므로 meta 선택자가 동작합니다). "
            "상품명·가격도 meta/JSON-LD 값과 대조해 정확한 선택자를 고르세요."
        )

    if probe_result.sample_links:
        parts.append(f"\n## 샘플 상품 링크\n" + "\n".join(f"- {link}" for link in probe_result.sample_links))

    if probe_result.ajax_requests:
        parts.append(f"\n## AJAX 요청 패턴 (옵션 동적 로딩 단서)\n" + "\n".join(
            f"- {req['method']} {req['url']} ({req['resource_type']})" for req in probe_result.ajax_requests
        ))

    hints_text = format_mapping_hints_for_prompt(mapping_hints)
    if hints_text:
        parts.append("\n" + hints_text)

    # Explicitly highlight user-confirmed all-products URL
    if mapping_hints:
        for hint in mapping_hints:
            if hint.field_path == "adapter.categories.all_products.url" and hint.locked:
                parts.append(f"\n## 사용자가 확인한 전체상품 페이지 URL\n- {hint.chosen_selector}")
                parts.append("위 URL을 adapter.categories.all_products.url 로 사용하세요.")

    return "\n".join(parts)


# Playwright 전용 의사클래스 — BeautifulSoup(soupsieve)가 파싱 못 하므로 검증 스킵.
_PLAYWRIGHT_PSEUDO = (":has-text(", ":text(", ":visible")
# 이미지 lazy 로딩 속성 — 런타임 _read_image_attribute와 동일 우선순위.
_IMAGE_ATTRS = ("data-src", "data-original", "data-lazy", "data-echo")


def _verify_number(text: str | None) -> int | None:
    """extract_number transform 재현 — 검증용 오프라인 숫자 파싱."""
    if not text:
        return None
    m = re.search(r"-?\d[\d,]*", text)
    if not m:
        return None
    try:
        return int(m.group().replace(",", ""))
    except ValueError:
        return None


def _extract_field_value(element, extractor: FieldExtractor, field_name: str = "") -> Any:
    """soup 요소에서 extractor(attribute/transform)를 반영해 값 추출. 없으면 None."""
    attr = extractor.attribute
    value: str | None = None
    if attr:
        if attr in ("src", "data-src"):
            candidates = [attr, extractor.fallback_attribute, *_IMAGE_ATTRS]
            for a in candidates:
                if not a:
                    continue
                v = element.get(a)
                if v and str(v).strip():
                    value = str(v).strip()
                    break
        else:
            v = element.get(attr)
            if (not v or not str(v).strip()) and extractor.fallback_attribute:
                v = element.get(extractor.fallback_attribute)
            value = str(v).strip() if v and str(v).strip() else None
    else:
        text = element.get_text(strip=True)
        value = text or None

    if value is None:
        return None
    value = clean_field_value(field_name, value)  # 라벨 오염 정리를 transform 전에 적용
    if value is None:
        return None
    if extractor.transform == "extract_number":
        return _verify_number(value)  # 숫자 파싱 실패 시 None → 실패로 처리
    return value


def verify_adapter_against_probe(adapter: Adapter, probe_result: ProbeResult) -> dict[str, Any]:
    """생성된 어댑터 선택자가 축소 DOM에서 실제로 값을 뽑는지 오프라인 검증.

    Playwright 전용 의사클래스나 fallback_from!="none" 필드, 파싱 불가 선택자는
    '검증 불가'로 건너뛴다(실패 아님). 반환:
      {"failed_fields": [...], "values": {field: value}, "product_link_count": n}
    """
    detail_html = getattr(probe_result, "detail_html", "") or ""
    listing_html = getattr(probe_result, "listing_html", "") or ""
    failed: list[str] = []
    values: dict[str, Any] = {}

    detail_soup = BeautifulSoup(detail_html, "html.parser") if detail_html else None
    product = adapter.adapter.product
    if detail_soup is not None:
        for name in REPAIRABLE_PRODUCT_FIELDS:
            extractor = getattr(product, name, None)
            if extractor is None or not (extractor.selector or "").strip():
                continue  # 선택자 미설정 → 검증 대상 아님
            if extractor.fallback_from not in (None, "", "none"):
                continue  # 자동 판정 필드 → 검증 불가
            selector = extractor.selector.strip()
            if any(p in selector for p in _PLAYWRIGHT_PSEUDO):
                continue  # Playwright 전용 → 검증 불가
            try:
                matches = detail_soup.select(selector)
            except (SelectorSyntaxError, NotImplementedError):  # 의사요소(::before 등)는 NotImplementedError
                continue  # 파싱 불가 → 검증 불가
            value = _extract_field_value(matches[0], extractor, name) if matches else None
            if value is None or (isinstance(value, str) and not value.strip()):
                failed.append(name)
            else:
                values[name] = value

    # listing product_link — 매치 개수만 확인(≥1이면 ok). reduce가 반복 요소를 압축하므로
    # 개수 기대치를 높이지 않는다.
    product_link_count = 0
    link_cfg = adapter.adapter.listing.product_link
    link_selector = (link_cfg.selector or "").strip()
    if listing_html and link_selector and not any(p in link_selector for p in _PLAYWRIGHT_PSEUDO):
        try:
            listing_soup = BeautifulSoup(listing_html, "html.parser")
            product_link_count = len(listing_soup.select(link_selector))
            if product_link_count == 0:
                failed.append("product_link")
        except (SelectorSyntaxError, NotImplementedError):  # 의사요소(::before 등)는 NotImplementedError
            pass  # 검증 불가

    return {"failed_fields": failed, "values": values, "product_link_count": product_link_count}


async def generate_adapter_yaml(
    probe_result: ProbeResult,
    supplier_name: str,
    llm_provider: str = "gemini",
    max_retries: int = 2,
    auto_fallback: bool = True,
    on_progress: Callable[[str], None] | None = None,
    mapping_hints: list[MappingHint] | None = None,
    include_manual_fields: bool = False,
) -> GenerationResult:
    user_prompt = _build_user_prompt(probe_result, supplier_name, mapping_hints)
    # 전체 자동화 모드: manual-only 필드까지 후보 선택자를 받도록 프롬프트/스트립을 전환.
    system_prompt = AUTO_SYSTEM_PROMPT if include_manual_fields else SYSTEM_PROMPT

    def _log(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    def _build_prompt(err: str = "") -> str:
        if err:
            return f"{user_prompt}\n\n## 이전 오류\n{err}\n\n위 오류를 수정하여 다시 생성하세요."
        return user_prompt

    # 잠금 힌트가 걸린 필드는 사용자 확정 선택자라 축소 DOM에서 안 잡혀도 정상 → 검증/수리 제외.
    locked_fields = {
        h.field_path.rsplit(".", 1)[-1]
        for h in (mapping_hints or [])
        if h.locked
    }

    async def _succeed(raw_response: str, used_provider: str, retries: int) -> GenerationResult:
        """finalize → 오프라인 검증 → 실패 시 1회 자동 수리 → 개선됐을 때만 수리본 채택."""
        yaml_text, adapter = _finalize_generated_yaml(raw_response, mapping_hints, strip_manual=not include_manual_fields)
        _log(f"Generation succeeded with {used_provider}.")

        verification = verify_adapter_against_probe(adapter, probe_result)
        failed = [f for f in verification["failed_fields"] if f not in locked_fields]
        repairable = [f for f in failed if f in REPAIRABLE_PRODUCT_FIELDS]
        detail = getattr(probe_result, "detail_html", "") or ""
        listing = getattr(probe_result, "listing_html", "") or ""

        if repairable and (detail or listing):
            _log(f"검증 실패 필드 {len(failed)}개 — 자동 수리 시도...")
            # 수리는 보강일 뿐 — 수리 중 오류(쿼터 등)로 이미 성공한 생성본을 버리지 않는다.
            try:
                repaired_yaml = await repair_adapter_fields(
                    yaml_text, repairable, probe_result,
                    llm_provider=used_provider, auto_fallback=auto_fallback, on_progress=on_progress,
                )
            except Exception as exc:
                _log(f"자동 수리 실패, 생성본 유지: {exc}")
                repaired_yaml = yaml_text
            if repaired_yaml != yaml_text:
                try:
                    new_adapter = _validate_yaml(repaired_yaml)
                except (ValidationError, yaml.YAMLError):
                    new_adapter = None
                if new_adapter is not None:
                    new_verification = verify_adapter_against_probe(new_adapter, probe_result)
                    new_failed = [f for f in new_verification["failed_fields"] if f not in locked_fields]
                    if len(new_failed) < len(failed):
                        _log(f"자동 수리로 실패 필드 {len(failed)}→{len(new_failed)}개 감소, 수리본 채택.")
                        yaml_text, adapter, verification, failed = (
                            repaired_yaml, new_adapter, new_verification, new_failed,
                        )
        verification = {**verification, "failed_fields": failed}
        return GenerationResult(
            yaml_text=yaml_text,
            adapter=adapter,
            provider_used=used_provider,
            retries=retries,
            verification=verification,
        )

    provider = llm_provider
    fallback_provider = "openai" if provider == "gemini" else "gemini"
    last_error: str = ""
    used_fallback = False

    _log(f"Generating adapter for {supplier_name} with {provider}...")

    # Try primary provider with retries
    for attempt in range(max_retries):
        client = get_llm_client(provider)
        try:
            raw_response = await client.generate(
                system_prompt,
                _build_prompt(last_error if attempt > 0 else ""),
            )
        except QuotaExceededError:
            if not auto_fallback or used_fallback:
                raise
            _log(
                f"{provider} 할당량 초과, "
                f"{'openai' if provider == 'gemini' else 'gemini'}로 전환합니다..."
            )
            provider = "openai" if provider == "gemini" else "gemini"
            used_fallback = True
            # Try fallback immediately (one attempt, no retries)
            client = get_llm_client(provider)
            raw_response = await client.generate(system_prompt, user_prompt)
            return await _succeed(raw_response, provider, retries=0)

        try:
            return await _succeed(raw_response, provider, retries=attempt)
        except (ValidationError, yaml.YAMLError) as exc:
            last_error = str(exc)
            _log(
                f"Validation error (attempt {attempt + 1}/{max_retries}), "
                f"retrying... ({exc})"
            )

    # After max_retries exhausted on primary, try fallback if applicable
    if auto_fallback and not used_fallback:
        _log(
            f"{provider} 최대 재시도 초과, "
            f"{'openai' if provider == 'gemini' else 'gemini'}로 전환합니다..."
        )
        provider = "openai" if provider == "gemini" else "gemini"
        client = get_llm_client(provider)
        raw_response = await client.generate(
            system_prompt, _build_prompt(last_error)
        )
        return await _succeed(raw_response, provider, retries=max_retries)

    raise ValueError(
        "Adapter generation failed with both providers. "
        f"Last error: {last_error}"
    )


# Fields the LLM auto-maps and that a repair pass may re-select. Image/detail/option
# fields are excluded — those are picked manually in stage 3.
REPAIRABLE_PRODUCT_FIELDS = (
    "supplier_product_code",
    "raw_product_name",
    "supply_price",
    "origin",
    "main_image_url",
)

_REPAIR_FIELD_HINTS = {
    "supplier_product_code": "상품 고유 코드/상품번호 텍스트",
    "raw_product_name": "상품명 제목 텍스트",
    "supply_price": "공급가/가격 숫자 (attribute 비우고 transform: extract_number)",
    "origin": "원산지 텍스트",
    "main_image_url": "대표 상품 이미지 img 태그 (attribute: src, 없으면 data-src)",
}

REPAIR_SYSTEM_PROMPT = """당신은 웹 스크래핑 CSS 선택자 교정 전문가입니다.
아래 필드들은 기존 어댑터의 CSS 선택자가 **실제 페이지에서 빈 값을 추출**했습니다.
주어진 상품 DOM을 다시 분석해 각 필드의 **더 정확한 CSS 선택자**를 찾으세요.

반드시 다음 JSON 형식으로만 응답하세요 (설명·코드블록 없이):
{"field_name": {"selector": "CSS선택자", "attribute": "src|data-src|value 또는 빈문자열", "transform": "extract_number 또는 빈문자열"}, ...}

규칙:
1. 값을 찾을 수 없는 필드는 결과에서 완전히 생략하세요 (빈 선택자 금지).
2. 가격(supply_price)은 attribute를 비우고 transform을 "extract_number"로 설정하세요.
3. 대표 이미지(main_image_url)는 attribute를 "src"로 하되 URL이 data-src에만 있으면 "data-src"로 하세요.
4. 원산지(origin)는 "대한민국", "중국", "국산" 같은 값 텍스트만 선택하세요. 판매가/배송비/상품코드가 같이 잡히는 컨테이너 선택자는 금지입니다.
5. 선택자는 구체적이고 고유하게(id/class/속성 활용). nth-of-type 남발 금지.
6. JSON 외 텍스트 출력 금지.
"""


def _repair_dom_context(probe_result: ProbeResult) -> str:
    parts: list[str] = []
    detail = getattr(probe_result, "detail_html", "") or ""
    listing = getattr(probe_result, "listing_html", "") or ""
    if detail:
        parts.append(f"## 상품 상세 페이지 DOM\n{detail[:12000]}")
    if listing:
        parts.append(f"## 상품 목록 페이지 DOM\n{listing[:8000]}")
    return "\n\n".join(parts)


def _apply_repaired_fields(yaml_text: str, repaired: dict) -> str:
    """Merge repaired field selectors into the YAML, replacing only those fields.

    Returns the re-dumped YAML if it still validates, else the original text.
    """
    raw = yaml.safe_load(yaml_text)
    if not isinstance(raw, dict):
        return yaml_text
    product = raw.setdefault("adapter", {}).setdefault("product", {})
    if not isinstance(product, dict):
        return yaml_text
    changed = False
    for field, spec in (repaired or {}).items():
        if field not in REPAIRABLE_PRODUCT_FIELDS or not isinstance(spec, dict):
            continue
        selector = str(spec.get("selector") or "").strip()
        if not selector:
            continue
        entry: dict = {**PRODUCT_DEFAULTS.get(field, {}), "selector": selector}
        attribute = str(spec.get("attribute") or "").strip()
        if attribute:
            entry["attribute"] = attribute
        transform = str(spec.get("transform") or "").strip()
        if transform:
            entry["transform"] = transform
        product[field] = entry
        changed = True
    if not changed:
        return yaml_text
    _strip_empty_selectors(raw)
    _sanitize_pseudo_elements(raw)  # repair가 되돌린 ::before 등 의사요소 선택자 제거
    try:
        adapter = Adapter.model_validate(raw)
    except ValidationError:
        return yaml_text
    return yaml.safe_dump(adapter.model_dump(mode="json", exclude_none=True), allow_unicode=True, sort_keys=False)


async def repair_adapter_fields(
    yaml_text: str,
    failed_fields: list[str],
    probe_result: ProbeResult,
    llm_provider: str = "gemini",
    auto_fallback: bool = True,
    on_progress: Callable[[str], None] | None = None,
) -> str:
    """One-shot LLM repair of product fields whose selectors extracted empty values.

    Returns updated YAML (or the original text unchanged if repair fails/yields nothing).
    # ponytail: single repair pass; add iteration only if one pass measurably falls short.
    """
    targets = [f for f in failed_fields if f in REPAIRABLE_PRODUCT_FIELDS]
    dom = _repair_dom_context(probe_result)
    if not targets or not dom:
        return yaml_text

    def _log(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    field_lines = "\n".join(f"- {f}: {_REPAIR_FIELD_HINTS.get(f, '')}" for f in targets)
    user_prompt = f"## 다시 선택자를 찾을 필드\n{field_lines}\n\n{dom}"

    _log(f"빈 값 필드 {len(targets)}개 자동 재매핑 중...")
    provider = llm_provider
    try:
        response = await get_llm_client(provider).generate(REPAIR_SYSTEM_PROMPT, user_prompt)
    except QuotaExceededError:
        if not auto_fallback:
            return yaml_text
        provider = "openai" if provider == "gemini" else "gemini"
        _log(f"할당량 초과, {provider}로 재매핑 전환...")
        response = await get_llm_client(provider).generate(REPAIR_SYSTEM_PROMPT, user_prompt)

    text = response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end]).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group()
    try:
        repaired = json.loads(text)
    except json.JSONDecodeError:
        _log("자동 재매핑 응답을 해석하지 못했습니다.")
        return yaml_text
    if not isinstance(repaired, dict):
        return yaml_text
    return _apply_repaired_fields(yaml_text, repaired)
