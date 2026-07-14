from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
import yaml

from app.analyzer.auto_adapter import (
    AUTO_FIELD_RETRY_CAP,
    AutoAdapterDeps,
    derive_code_url_param,
    detect_detail_image_evidence,
    detect_option_evidence,
    run_auto_adapter,
)


BASE_YAML = """adapter:
  name: T
  base_url: https://x.com
  listing:
    product_link:
      selector: a[href*='detail']
  product:
    supplier_product_code:
      selector: .code
    raw_product_name:
      selector: .name
    supply_price:
      selector: .price
      transform: extract_number
    origin:
      selector: .origin
    main_image_url:
      selector: img.main
      attribute: src
"""

_OK_VALUES = {
    "supply_price": "12000",
    "origin": "국산",
    "option_values": "3개 · S, M, L",
    "option_prices": "3개 · 0, 1000, 2000",
}
_IMAGE_KEYS = {"detail_content", "extra_image_urls"}


def _ok_entry(url: str, key: str) -> dict:
    if key in _IMAGE_KEYS:
        return {"url": url, "value": "3개 인식", "ok": True, "imageUrls": ["/a.jpg"], "imageCount": 3}
    idx = url.rsplit("/", 1)[-1]
    per_url = {  # 상품마다 달라야 하는 필드(판별력 검사 대상)는 URL별로 다른 값
        "supplier_product_code": f"P123-{idx}",
        "raw_product_name": f"멋진 상품 {idx}",
        "main_image_url": f"/img/a{idx}.jpg",
    }
    return {"url": url, "value": per_url.get(key) or _OK_VALUES.get(key, "값"), "ok": True}


def _fail_entry(url: str, key: str) -> dict:
    if key in _IMAGE_KEYS:
        return {"url": url, "value": "0개 인식", "ok": False, "imageUrls": [], "imageCount": 0}
    return {"url": url, "value": "", "ok": False, "error": None}


class FakeDeps(AutoAdapterDeps):
    """AutoAdapterDeps 를 채우는 결정적 fake. Playwright/LLM 없이 루프만 돌린다."""

    def __init__(self, base_yaml: str = BASE_YAML, *, fail_first=(), fail_always=(),
                 bad_values=None, status_pair=None, status_suggestion=None,
                 option_parser=None, judge=None, code_from_name=False):
        self.base_yaml = base_yaml
        self.fail_first = set(fail_first)
        self.fail_always = set(fail_always)
        self.code_from_name = code_from_name  # 상품코드가 상품명과 동일 요소를 잡은 itopic 상황 재현
        self.bad_values = dict(bad_values or {})  # {key: "포맷 {i}"} — repair 전까지 이 값 반환
        self._repaired: set[str] = set()
        self.repair_calls: list[str] = []
        self.feedbacks: list[str] = []
        self.tested: list[tuple[str, ...]] = []
        self.judge_calls: list[dict] = []
        self.tested_urls: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
        self.analyze_url: str | None = None
        self._status_pair = status_pair
        self._status_suggestion = status_suggestion
        self._option_parser = option_parser
        self._judge = judge
        super().__init__(
            generate=self._generate,
            test_fields=self._test_fields,
            repair_field=self._repair_field,
            find_status_pair=self._find_status_pair,
            compare_status=self._compare_status,
            analyze_options=self._analyze_options,
            judge_values=self._judge_values if judge is not None else None,
        )

    async def _generate(self) -> str:
        return self.base_yaml

    async def _test_fields(self, yaml_text, urls, fields):
        self.tested.append(tuple(fields))
        self.tested_urls.append((tuple(fields), tuple(urls)))
        product = (yaml.safe_load(yaml_text).get("adapter") or {}).get("product") or {}
        out = {}
        for key in fields:
            spec = product.get(key) if isinstance(product, dict) else None
            if isinstance(spec, dict) and spec.get("fallback_from") == "url" and spec.get("url_param"):
                # fallback_from=url 스펙이면 URL 쿼리에서 값을 파싱해 돌려준다 (런타임과 동형).
                from urllib.parse import parse_qs, urlparse
                param = spec["url_param"]
                out[key] = [
                    {"url": u, "value": parse_qs(urlparse(u).query).get(param, [""])[0], "ok": True}
                    for u in urls
                ]
                continue
            if key == "supplier_product_code" and self.code_from_name and key not in self._repaired:
                # 상품코드 선택자가 상품명 요소를 잡음 → 값이 상품명과 동일 (상품별로는 다름)
                out[key] = [
                    {"url": u, "value": _ok_entry(u, "raw_product_name")["value"], "ok": True}
                    for u in urls
                ]
                continue
            failing = key in self.fail_always or (key in self.fail_first and key not in self._repaired)
            entries = []
            for i, u in enumerate(urls):
                if failing:
                    entries.append(_fail_entry(u, key))
                elif key in self.bad_values and key not in self._repaired:
                    entries.append({"url": u, "value": self.bad_values[key].format(i=i), "ok": True})
                else:
                    entries.append(_ok_entry(u, key))
            out[key] = entries
        return out

    async def _repair_field(self, yaml_text, field, feedback):
        self.repair_calls.append(field.field_path)
        self.feedbacks.append(feedback)
        self._repaired.add(field.test_key)
        return yaml_text + f"\n# repaired {field.test_key} {len(self.repair_calls)}"

    async def _find_status_pair(self, urls):
        return self._status_pair

    async def _compare_status(self, yaml_text, available, soldout):
        if self._status_suggestion is None:
            raise AssertionError("compare_status should not be called when no pair")
        return self._status_suggestion

    async def _analyze_options(self, yaml_text, url):
        self.analyze_url = url
        return self._option_parser

    async def _judge_values(self, samples):
        self.judge_calls.append(dict(samples))
        return self._judge(samples)


