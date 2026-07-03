from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal


KEY_FIELDS = ("raw_product_name", "supply_price", "main_image_url")
WARNING_FIELDS = ("supplier_status", "origin", "detail_content", "extra_image_urls")


@dataclass
class FieldValidation:
    field: str
    passed: int
    total: int
    ok: bool


@dataclass
class ValidationSummary:
    has_validation: bool
    total_samples: int = 0
    field_results: dict[str, FieldValidation] = field(default_factory=dict)
    failed_key_fields: list[str] = field(default_factory=list)
    warning_fields: list[str] = field(default_factory=list)

    @property
    def can_save_cleanly(self) -> bool:
        return self.has_validation and not self.failed_key_fields


@dataclass
class SaveGateDecision:
    should_warn: bool
    reason: Literal["none", "missing", "stale", "failed"]
    message: str
    failed_fields: list[str] = field(default_factory=list)
    allow_continue: bool = True


def _threshold(total: int) -> int:
    if total <= 1:
        return 1
    return 2 if total <= 3 else max(1, int(total * 0.67 + 0.999))


def _value(entry: dict[str, Any]) -> str:
    return str(entry.get("value") or "").strip()


def _origin_value_ok(value: str) -> bool:
    if not value:
        return False
    compact = re.sub(r"\s+", " ", value).strip()
    if len(compact) > 30:
        return False
    return not re.search(r"판매가|공급가|배송비|상품코드|상품명|대표\s*이미지|옵션", compact)


def is_field_value_ok(field: str, entry: dict[str, Any]) -> bool:
    value = _value(entry)
    if field == "raw_product_name":
        return bool(value) and value != "이름 없음"
    if field == "supply_price":
        return bool(re.search(r"\d", value.replace(",", "")))
    if field == "main_image_url":
        return bool(value) and ("/" in value or "." in value or value.startswith("data:"))
    if field in ("detail_content", "extra_image_urls") and "imageCount" in entry:
        return int(entry.get("imageCount") or 0) > 0
    if field == "origin":
        return _origin_value_ok(value)
    if field in ("supplier_product_code", "supplier_product_id"):
        url = str(entry.get("url") or "").strip()
        return bool(value) and value != url and not value.startswith("http://") and not value.startswith("https://")
    return bool(value) or bool(entry.get("ok"))


def _field_validation(field: str, entries: list[dict[str, Any]]) -> FieldValidation:
    total = len(entries)
    passed = sum(1 for entry in entries if is_field_value_ok(field, entry))
    return FieldValidation(field=field, passed=passed, total=total, ok=total > 0 and passed >= _threshold(total))


def build_validation_summary(raw_results: dict[str, list[dict[str, Any]]] | None) -> ValidationSummary:
    if not raw_results:
        return ValidationSummary(has_validation=False)

    total_samples = max((len(entries) for entries in raw_results.values() if isinstance(entries, list)), default=0)
    if total_samples == 0:
        return ValidationSummary(has_validation=False)

    field_results: dict[str, FieldValidation] = {}
    for field, entries in raw_results.items():
        if isinstance(entries, list):
            field_results[field] = _field_validation(field, entries)

    failed: list[str] = [field for field in KEY_FIELDS if not field_results.get(field, FieldValidation(field, 0, total_samples, False)).ok]
    code_ok = field_results.get("supplier_product_code", FieldValidation("supplier_product_code", 0, total_samples, False)).ok
    if not code_ok:
        failed.append("supplier_product_code")

    warnings = [field for field in WARNING_FIELDS if field in field_results and not field_results[field].ok]
    return ValidationSummary(True, total_samples, field_results, failed, warnings)


def get_save_gate_decision(summary: ValidationSummary | None, is_stale: bool) -> SaveGateDecision:
    if summary is None or not summary.has_validation:
        return SaveGateDecision(True, "missing", "저장 전 샘플 상품 테스트를 실행하지 않았습니다.")
    if is_stale:
        return SaveGateDecision(True, "stale", "현재 YAML은 테스트 후 변경되었습니다.")
    if summary.failed_key_fields:
        return SaveGateDecision(True, "failed", "필수 필드 검증에 실패했습니다.", summary.failed_key_fields)
    return SaveGateDecision(False, "none", "검증 통과")
