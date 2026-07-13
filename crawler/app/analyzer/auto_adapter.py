"""전체 자동화 어댑터 오케스트레이터.

기존 4단계 수동 마법사의 2단계(사람이 브라우저에서 선택자를 클릭하는 부분)를,
AI가 스스로 생성→라이브검증→재프롬프트하는 자동 루프로 대체하는 *병행* 실행 경로.
기존 수동 경로는 그대로 두고 이쪽만 새로 추가한다.

이 모듈은 순수 async 로직만 담는다 — Playwright/LLM/QThread 접촉은 전부 주입된
``AutoAdapterDeps`` 콜러블 뒤에 둬서 테스트에서 fake 로 대체할 수 있게 한다.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field as dc_field
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qs, urlparse

import yaml
from bs4 import BeautifulSoup

from app.analyzer.adapter_generator import REPAIRABLE_PRODUCT_FIELDS
from app.analyzer.adapter_schema import FIELD_LABELS_KO, OPTION_VALUES_FIELD_PATH
from app.analyzer.mapping_hints import MappingHint
from app.analyzer.option_text_parser import is_option_placeholder
from app.analyzer.validation_summary import is_field_value_ok


# ── 튜닝 상수 (매직넘버 금지) ────────────────────────────────────────────────
AUTO_FIELD_RETRY_CAP = 4          # 필드별 재프롬프트 상한. 초과 시 그 필드만 미확정.
AUTO_LIVE_SAMPLE_MAX = 5          # 다각도 라이브 검증에 쓸 샘플 상품 URL 최대 개수.
AUTO_MAJORITY_RATIO = 0.5         # 과반(≥ 절반) URL에서 통과하면 필드 확정.
AUTO_STATUS_SCAN_MAX = 6          # 판매중/품절 후보 쌍을 찾을 때 스캔할 샘플 최대 개수.

_CATEGORY_FIELD_PATH = "adapter.categories.navigation.menu_selector"


@dataclass(frozen=True)
class AutoField:
    test_key: str            # AdapterTestWorker 필드명 (라이브 검증 키)
    field_path: str          # MappingHint / YAML 경로
    page_kind: str = "detail"
    manual_only: bool = False  # 미확정 시 YAML에서 후보를 제거할지 (핵심 상품필드는 유지)


# 핵심 상품 필드 — 항상 검증/재시도 대상.
_PRODUCT_FIELDS = [AutoField(name, f"adapter.product.{name}") for name in REPAIRABLE_PRODUCT_FIELDS]
# manual-only 필드 — base YAML에 후보가 있을 때만 대상 (없으면 해당 사이트에 없다고 보고 스킵).
_MANUAL_FIELDS = [
    AutoField("detail_content", "adapter.product.detail_content", manual_only=True),
    AutoField("extra_image_urls", "adapter.product.extra_image_urls", manual_only=True),
    AutoField("option_values", "adapter.options.groups.0.values_selector", manual_only=True),
    AutoField("option_prices", "adapter.options.option_price_delta", manual_only=True),
]


@dataclass
class AutoAdapterDeps:
    """오케스트레이터가 필요로 하는 브라우저/LLM 작업. 워커가 실제 구현을, 테스트가 fake 를 준다."""

    # 확장 프롬프트로 1차 YAML 생성 (manual 후보 포함).
    generate: Callable[[], Awaitable[str]]
    # 여러 URL × 필드 라이브 검증 → {test_key: [entry, ...]} (AdapterTestWorker.raw_results 형태).
    test_fields: Callable[[str, list[str], tuple[str, ...]], Awaitable[dict[str, list[dict]]]]
    # 한 필드 재선택(실패 피드백 기반) → 갱신된 YAML(개선 없으면 원본 그대로).
    repair_field: Callable[[str, AutoField, str], Awaitable[str]]
    # 샘플 URL 스캔 → (available_url, soldout_url) | None. None 이면 조용히 스킵.
    find_status_pair: Callable[[list[str]], Awaitable[tuple[str, str] | None]] | None = None
    # 판매중/품절 비교 → suggestion dict (SoldoutCompareWorker 결과 형태).
    compare_status: Callable[[str, str, str], Awaitable[dict]] | None = None
    # 옵션 텍스트 파서 분석 → parser dict | None.
    analyze_options: Callable[[str, str], Awaitable[dict | None]] | None = None
    # 추출값 타당성 LLM 검수: {field_key: [샘플값...]} → {field_key: {"ok": bool, "reason": str}}.
    # None 이거나 예외/파싱실패 시 파이프라인을 막지 않고 통과로 간주한다.
    judge_values: Callable[[dict[str, list[str]]], Awaitable[dict[str, dict]]] | None = None


@dataclass
class AutoAdapterResult:
    yaml_text: str
    mapping_hints: list[MappingHint] = dc_field(default_factory=list)  # 확정 필드 (참고/기록용)
    unresolved_fields: list[str] = dc_field(default_factory=list)      # 사람이 마저 처리할 field_path
    log: list[str] = dc_field(default_factory=list)
    status_pair: tuple[str, str] | None = None
    # 필드별 판정: {field_path: {"state": "confirmed|unresolved|absent|skipped", "reason": str}}
    dispositions: dict[str, dict] = dc_field(default_factory=dict)


# ── 순수 헬퍼 ────────────────────────────────────────────────────────────────
def _field_passes(test_key: str, entries: list[dict]) -> bool:
    if not entries:
        return False
    passed = sum(1 for e in entries if isinstance(e, dict) and is_field_value_ok(test_key, e))
    return passed >= max(1, math.ceil(len(entries) * AUTO_MAJORITY_RATIO))


def _read_spec(data: dict, field: AutoField) -> dict:
    """현재 YAML dict 에서 필드의 선택자 스펙을 읽는다. 없으면 {}."""
    adapter = (data or {}).get("adapter") or {}
    if field.field_path == "adapter.options.groups.0.values_selector":
        groups = (adapter.get("options") or {}).get("groups") or []
        if groups and isinstance(groups[0], dict):
            return {"selector": groups[0].get("values_selector") or ""}
        return {}
    if field.field_path == "adapter.options.option_price_delta":
        spec = (adapter.get("options") or {}).get("option_price_delta")
        return dict(spec) if isinstance(spec, dict) else {}
    if field.field_path.startswith("adapter.product."):
        name = field.field_path.rsplit(".", 1)[-1]
        spec = (adapter.get("product") or {}).get(name)
        return dict(spec) if isinstance(spec, dict) else {}
    return {}


def _read_selector(data: dict, field: AutoField) -> str:
    return str(_read_spec(data, field).get("selector") or "").strip()


def _hint_from_spec(field: AutoField, spec: dict) -> MappingHint | None:
    selector = str(spec.get("selector") or "").strip()
    if not selector:
        return None
    kwargs: dict[str, Any] = {
        "page_kind": field.page_kind,
        "field_path": field.field_path,
        "chosen_selector": selector,
    }
    for key in ("attribute", "transform", "multiple", "html", "fallback", "fallback_from"):
        value = spec.get(key)
        if value not in (None, ""):
            kwargs[key] = value
    try:
        return MappingHint(**kwargs)
    except ValueError:
        return None


def _strip_field(yaml_text: str, field: AutoField) -> str:
    """미확정 manual-only 필드의 깨진 후보를 YAML 에서 제거 (사람이 깨끗이 재선택하도록)."""
    try:
        raw = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError:
        return yaml_text
    adapter = raw.get("adapter")
    if not isinstance(adapter, dict):
        return yaml_text
    if field.field_path == "adapter.options.groups.0.values_selector":
        if isinstance(adapter.get("options"), dict):
            adapter["options"].pop("groups", None)
    elif field.field_path == "adapter.options.option_price_delta":
        if isinstance(adapter.get("options"), dict):
            adapter["options"].pop("option_price_delta", None)
    elif field.field_path.startswith("adapter.product."):
        name = field.field_path.rsplit(".", 1)[-1]
        if isinstance(adapter.get("product"), dict):
            adapter["product"].pop(name, None)
    return yaml.safe_dump(raw, allow_unicode=True, sort_keys=False)


# 상품코드로 흔히 쓰이는 쿼리 파라미터 이름 — 앞일수록 강한 신호(정확일치 우선).
_CODE_PARAM_NAMES = [
    "branduid", "goodsno", "goods_no", "product_no", "productno",
    "prdno", "prd_no", "pid", "itemid", "item_id", "it_id",
    "pcode", "p_code", "code", "uid", "idx", "no", "id",
]


def derive_code_url_param(urls: list[str]) -> str | None:
    """샘플 URL들의 쿼리 파라미터에서 상품코드일 가능성이 높은 파라미터 이름을 결정적으로 유도.

    후보: 과반 URL에 존재하고 URL마다 값이 서로 다른(≥2종) 파라미터.
    우선순위: (1) 알려진 코드 이름 정확일치 → (2) 값이 전부 숫자 → (3) 그 외. 없으면 None.
    """
    parsed = [parse_qs(urlparse(u).query) for u in urls if u]
    if not parsed:
        return None
    threshold = max(1, math.ceil(len(parsed) * AUTO_MAJORITY_RATIO))
    values: dict[str, list[str]] = {}
    for qs in parsed:
        for name, vals in qs.items():
            values.setdefault(name, []).append((vals or [""])[0])
    pool = {
        name: vals for name, vals in values.items()
        if len([v for v in vals if v]) >= threshold and len({v for v in vals if v}) >= 2
    }
    if not pool:
        return None
    lower = {name.lower(): name for name in pool}
    for known in _CODE_PARAM_NAMES:  # (1) 알려진 이름 정확일치
        if known in lower:
            return lower[known]
    for name, vals in pool.items():  # (2) 값이 전부 숫자
        if all(v.isdigit() for v in vals if v):
            return name
    return next(iter(pool))  # (3) 그 외 첫 후보


def _apply_url_param(yaml_text: str, field: AutoField, param: str) -> str:
    """필드를 {fallback_from: url, url_param: <param>} 로 교체(selector 제거). 뷰모델 setFieldUrlParam과 동형."""
    try:
        raw = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError:
        return yaml_text
    product = (raw.get("adapter") or {}).get("product")
    if not isinstance(product, dict):
        return yaml_text
    product[field.field_path.rsplit(".", 1)[-1]] = {"fallback_from": "url", "url_param": param}
    return yaml.safe_dump(raw, allow_unicode=True, sort_keys=False)


def _apply_status_suggestion(yaml_text: str, suggestion: dict) -> str:
    """품절 판별 제안을 supplier_status/status_mapping 으로 병합.

    뷰모델 acceptSoldoutSuggestion 과 같은 규칙 (여기선 오케스트레이터가 자동 적용).
    """
    selector = str(suggestion.get("selector") or "").strip()
    fallback_from = str(suggestion.get("fallback_from") or "none").strip()
    if fallback_from not in {"none", "cart_button", "maxq"}:
        fallback_from = "none"
    if not selector and fallback_from == "none":
        return yaml_text
    try:
        raw = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError:
        return yaml_text
    product = raw.setdefault("adapter", {}).setdefault("product", {})
    if not isinstance(product, dict):
        return yaml_text
    field: dict[str, Any] = {}
    if selector:
        field["selector"] = selector
        if fallback_from == "none" and "img" in selector.lower():
            field["attribute"] = "alt"
            field["fallback_attribute"] = "src"
    if fallback_from != "none":
        field["fallback_from"] = fallback_from
    product["supplier_status"] = field
    mapping = dict(suggestion.get("mapping") or {})
    if fallback_from in {"cart_button", "maxq"}:
        mapping.update({"available": "available", "sold_out": "sold_out"})
    else:
        mapping.setdefault("품절", "sold_out")
        mapping.setdefault("완판", "sold_out")
        mapping.setdefault("soldout", "sold_out")
        mapping.setdefault("sold out", "sold_out")
        mapping.setdefault("판매중", "available")
    product["status_mapping"] = {"mapping": mapping, "default": suggestion.get("default") or "available"}
    return yaml.safe_dump(raw, allow_unicode=True, sort_keys=False)


def _splice_option_parser(yaml_text: str, parser: dict) -> str:
    try:
        raw = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError:
        return yaml_text
    options = raw.setdefault("adapter", {}).setdefault("options", {})
    if not isinstance(options, dict):
        return yaml_text
    options["option_text_parser"] = dict(parser)
    return yaml.safe_dump(raw, allow_unicode=True, sort_keys=False)


def _failure_feedback(field: AutoField, entries: list[dict]) -> str:
    if not entries:
        return "모든 샘플에서 값을 추출하지 못했습니다 (선택자가 아무 요소도 못 잡음)."
    # 추가 이미지가 전 샘플에서 0개 — 대표 이미지 dedup 후 비었을 가능성이 큼.
    if field.test_key == "extra_image_urls" and not any(e.get("imageCount") for e in entries):
        return (
            "추가 이미지가 0개입니다. 선택자가 대표 이미지만 잡았거나 갤러리가 없습니다. "
            "대표 이미지와 다른 썸네일/갤러리 영역의 img를 선택하세요."
        )
    parts: list[str] = []
    for entry in entries[:4]:
        url = str(entry.get("url") or "")
        err = entry.get("error")
        value = entry.get("value")
        if err:
            parts.append(f"- {url}: 에러 {err}")
        elif not is_field_value_ok(field.test_key, entry):
            parts.append(f"- {url}: 유효하지 않은 값 {str(value)[:60]!r}")
    return "다음 샘플에서 실패했습니다:\n" + "\n".join(parts)


# ── 자동 모드 전용 강화 검증 ─────────────────────────────────────────────────
# is_field_value_ok(수동 마법사와 공용)는 동작을 바꾸지 않고, auto 경로에만 계층을 얹는다.
_DISTINCT_FIELDS = {"raw_product_name", "supplier_product_code", "main_image_url"}
_DISTINCT_MIN_SAMPLES = 3   # 유효 값이 이 개수 이상인데 전부 동일하면 사이트 공통 요소를 잡은 것
_JUDGE_EXCLUDE = {"detail_content", "extra_image_urls"}  # '3개 인식' 같은 개수 요약이라 값 검수 무의미

_FIELD_LABELS = {**FIELD_LABELS_KO, "option_values": "옵션값", "option_prices": "옵션가격"}

_SUPPLIER_STATUS_FIELD = AutoField("supplier_status", "adapter.product.supplier_status", manual_only=True)


def _event_line(kind: str, **payload: Any) -> str:
    """UI 대시보드용 구조화 이벤트 한 줄. progress 시그널(str)로 그대로 흘린다."""
    return "[event:" + json.dumps({"kind": kind, **payload}, ensure_ascii=False) + "]"


def _entry_values(entries: list[dict]) -> list[str]:
    return [str(e.get("value") or "").strip() for e in entries if isinstance(e, dict)]


def _value_preview(entries: list[dict]) -> str:
    for value in _entry_values(entries):
        if value:
            return value[:80]
    return ""


def _distinctness_failure(test_key: str, entries: list[dict]) -> str | None:
    """상품마다 달라야 하는 필드가 모든 샘플에서 동일 값이면 실패 사유를 돌려준다."""
    if test_key not in _DISTINCT_FIELDS:
        return None
    values = [v for v in _entry_values(entries) if v]
    if len(values) >= _DISTINCT_MIN_SAMPLES and len(set(values)) == 1:
        return (
            f"선택자가 모든 상품에서 동일한 값 {values[0][:80]!r}을 반환 — "
            "상품별 요소가 아닌 사이트 공통 요소(헤더/푸터/배너)를 잡은 것입니다."
        )
    return None


def _tokens(text: Any) -> set[str]:
    return set(re.findall(r"[0-9A-Za-z가-힣]+", str(text).lower()))


def _parse_price(text: Any) -> float | None:
    m = re.search(r"\d[\d.]*", str(text).replace(",", ""))
    try:
        return float(m.group()) if m else None
    except ValueError:
        return None


def _basename(url: str) -> str:
    return url.split("?", 1)[0].rsplit("/", 1)[-1]


def _structured_check(test_key: str, entry: dict, structured: dict) -> tuple[str | None, str | None]:
    """probe 상세 페이지의 og/JSON-LD 값과 추출값 대조 → (실패 사유, 확인 note)."""
    value = str(entry.get("value") or "").strip()
    if not value or not structured:
        return None, None
    if test_key == "raw_product_name":
        ref = structured.get("og:title") or structured.get("jsonld:name")
        if ref and not (_tokens(value) & _tokens(ref)):
            return (
                f"페이지 og:title은 {str(ref)[:80]!r}인데 추출값은 {value[:80]!r}입니다 — "
                "상품명이 아닌 요소를 잡았습니다.",
                None,
            )
    elif test_key == "supply_price":
        ref = structured.get("jsonld:price") or structured.get("product:price:amount")
        ref_num, val_num = _parse_price(ref or ""), _parse_price(value)
        if ref_num is not None and val_num is not None and ref_num != val_num:
            return f"페이지 구조화 데이터의 가격은 {ref}인데 추출값은 {value[:40]!r}입니다.", None
    elif test_key == "main_image_url":
        ref = structured.get("og:image") or structured.get("jsonld:image")
        if ref and _basename(str(ref)) and _basename(str(ref)) == _basename(value):
            # 불일치는 실패로 치지 않음 — og:image가 대표이미지와 다른 파일일 수 있다.
            return None, f"대표이미지가 og:image({_basename(str(ref))})와 일치 — 강한 확정 신호."
    return None, None


def _live_failure(
    field: AutoField,
    entries: list[dict],
    structured: dict,
    detail_page_url: str,
    on_note: Callable[[str], None],
) -> str | None:
    """과반 + 판별력 + 구조화 대조 종합 판정. 통과면 None, 실패면 재프롬프트 피드백."""
    if not _field_passes(field.test_key, entries):
        return _failure_feedback(field, entries)
    reason = _distinctness_failure(field.test_key, entries)
    if reason:
        return reason
    if detail_page_url and structured:
        for entry in entries:
            if str(entry.get("url") or "") != detail_page_url:
                continue
            fail, note = _structured_check(field.test_key, entry, structured)
            if note:
                on_note(note)
            if fail:
                return fail
    return None


async def _judge_or_pass(
    judge: Callable[[dict[str, list[str]]], Awaitable[dict[str, dict]]] | None,
    samples: dict[str, list[str]],
    on_note: Callable[[str], None],
) -> dict[str, dict]:
    """judge 콜러블이 없거나 실패하면 파이프라인을 막지 않고 전부 통과로 간주."""
    if judge is None or not samples:
        return {}
    try:
        verdicts = await judge(samples)
        return verdicts if isinstance(verdicts, dict) else {}
    except Exception as exc:
        on_note(f"AI 값 검수 실패 — 통과로 간주: {exc}")
        return {}


def _judge_rejection(verdicts: dict[str, dict], test_key: str) -> str | None:
    verdict = verdicts.get(test_key)
    if isinstance(verdict, dict) and verdict.get("ok") is False:
        return f"AI 값 검수 불합격: {str(verdict.get('reason') or '사유 없음')[:120]}"
    return None


_QTY_TOKENS = ("qty", "quantity", "수량")


def detect_option_evidence(detail_html: str) -> bool:
    """상세 DOM에 실제 옵션 <select>가 있는지 — placeholder 아닌 <option> 2개 이상."""
    if not detail_html:
        return False
    soup = BeautifulSoup(detail_html, "html.parser")
    for select in soup.find_all("select"):
        ident = f"{select.get('name') or ''} {select.get('id') or ''}".lower()
        if any(tok in ident for tok in _QTY_TOKENS):
            continue
        real = [o for o in select.find_all("option") if not is_option_placeholder(o.get_text())]
        if len(real) >= 2:
            return True
    return False


def detect_detail_image_evidence(detail_html: str) -> bool:
    """축소 상세 DOM에 <img>(src 또는 data-src)가 2개 이상이면 상세/추가 이미지가 있다고 본다."""
    if not detail_html:
        return False
    soup = BeautifulSoup(detail_html, "html.parser")
    imgs = [img for img in soup.find_all("img") if img.get("src") or img.get("data-src")]
    return len(imgs) >= 2


def _code_equals_name(code_entries: list[dict], name_entries: list[dict]) -> bool:
    """상품코드와 상품명이 URL별로 과반 동일하면 True — 코드 선택자가 상품명 요소를 잡은 것."""
    code_by_url = {e.get("url"): str(e.get("value") or "").strip() for e in code_entries if isinstance(e, dict)}
    name_by_url = {e.get("url"): str(e.get("value") or "").strip() for e in name_entries if isinstance(e, dict)}
    urls = [u for u in code_by_url if u in name_by_url and code_by_url[u] and name_by_url[u]]
    if not urls:
        return False
    same = sum(1 for u in urls if code_by_url[u] == name_by_url[u])
    return same >= max(1, math.ceil(len(urls) * AUTO_MAJORITY_RATIO))


# ── 메인 오케스트레이터 ──────────────────────────────────────────────────────
async def run_auto_adapter(
    probe_result: Any,
    supplier_name: str,
    deps: AutoAdapterDeps,
    test_urls: list[str] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> AutoAdapterResult:
    log: list[str] = []

    def _log(msg: str, fraction: float | None = None) -> None:
        log.append(msg)
        if on_progress:
            on_progress(f"[progress:{fraction:.2f}] {msg}" if fraction is not None else msg)

    def _emit(kind: str, **payload: Any) -> None:
        if on_progress:
            on_progress(_event_line(kind, **payload))

    def _note(text: str) -> None:
        log.append(text)
        _emit("note", text=text)

    def _emit_field(field: AutoField, status: str, attempt: int, value: str = "", reason: str = "") -> None:
        _emit(
            "field", field=field.field_path, key=field.test_key,
            label=_FIELD_LABELS.get(field.test_key, field.test_key),
            status=status, attempt=attempt, cap=AUTO_FIELD_RETRY_CAP,
            value=(value or "")[:80], reason=(reason or "")[:120],
        )

    dispositions: dict[str, dict] = {}

    def _set_disp(field_path: str, state: str, reason: str = "") -> None:
        dispositions[field_path] = {"state": state, "reason": reason[:200]}

    urls = list(test_urls or [
        str(item.get("url"))
        for item in getattr(probe_result, "sample_products", []) or []
        if item.get("url")
    ])[:AUTO_LIVE_SAMPLE_MAX]
    if not urls:
        # 라이브 검증 대상이 없으면 자동화 불가 — 사람이 샘플 URL을 줘야 한다.
        _log("검증할 샘플 상품 URL이 없습니다.", 1.0)
        return AutoAdapterResult(yaml_text="", unresolved_fields=[], log=log)

    _emit("stage", stage="generate", status="active", label="수집 설정 생성")
    _log("확장 프롬프트로 수집 설정 초안 생성 중...", 0.05)
    working_yaml = await deps.generate()
    # supplier_status 위생: 라이브 검증이 불가능한 필드는 LLM 추측만으로 받지 않는다.
    # 판매 상태는 아래 status-pair 비교 경로(confidence high/medium)로만 설정된다.
    stripped_status = _strip_field(working_yaml, _SUPPLIER_STATUS_FIELD)
    if stripped_status != working_yaml:
        working_yaml = stripped_status
        _note("1차 YAML의 supplier_status 후보 제거 — 판매 상태는 실측 비교로만 확정합니다.")
    _emit("stage", stage="generate", status="done", label="수집 설정 생성")

    base = yaml.safe_load(working_yaml) or {}
    targets = list(_PRODUCT_FIELDS)
    targets += [f for f in _MANUAL_FIELDS if _read_selector(base, f)]  # 후보 있는 manual 필드만
    # 옵션 강제 추적: 1차 YAML에 후보가 없어도 상세 DOM에 옵션 <select> 증거가 있으면 대상 포함.
    option_field = next(f for f in _MANUAL_FIELDS if f.field_path == OPTION_VALUES_FIELD_PATH)
    detail_html_text = getattr(probe_result, "detail_html", "") or ""
    if option_field not in targets and detect_option_evidence(detail_html_text):
        targets.append(option_field)
        _note("상세 DOM에서 옵션 select 증거 발견 — 옵션값 선택자 탐색을 강제합니다.")
    # 이미지 강제 추적: 1차 YAML에 후보가 없어도 상세 DOM에 <img> 증거가 있으면 대상 포함.
    if detect_detail_image_evidence(detail_html_text):
        _IMAGE_FIELD_PATHS = ("adapter.product.detail_content", "adapter.product.extra_image_urls")
        forced = False
        for path in _IMAGE_FIELD_PATHS:
            image_field = next(f for f in _MANUAL_FIELDS if f.field_path == path)
            if image_field not in targets:
                targets.append(image_field)
                forced = True
        if forced:
            _note("상세 DOM에서 이미지 증거 발견 — 상세/추가 이미지 선택자 탐색을 강제합니다.")

    structured = dict(getattr(probe_result, "structured_data", None) or {})
    detail_page_url = str(getattr(probe_result, "detail_page_url", "") or "")

    all_keys = tuple(f.test_key for f in targets)
    _emit("stage", stage="verify", status="active", label="라이브 검증")
    _log(f"{len(urls)}개 샘플에서 {len(all_keys)}개 필드 라이브 검증 중...", 0.20)
    results = await deps.test_fields(working_yaml, urls, all_keys)

    # 1차 종합 판정(과반+판별력+구조화) 후, 통과 필드들만 모아 한 번에 AI 값 검수.
    failures: dict[str, str] = {}
    for field in targets:
        reason = _live_failure(field, results.get(field.test_key, []), structured, detail_page_url, _note)
        if reason is not None:
            failures[field.test_key] = reason
    # 교차 필드 검사: 상품코드가 상품명과 과반 동일하면 코드 선택자가 상품명 요소를 잡은 것.
    # 실패 처리하면 아래 repair 루프에서 URL 파라미터 유도(branduid 등)가 먼저 시도돼 해결된다.
    if "supplier_product_code" not in failures and _code_equals_name(
        results.get("supplier_product_code", []), results.get("raw_product_name", []),
    ):
        failures["supplier_product_code"] = (
            "상품코드 선택자가 상품명과 같은 요소를 잡았습니다. "
            "코드는 보통 별도 셀이나 URL 파라미터에 있습니다."
        )
    judge_samples = {
        f.test_key: _entry_values(results.get(f.test_key, []))
        for f in targets
        if f.test_key not in failures and f.test_key not in _JUDGE_EXCLUDE
    }
    verdicts = await _judge_or_pass(deps.judge_values, judge_samples, _note)
    for field in targets:
        rejection = _judge_rejection(verdicts, field.test_key)
        if rejection and field.test_key not in failures:
            failures[field.test_key] = rejection

    confirmed: list[MappingHint] = []
    unresolved: list[str] = []
    span = max(1, len(targets))
    for idx, field in enumerate(targets):
        fraction = 0.25 + 0.55 * (idx / span)
        entries = results.get(field.test_key, [])
        failure = failures.get(field.test_key)
        _emit_field(field, "testing", 1, _value_preview(entries), failure or "")
        if failure is None:
            hint = _hint_from_spec(field, _read_spec(base, field))
            if hint:
                confirmed.append(hint)
            _emit_field(field, "confirmed", 1, _value_preview(entries))
            _set_disp(field.field_path, "confirmed", f"{len(urls)}개 샘플 검증 통과")
            _log(f"{field.field_path} 확정 (1차 통과)", fraction)
            continue

        # 상품코드: URL 쿼리 파라미터 결정적 유도를 LLM repair보다 먼저 시도 (재시도 카운트 무소모).
        if field.test_key == "supplier_product_code":
            param = derive_code_url_param(urls)
            if param:
                candidate_yaml = _apply_url_param(working_yaml, field, param)
                cand = (await deps.test_fields(candidate_yaml, urls, (field.test_key,))).get(field.test_key, [])
                if _live_failure(field, cand, structured, detail_page_url, _note) is None:
                    working_yaml = candidate_yaml
                    base = yaml.safe_load(working_yaml) or {}
                    _note(f"상품코드를 URL 파라미터 {param}에서 추출")
                    _emit_field(field, "confirmed", 1, _value_preview(cand))
                    _set_disp(field.field_path, "confirmed", f"URL 파라미터 {param}에서 추출")
                    _log(f"{field.field_path} 확정 (URL 파라미터 {param} 유도)", fraction)
                    continue
                # 유도 실패 — working_yaml 미변형이므로 그대로 기존 repair 루프 진행.

        resolved = False
        for attempt in range(1, AUTO_FIELD_RETRY_CAP + 1):
            _emit_field(field, "retry", attempt, _value_preview(entries), failure)
            _log(f"{field.field_path} 재선택 시도 {attempt}/{AUTO_FIELD_RETRY_CAP}...", fraction)
            new_yaml = await deps.repair_field(working_yaml, field, failure)
            if not new_yaml or new_yaml == working_yaml:
                break  # LLM이 개선 못 함 — 더 돌려도 같음
            working_yaml = new_yaml
            base = yaml.safe_load(working_yaml) or {}
            entries = (await deps.test_fields(working_yaml, urls, (field.test_key,))).get(field.test_key, [])
            failure = _live_failure(field, entries, structured, detail_page_url, _note)
            if failure is None and field.test_key not in _JUDGE_EXCLUDE:
                # 재시도 성공 후에도 AI 값 검수를 다시 통과해야 확정.
                retry_verdicts = await _judge_or_pass(
                    deps.judge_values, {field.test_key: _entry_values(entries)}, _note,
                )
                failure = _judge_rejection(retry_verdicts, field.test_key)
            if failure is None:
                hint = _hint_from_spec(field, _read_spec(base, field))
                if hint:
                    confirmed.append(hint)
                _emit_field(field, "confirmed", attempt, _value_preview(entries))
                _set_disp(field.field_path, "confirmed", f"재시도 {attempt}회 후 수렴")
                _log(f"{field.field_path} 확정 (재시도 {attempt}회 후 수렴)", fraction)
                resolved = True
                break

        if not resolved:
            unresolved.append(field.field_path)
            _emit_field(field, "unresolved", AUTO_FIELD_RETRY_CAP, _value_preview(entries), failure or "")
            _set_disp(field.field_path, "unresolved", failure or "재시도 상한 도달 — 수동 확인 필요")
            _log(f"{field.field_path} 상한 도달 — 사람에게 위임", fraction)
            if field.manual_only:
                working_yaml = _strip_field(working_yaml, field)
    _emit("stage", stage="verify", status="done", label="라이브 검증")

    # ── 판매 상태: 판매중/품절 후보 쌍 자동 탐색 → 못 찾으면 조용히 스킵 ──
    status_pair: tuple[str, str] | None = None
    _status_path = _SUPPLIER_STATUS_FIELD.field_path
    if deps.find_status_pair:
        _emit("stage", stage="status", status="active", label="판매 상태 판별")
        _log("판매중/품절 상품 후보 쌍 탐색 중...", 0.85)
        status_pair = await deps.find_status_pair(urls)
        if status_pair and deps.compare_status:
            suggestion = await deps.compare_status(working_yaml, status_pair[0], status_pair[1])
            if suggestion and str(suggestion.get("confidence") or "low") != "low":
                working_yaml = _apply_status_suggestion(working_yaml, suggestion)
                _log("판매 상태 선택자 자동 확정", 0.88)
                _emit("stage", stage="status", status="done", label="판매 상태 판별")
                _set_disp(_status_path, "confirmed", "품절/판매중 실측 비교로 판별자 확정")
                _emit_field(_SUPPLIER_STATUS_FIELD, "confirmed", 1, reason="품절/판매중 실측 비교로 판별자 확정")
            else:
                reason = "품절 판별 신뢰도 낮음 — 수동 확인 필요"
                _log("판매 상태를 확신하지 못해 기본값(available)으로 둡니다.", 0.88)
                _emit("stage", stage="status", status="skipped", label="판매 상태 판별")
                _set_disp(_status_path, "unresolved", reason)
                _emit_field(_SUPPLIER_STATUS_FIELD, "unresolved", AUTO_FIELD_RETRY_CAP, reason=reason)
        else:
            reason = f"샘플 {len(urls)}개 중 품절 상품 없음 — 기본값 '판매중'으로 동작"
            _log("판매중/품절 후보 쌍을 찾지 못해 판매 상태를 건너뜁니다.", 0.88)
            _emit("stage", stage="status", status="skipped", label="판매 상태 판별")
            _set_disp(_status_path, "absent", reason)
            _emit_field(_SUPPLIER_STATUS_FIELD, "absent", 0, reason=reason)
    else:
        reason = "판매 상태 자동 판별 미수행 — 기본값 '판매중'으로 동작"
        _set_disp(_status_path, "absent", reason)
        _emit_field(_SUPPLIER_STATUS_FIELD, "absent", 0, reason=reason)

    # ── 옵션 텍스트 파서: 옵션값이 확정됐을 때만 ──
    option_values_ok = any(h.field_path == OPTION_VALUES_FIELD_PATH for h in confirmed)
    if option_values_ok and deps.analyze_options:
        _emit("stage", stage="options", status="active", label="옵션 분석")
        _log("옵션 텍스트 파서 자동 설계 중...", 0.92)
        try:
            parser = await deps.analyze_options(working_yaml, urls[0])
        except Exception as exc:  # 파서 실패는 치명적 아님 — 옵션값은 원문으로 수집됨
            parser = None
            _log(f"옵션 파서 자동 설계 실패, 건너뜀: {exc}", 0.92)
        if parser:
            working_yaml = _splice_option_parser(working_yaml, parser)
            _log("옵션 텍스트 파서 확정", 0.94)
        _emit("stage", stage="options", status="done" if parser else "skipped", label="옵션 분석")

    # ── 카테고리: 자동 탐지 실패 시 사람에게 위임 (억지 진행 금지) ──
    if not (getattr(probe_result, "categories", None) or getattr(probe_result, "has_all_products", False)):
        unresolved.append(_CATEGORY_FIELD_PATH)
        _log("카테고리 자동 탐지 실패 — 카테고리 메뉴 지정을 사람에게 위임", 0.96)
        _emit("stage", stage="category", status="failed", label="카테고리 탐지")
    else:
        _emit("stage", stage="category", status="done", label="카테고리 탐지")

    # ── 추적하지 않은 옵션/이미지 필드는 absent 로 명시(누락 아님을 UI가 구분하게) ──
    _ABSENT_REASONS = {
        OPTION_VALUES_FIELD_PATH:
            "상세 페이지에서 옵션 요소(select) 미발견 — 이 도매처는 옵션 미제공으로 판정",
        "adapter.options.option_price_delta": "옵션 미제공 — 옵션 가격 없음",
        "adapter.product.detail_content": "상세 페이지에서 이미지 미발견",
        "adapter.product.extra_image_urls": "상세 페이지에서 이미지 미발견",
    }
    for mf in _MANUAL_FIELDS:
        if mf.field_path not in dispositions:
            reason = _ABSENT_REASONS.get(mf.field_path, "미제공")
            _set_disp(mf.field_path, "absent", reason)
            _emit_field(mf, "absent", 0, reason=reason)

    _emit("stage", stage="finalize", status="done", label="마무리")
    _log(
        f"완료: 확정 {len(confirmed)}개, 미확정 {len(unresolved)}개"
        + (f" ({', '.join(unresolved)})" if unresolved else ""),
        1.0,
    )
    return AutoAdapterResult(
        yaml_text=working_yaml,
        mapping_hints=confirmed,
        unresolved_fields=unresolved,
        log=log,
        status_pair=status_pair,
        dispositions=dispositions,
    )