def _probe(all_products=True, detail_html="", structured=None, detail_url=""):
    return SimpleNamespace(
        sample_products=[{"url": f"https://x.com/p/{i}"} for i in range(5)],
        categories=[{"name": "c", "url": "/c"}] if all_products else [],
        has_all_products=all_products,
        detail_html=detail_html,
        structured_data=structured or {},
        detail_page_url=detail_url,
    )


def _run(deps, *, all_products=True, detail_html="", structured=None, detail_url="", **kw):
    probe = _probe(all_products, detail_html, structured, detail_url)
    return asyncio.run(run_auto_adapter(probe, "몰", deps, **kw))


# ── (a) 1차 통과 → 재시도 없음 ──────────────────────────────────────────────
def test_first_pass_confirms_without_repair():
    deps = FakeDeps()
    result = _run(deps)
    assert deps.repair_calls == []
    assert result.unresolved_fields == []
    confirmed = {h.field_path for h in result.mapping_hints}
    assert confirmed == {
        "adapter.product.supplier_product_code",
        "adapter.product.raw_product_name",
        "adapter.product.supply_price",
        "adapter.product.origin",
        "adapter.product.main_image_url",
    }


# ── (b) 실패 → 재프롬프트 → 수렴 ────────────────────────────────────────────
def test_repair_converges_after_one_retry():
    deps = FakeDeps(fail_first=["supply_price"])
    result = _run(deps)
    assert deps.repair_calls == ["adapter.product.supply_price"]  # 정확히 1회
    assert "adapter.product.supply_price" not in result.unresolved_fields
    assert "adapter.product.supply_price" in {h.field_path for h in result.mapping_hints}


