from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

import yaml
from pydantic import ValidationError

from app.analyzer.adapter_schema import Adapter
from app.analyzer.llm_client import get_llm_client, QuotaExceededError
from app.analyzer.mapping_hints import MappingHint, apply_locked_hints_to_yaml_dict, format_mapping_hints_for_prompt
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
    supplier_status:
      selector: CSS_selector
    status_mapping:
      mapping:
        "판매중": available
        "품절": sold_out
      default: available
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
2. status 값은 한국어 → available/sold_out/stopped 매핑을 포함하세요.
3. 대표 이미지는 src 또는 data-src 속성을 사용하고 jpg/jpeg/png/webp 형식만 대상으로 하세요 (lazy loading 대응).
   상세 페이지(detail_content), 추가 이미지(extra_image_urls), 옵션값(groups), 옵션가격(option_price_delta)은 자동 생성하지 마세요.
   이 필드들은 사용자가 3단계 매핑 화면에서 직접 선택합니다.
4. 선택자를 찾을 수 없는 필드는 해당 필드를 YAML에서 완전히 생략하세요. 빈 문자열("")을 선택자로 사용하지 마세요.
5. YAML만 출력하세요. 코드 블록이나 설명 없이 바로 YAML.
6. 판매 상태(supplier_status) 감지 규칙:
   a. "품절", "soldout", "sold out", "완판" 텍스트나 이미지가 있으면 해당 선택자를 사용하세요.
   b. 명시적인 상태 표시가 없으면, 장바구니/구매 버튼(img[src*='cart'], img[src*='buy']) 존재 여부로 판단하세요.
      이 경우 fallback_from: cart_button 을 설정하세요.
   c. hidden input의 maxq 값이 0이면 품절입니다.
      이 경우 fallback_from: maxq 를 설정하세요.
   d. 판매 상태를 전혀 알 수 없는 경우 supplier_status 필드를 생략하세요.
"""


@dataclass
class GenerationResult:
    yaml_text: str
    adapter: Adapter
    provider_used: str
    retries: int


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


def _finalize_generated_yaml(raw_response: str, mapping_hints: list[MappingHint] | None = None) -> tuple[str, Adapter]:
    raw = yaml.safe_load(_extract_yaml(raw_response))
    _strip_empty_selectors(raw)
    _strip_auto_manual_fields(raw, mapping_hints)
    Adapter.model_validate(raw)
    apply_locked_hints_to_yaml_dict(raw, mapping_hints)
    _strip_empty_selectors(raw)
    adapter = Adapter.model_validate(raw)
    dumped = yaml.safe_dump(adapter.model_dump(mode="json", exclude_none=True), allow_unicode=True, sort_keys=False)
    return dumped, adapter


MANUAL_ONLY_PRODUCT_FIELDS = {"detail_content", "extra_image_urls"}
MANUAL_ONLY_OPTION_FIELDS = {"groups", "option_price_delta"}


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


async def generate_adapter_yaml(
    probe_result: ProbeResult,
    supplier_name: str,
    llm_provider: str = "gemini",
    max_retries: int = 2,
    auto_fallback: bool = True,
    on_progress: Callable[[str], None] | None = None,
    mapping_hints: list[MappingHint] | None = None,
) -> GenerationResult:
    user_prompt = _build_user_prompt(probe_result, supplier_name, mapping_hints)

    def _log(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    def _build_prompt(err: str = "") -> str:
        if err:
            return f"{user_prompt}\n\n## 이전 오류\n{err}\n\n위 오류를 수정하여 다시 생성하세요."
        return user_prompt

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
                SYSTEM_PROMPT,
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
            raw_response = await client.generate(SYSTEM_PROMPT, user_prompt)
            yaml_text, adapter = _finalize_generated_yaml(raw_response, mapping_hints)
            _log(f"Generation succeeded with fallback {provider}.")
            return GenerationResult(
                yaml_text=yaml_text,
                adapter=adapter,
                provider_used=provider,
                retries=0,
            )

        try:
            yaml_text, adapter = _finalize_generated_yaml(raw_response, mapping_hints)
            _log(f"Generation succeeded with {provider}.")
            return GenerationResult(
                yaml_text=yaml_text,
                adapter=adapter,
                provider_used=provider,
                retries=attempt,
            )
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
            SYSTEM_PROMPT, _build_prompt(last_error)
        )
        yaml_text, adapter = _finalize_generated_yaml(raw_response, mapping_hints)
        _log(f"Generation succeeded with fallback {provider}.")
        return GenerationResult(
            yaml_text=yaml_text,
            adapter=adapter,
            provider_used=provider,
            retries=max_retries,
        )

    raise ValueError(
        "Adapter generation failed with both providers. "
        f"Last error: {last_error}"
    )