# ── (c) 상한까지 실패해도 그 필드만 미확정, 파이프라인 생존 ─────────────────
def test_field_hits_retry_cap_and_stays_unresolved():
    deps = FakeDeps(fail_always=["origin"])
    result = _run(deps)
    origin_repairs = [c for c in deps.repair_calls if c == "adapter.product.origin"]
    assert len(origin_repairs) == AUTO_FIELD_RETRY_CAP
    assert result.unresolved_fields == ["adapter.product.origin"]
    # 나머지 필드는 정상 확정되고 YAML 도 반환됨
    assert result.yaml_text
    assert "adapter.product.raw_product_name" in {h.field_path for h in result.mapping_hints}


# ── 판별력(distinctness): 모든 상품에서 동일 값 → 실패 + 값 인용 피드백 ─────
def test_identical_values_across_samples_fail_distinctness():
    footer = "통신판매업신고번호 : 2011 경기풍양 0091호"
    deps = FakeDeps(bad_values={"raw_product_name": footer})  # {i} 없음 → 전 샘플 동일
    result = _run(deps)
    assert deps.repair_calls == ["adapter.product.raw_product_name"]
    assert "adapter.product.raw_product_name" in {h.field_path for h in result.mapping_hints}
    assert any("동일한 값" in fb and footer in fb for fb in deps.feedbacks)


def test_legitimately_identical_origin_is_not_penalized():
    deps = FakeDeps()  # origin은 전 샘플 "국산" — 판별력 검사 제외 대상
    result = _run(deps)
    assert "adapter.product.origin" in {h.field_path for h in result.mapping_hints}


# ── 구조화 데이터 대조: og:title 불일치 → 실패, 일치 → 통과 ─────────────────
def test_structured_title_mismatch_fails_and_quotes_og_title():
    deps = FakeDeps(bad_values={"raw_product_name": "고객센터 안내 {i}"})
    result = _run(deps, structured={"og:title": "멋진 상품"}, detail_url="https://x.com/p/0")
    assert deps.repair_calls == ["adapter.product.raw_product_name"]
    assert any("og:title" in fb and "멋진 상품" in fb for fb in deps.feedbacks)
    assert "adapter.product.raw_product_name" in {h.field_path for h in result.mapping_hints}


def test_structured_title_match_passes_first_time():
    deps = FakeDeps()
    result = _run(deps, structured={"og:title": "멋진 상품"}, detail_url="https://x.com/p/0")
    assert deps.repair_calls == []
    assert "adapter.product.raw_product_name" in {h.field_path for h in result.mapping_hints}


def test_structured_price_mismatch_fails():
    deps = FakeDeps(bad_values={"supply_price": "9999"})
    result = _run(deps, structured={"jsonld:price": "12000"}, detail_url="https://x.com/p/0")
    assert "adapter.product.supply_price" in deps.repair_calls
    assert any("12000" in fb for fb in deps.feedbacks)
    assert "adapter.product.supply_price" in {h.field_path for h in result.mapping_hints}


# ── AI 값 검수(judge): 불합격 → 재시도 루프 + reason 피드백, 예외 → 통과 간주 ─
def test_judge_rejection_demotes_field_and_reason_reaches_feedback():
    state = {"first": True}

    def judge(samples):
        if "supply_price" in samples and state["first"]:
            state["first"] = False
            return {"supply_price": {"ok": False, "reason": "가격이 0으로 보임"}}
        return {key: {"ok": True, "reason": ""} for key in samples}

    deps = FakeDeps(judge=judge)
    result = _run(deps)
    assert deps.repair_calls == ["adapter.product.supply_price"]
    assert any("가격이 0으로 보임" in fb for fb in deps.feedbacks)
    # 재시도 후 다시 judge를 통과해야 확정 — 단일 필드 재검수 호출이 있었어야 함
    assert any(set(call) == {"supply_price"} for call in deps.judge_calls)
    assert "adapter.product.supply_price" in {h.field_path for h in result.mapping_hints}


def test_judge_exception_does_not_block_pipeline():
    def judge(samples):
        raise RuntimeError("LLM down")

    deps = FakeDeps(judge=judge)
    result = _run(deps)
    assert deps.repair_calls == []
    assert result.unresolved_fields == []
    assert len(result.mapping_hints) == 5


# ── supplier_status 위생: 1차 YAML에 있어도 무조건 제거 ─────────────────────
STATUS_YAML = BASE_YAML + """    supplier_status:
      selector: .soldout-banner
"""


def test_supplier_status_candidate_is_stripped_from_first_yaml():
    deps = FakeDeps(STATUS_YAML, status_pair=None)
    result = _run(deps)
    assert "supplier_status" not in result.yaml_text
    assert "supplier_status" not in {t for keys in deps.tested for t in keys}


# ── (d) 판매중/품절 쌍을 못 찾으면 조용히 스킵 ──────────────────────────────
def test_status_pair_not_found_skips_silently():
    deps = FakeDeps(status_pair=None, status_suggestion=None)
    result = _run(deps)
    assert result.status_pair is None
    assert "supplier_status" not in result.yaml_text  # 강제로 넣지 않음


def test_status_pair_found_applies_suggestion():
    deps = FakeDeps(
        status_pair=("https://x.com/p/0", "https://x.com/p/1"),
        status_suggestion={
            "selector": "", "fallback_from": "cart_button",
            "mapping": {}, "default": "available", "confidence": "high",
        },
    )
    result = _run(deps)
    assert result.status_pair == ("https://x.com/p/0", "https://x.com/p/1")
    assert "supplier_status" in result.yaml_text
    assert "cart_button" in result.yaml_text


# ── manual 필드: 후보도 없고 DOM 증거도 없으면 스킵 ─────────────────────────
def test_absent_manual_fields_without_dom_evidence_are_not_pursued():
    deps = FakeDeps()  # BASE_YAML 엔 옵션/이미지 필드 없음 + probe detail_html 비어 있음
    result = _run(deps)
    assert "adapter.options.groups.0.values_selector" not in result.unresolved_fields
    assert "adapter.product.detail_content" not in result.unresolved_fields
    assert "option_values" not in {t for keys in deps.tested for t in keys}


# ── 옵션 강제 추적: 후보 없어도 DOM 증거 있으면 추적, 실패 시 unresolved ────
OPTION_EVIDENCE_HTML = """
<select id="product_option_id1" name="option1">
  <option>- 옵션 선택 -</option>
  <option>빨강</option>
  <option>파랑</option>
</select>
"""


def test_option_evidence_forces_pursuit_without_candidate():
    deps = FakeDeps(fail_first=["option_values"])  # BASE_YAML 엔 옵션 후보 없음
    result = _run(deps, detail_html=OPTION_EVIDENCE_HTML)
    assert "adapter.options.groups.0.values_selector" in deps.repair_calls
    assert "adapter.options.groups.0.values_selector" not in result.unresolved_fields


def test_option_evidence_unresolved_when_cap_reached():
    deps = FakeDeps(fail_always=["option_values"])
    result = _run(deps, detail_html=OPTION_EVIDENCE_HTML)
    assert "adapter.options.groups.0.values_selector" in result.unresolved_fields  # 조용한 스킵 금지


def test_detect_option_evidence():
    assert detect_option_evidence(OPTION_EVIDENCE_HTML) is True
    assert detect_option_evidence("") is False
    assert detect_option_evidence("<select><option>- 필수 선택 -</option><option>빨강</option></select>") is False
    qty = "<select name='quantity'><option>1</option><option>2</option></select>"
    assert detect_option_evidence(qty) is False


# ── manual 필드: base 에 후보 있고 실패하면 미확정 + YAML 에서 스트립 ────────
OPTION_YAML = BASE_YAML + """  options:
    detection: dom
    groups:
    - name: 옵션
      values_selector: .opt
"""


def test_present_option_field_that_fails_is_stripped_and_unresolved():
    deps = FakeDeps(OPTION_YAML, fail_always=["option_values"])
    result = _run(deps)
    assert "adapter.options.groups.0.values_selector" in result.unresolved_fields
    parsed = yaml.safe_load(result.yaml_text)
    assert "groups" not in (parsed["adapter"].get("options") or {})


def test_confirmed_option_triggers_parser_analysis():
    parser = {"enabled": True, "pattern": "(?P<value>.+) (?P<price>\\d+)", "price_kind": "delta"}
    deps = FakeDeps(OPTION_YAML, option_parser=parser)
    result = _run(deps)
    assert "adapter.options.groups.0.values_selector" in {h.field_path for h in result.mapping_hints}
    parsed = yaml.safe_load(result.yaml_text)
    assert parsed["adapter"]["options"]["option_text_parser"]["pattern"] == parser["pattern"]


# ── 카테고리 자동 탐지 실패 시 사람에게 위임 ────────────────────────────────
def test_missing_categories_are_delegated_to_human():
    deps = FakeDeps()
    result = _run(deps, all_products=False)
    assert "adapter.categories.navigation.menu_selector" in result.unresolved_fields


# ── 구조화 이벤트 스트림: 방출 라인이 프로토콜 JSON으로 파싱되는지 ──────────
def test_progress_events_follow_protocol():
    lines: list[str] = []
    deps = FakeDeps(fail_first=["supply_price"])
    asyncio.run(run_auto_adapter(_probe(), "몰", deps, on_progress=lines.append))

    events = [json.loads(l[len("[event:"):-1]) for l in lines if l.startswith("[event:") and l.endswith("]")]
    assert events
    assert {e["kind"] for e in events} <= {"stage", "field", "visit", "shot", "note"}

    stages = [e for e in events if e["kind"] == "stage"]
    assert {e["stage"] for e in stages} >= {"generate", "verify", "status", "category", "finalize"}
    assert all(e["status"] in {"active", "done", "failed", "skipped"} for e in stages)

    fields = [e for e in events if e["kind"] == "field"]
    assert fields
    for e in fields:
        assert {"field", "key", "label", "status", "attempt", "cap", "value", "reason"} <= set(e)
        assert e["status"] in {"testing", "retry", "confirmed", "unresolved", "absent"}
        assert len(e["value"]) <= 80 and len(e["reason"]) <= 120
    assert any(e["status"] == "retry" and e["key"] == "supply_price" for e in fields)
    assert any(e["status"] == "confirmed" for e in fields)
    # 진행바용 [progress:x] 라인도 계속 방출된다
    assert any(l.startswith("[progress:") for l in lines)


# ── 상품코드 URL 파라미터 유도 (순수 헬퍼) ──────────────────────────────────
def test_derive_prefers_known_code_name():
    urls = [
        "https://x.com/shopdetail.html?branduid=712537&special=1&GfDT=aaa",
        "https://x.com/shopdetail.html?branduid=712999&special=1&GfDT=bbb",
        "https://x.com/shopdetail.html?branduid=713111&special=1&GfDT=ccc",
    ]
    assert derive_code_url_param(urls) == "branduid"  # special(전부 동일)·GfDT(트래킹)보다 우선


def test_derive_excludes_constant_param():
    urls = [f"https://x.com/d?special=1&code={i}" for i in range(3)]
    assert derive_code_url_param(urls) == "code"


def test_derive_numeric_when_no_known_name():
    urls = [f"https://x.com/d?token=zz{i}&seq={100 + i}" for i in range(3)]
    assert derive_code_url_param(urls) == "seq"  # 알려진 이름 없음 → 값이 전부 숫자인 seq


def test_derive_none_when_no_query():
    assert derive_code_url_param(["https://x.com/p/1", "https://x.com/p/2"]) is None
    assert derive_code_url_param([]) is None


# ── 오케스트레이터: 상품코드 실패 → URL 유도 성공 → repair 없이 확정 ────────
_CODE_URLS = [f"https://x.com/shopdetail.html?branduid=71{i}537" for i in range(3)]


def test_supplier_code_url_derivation_confirms_without_repair():
    deps = FakeDeps(fail_first=["supplier_product_code"])  # .code 선택자 1차 실패
    result = _run(deps, test_urls=_CODE_URLS)
    assert deps.repair_calls == []  # LLM repair 호출 없음
    assert "adapter.product.supplier_product_code" not in result.unresolved_fields
    parsed = yaml.safe_load(result.yaml_text)
    code = parsed["adapter"]["product"]["supplier_product_code"]
    assert code == {"fallback_from": "url", "url_param": "branduid"}


def test_supplier_code_falls_back_to_repair_when_no_url_param():
    deps = FakeDeps(fail_first=["supplier_product_code"])  # 쿼리 없는 URL → 유도 실패
    result = _run(deps)  # 기본 probe URL은 쿼리 없음
    assert deps.repair_calls == ["adapter.product.supplier_product_code"]
    assert "adapter.product.supplier_product_code" not in result.unresolved_fields


# ── 교차 필드 검사: 상품코드=상품명 → 실패 → URL 유도로 확정 (itopic 회귀) ──
def test_code_equals_name_fails_then_url_derivation_confirms():
    deps = FakeDeps(code_from_name=True)
    result = _run(deps, test_urls=_CODE_URLS)
    # 코드는 상품명과 동일하므로 교차검사에서 실패 → LLM repair 없이 URL 파라미터로 확정
    assert deps.repair_calls == []
    assert "adapter.product.supplier_product_code" not in result.unresolved_fields
    parsed = yaml.safe_load(result.yaml_text)
    assert parsed["adapter"]["product"]["supplier_product_code"] == {
        "fallback_from": "url", "url_param": "branduid",
    }
    disp = result.dispositions["adapter.product.supplier_product_code"]
    assert disp["state"] == "confirmed" and "branduid" in disp["reason"]


def test_code_equals_name_falls_back_to_repair_without_url_param():
    deps = FakeDeps(code_from_name=True)  # 쿼리 없는 기본 probe URL → URL 유도 불가
    result = _run(deps)
    assert deps.repair_calls == ["adapter.product.supplier_product_code"]
    assert "adapter.product.supplier_product_code" not in result.unresolved_fields


# ── 이미지 증거: img≥2 → 후보 없어도 추적, 없으면 absent ─────────────────────
DETAIL_IMAGE_HTML = "<div class='detail'><img src='/d/1.jpg'><img data-src='/d/2.jpg'></div>"


def test_detect_detail_image_evidence():
    assert detect_detail_image_evidence(DETAIL_IMAGE_HTML) is True
    assert detect_detail_image_evidence("<div><img src='/only.jpg'></div>") is False
    assert detect_detail_image_evidence("") is False


def test_image_evidence_forces_pursuit_without_candidate():
    deps = FakeDeps(fail_first=["detail_content", "extra_image_urls"])  # BASE_YAML엔 이미지 후보 없음
    result = _run(deps, detail_html=DETAIL_IMAGE_HTML)
    assert "adapter.product.detail_content" in deps.repair_calls
    assert "adapter.product.extra_image_urls" in deps.repair_calls
    assert "adapter.product.detail_content" not in result.unresolved_fields


def test_image_absent_without_evidence_is_marked_absent():
    deps = FakeDeps()  # 이미지 증거 없음
    result = _run(deps)
    disp = result.dispositions["adapter.product.detail_content"]
    assert disp["state"] == "absent"
    assert "detail_content" not in {t for keys in deps.tested for t in keys}


# ── dispositions: 각 상태가 올바른 reason과 함께 채워지는지 ──────────────────
def test_dispositions_cover_all_fields_with_states():
    deps = FakeDeps()
    result = _run(deps)
    d = result.dispositions
    # 핵심 상품필드 5종 confirmed
    for path in (
        "adapter.product.supplier_product_code", "adapter.product.raw_product_name",
        "adapter.product.supply_price", "adapter.product.origin", "adapter.product.main_image_url",
    ):
        assert d[path]["state"] == "confirmed" and d[path]["reason"]
    # 옵션 2종 + 이미지 2종 absent (후보/증거 없음)
    for path in (
        "adapter.options.groups.0.values_selector", "adapter.options.option_price_delta",
        "adapter.product.detail_content", "adapter.product.extra_image_urls",
    ):
        assert d[path]["state"] == "absent"
    # 판매상태: 품절 쌍 없음 → absent, 기본값 안내 reason
    assert d["adapter.product.supplier_status"]["state"] == "absent"
    assert "판매중" in d["adapter.product.supplier_status"]["reason"]


def test_disposition_unresolved_carries_failure_reason():
    deps = FakeDeps(fail_always=["origin"])
    result = _run(deps)
    disp = result.dispositions["adapter.product.origin"]
    assert disp["state"] == "unresolved" and disp["reason"]


def test_disposition_status_confirmed_when_pair_found():
    deps = FakeDeps(
        status_pair=("https://x.com/p/0", "https://x.com/p/1"),
        status_suggestion={
            "selector": "", "fallback_from": "cart_button",
            "mapping": {}, "default": "available", "confidence": "high",
        },
    )
    result = _run(deps)
    assert result.dispositions["adapter.product.supplier_status"]["state"] == "confirmed"


# ── option_url 배선: 옵션 필드만 option_test_urls로, 나머지는 기존 urls ────────
_OPT_URLS = ["https://x.com/opt/withoptions"]


def test_option_url_routes_only_option_fields_to_option_urls():
    deps = FakeDeps(OPTION_YAML)  # 옵션 후보 있음 → 확정 경로
    result = _run(deps, option_dom=OPTION_EVIDENCE_HTML, option_test_urls=_OPT_URLS)
    for fields, urls in deps.tested_urls:
        if "option_values" in fields or "option_prices" in fields:
            assert list(urls) == _OPT_URLS          # 옵션 필드는 옵션 URL로 검증
            assert "option_values" not in fields or set(fields) <= {"option_values", "option_prices"}
        else:
            assert _OPT_URLS[0] not in urls          # 다른 필드는 옵션 URL 미사용
    # 옵션 파서 분석도 옵션 URL 기준
    assert deps.analyze_url == _OPT_URLS[0]
    assert "adapter.options.groups.0.values_selector" in {h.field_path for h in result.mapping_hints}


def test_option_dom_drives_evidence_not_detail_html():
    # detail_html 비어 있어도 option_dom에 select 증거가 있으면 옵션 추적을 강제한다.
    deps = FakeDeps(fail_first=["option_values"])
    result = _run(deps, detail_html="", option_dom=OPTION_EVIDENCE_HTML, option_test_urls=_OPT_URLS)
    assert "adapter.options.groups.0.values_selector" in deps.repair_calls
    assert "adapter.options.groups.0.values_selector" not in result.unresolved_fields
    # 옵션 필드 재검증도 옵션 URL로
    opt_calls = [urls for fields, urls in deps.tested_urls if "option_values" in fields]
    assert opt_calls and all(list(u) == _OPT_URLS for u in opt_calls)


def test_no_option_url_keeps_single_batch_and_default_urls():
    deps = FakeDeps(OPTION_YAML)  # option_test_urls 미지정 → 기존 동작
    _run(deps)
    # 옵션 필드가 다른 필드와 같은 배치(단일 test_fields 호출)에 포함된다
    assert any("option_values" in fields and "raw_product_name" in fields for fields in deps.tested)
    assert deps.analyze_url == "https://x.com/p/0"  # 기존 urls[0]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
