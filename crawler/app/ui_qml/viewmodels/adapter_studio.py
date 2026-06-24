from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Callable, Mapping
from typing import Any

import yaml
from PySide6.QtCore import QObject, Property, QElapsedTimer, QTimer, Signal, Slot

from app.analyzer.adapter_schema import FIELD_LABELS_KO, get_product_field_mappings
from app.analyzer.element_picker import suggest_defaults_for_field
from app.analyzer.mapping_hints import MappingHint, apply_locked_hints_to_yaml_dict
from app.analyzer.validation_summary import build_validation_summary, get_save_gate_decision
from app.config import load_config
from app.credentials.store import load_supplier_credentials, save_supplier_credentials
from app.crawlers.registry import load_adapter_from_text, save_adapter
from app.ui_qml.models.list_model import ListModel
from app.ui_qml.viewmodels.base import BaseViewModel, sanitize_diagnostic
from app.workers.adapter import (
    AdapterTestRequest, AdapterTestWorker, GenerateRequest, GenerateWorker,
    PickerRequest, PickerWorker, ProbeRequest, ProbeWorker,
)


MAPPING_ROLES = ("key", "label", "selector", "attribute", "transform", "status", "testValue", "testOk")
_SHUTDOWN_WORKERS: list[object] = []


def yaml_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "", value.lower().replace(" ", "-"))


def studio_credential_key(name: str, main_url: str) -> str:
    normalized_name = unicodedata.normalize("NFKC", name).strip().casefold()
    normalized_url = unicodedata.normalize("NFKC", main_url).strip().casefold()
    readable = _slugify(normalized_name) or "supplier"
    digest = hashlib.sha256(f"{normalized_name}\n{normalized_url}".encode("utf-8")).hexdigest()[:16]
    return f"studio-{readable[:40]}-{digest}"


class AdapterStudioViewModel(BaseViewModel):
    stateChanged = Signal()

    def __init__(self, parent: QObject | None = None, *, app_view_model=None,
                 worker_factories: Mapping[str, Callable[..., object]] | None = None) -> None:
        super().__init__(parent)
        self._app = app_view_model
        self._factories = {
            "probe": ProbeWorker, "generate": GenerateWorker,
            "picker": PickerWorker, "test": AdapterTestWorker,
            **dict(worker_factories or {}),
        }
        self._current_stage = 0
        self._yaml_text = ""
        self._yaml_dirty = False
        self._validated_hash: str | None = None
        self._validation_stale = True
        self._validation_summary = None
        self._save_warning: dict[str, Any] = {}
        self._warning_ack: tuple[str, str] | None = None
        self._mapping_rows = ListModel(MAPPING_ROLES, parent=self)
        self._probe_result = None
        self._probe_summary: dict[str, Any] = {}
        self._advanced_editor_open = False
        self._busy = False
        self._worker = None
        self._retired_workers: list[object] = []
        self._operation_id = 0
        self._cancelled_operations: set[int] = set()
        self._shutting_down = False
        self._pending_hint = None
        self._mapping_hints: list[MappingHint] = []
        self._inputs = {
            "supplierName": "", "mainUrl": "", "listingUrl": "", "detailUrl": "",
            "needsLogin": False, "loginUrl": "", "username": "", "password": "",
        }

    currentStage = Property(int, lambda self: self._current_stage, notify=stateChanged)
    yamlText = Property(str, lambda self: self._yaml_text, notify=stateChanged)
    yamlDirty = Property(bool, lambda self: self._yaml_dirty, notify=stateChanged)
    validationStale = Property(bool, lambda self: self._validation_stale, notify=stateChanged)
    validationSummary = Property("QVariantMap", lambda self: self._summary_map(), notify=stateChanged)
    mappingRows = Property(QObject, lambda self: self._mapping_rows, constant=True)
    probeSummary = Property("QVariantMap", lambda self: dict(self._probe_summary), notify=stateChanged)
    canSave = Property(bool, lambda self: self._can_save(), notify=stateChanged)
    saveWarning = Property("QVariantMap", lambda self: dict(self._save_warning), notify=stateChanged)
    advancedEditorOpen = Property(bool, lambda self: self._advanced_editor_open, notify=stateChanged)
    busy = Property(bool, lambda self: self._busy, notify=stateChanged)
    connectionInputs = Property("QVariantMap", lambda self: {k: v for k, v in self._inputs.items() if k not in {"username", "password"}}, notify=stateChanged)

    def _emit(self) -> None:
        self.stateChanged.emit()
        self.changed.emit()

    def _summary_map(self) -> dict[str, Any]:
        summary = self._validation_summary
        if summary is None:
            return {"hasValidation": False, "message": "검증이 필요합니다."}
        return {
            "hasValidation": summary.has_validation,
            "totalSamples": summary.total_samples,
            "failedKeyFields": list(summary.failed_key_fields),
            "warningFields": list(summary.warning_fields),
            "passed": summary.can_save_cleanly,
            "message": "검증 통과" if summary.can_save_cleanly else "필수 필드 검증 실패",
        }

    def _can_save(self) -> bool:
        if not self._yaml_text:
            return False
        try:
            load_adapter_from_text(self._yaml_text)
        except Exception:
            return False
        decision = get_save_gate_decision(self._validation_summary, self._validation_stale)
        if not decision.should_warn:
            return True
        return decision.allow_continue and self._warning_ack == (yaml_content_hash(self._yaml_text), decision.reason)

    def _clear_save_warning(self) -> None:
        self._save_warning = {}
        self._warning_ack = None

    @Slot(int)
    def setCurrentStage(self, stage: int) -> None:
        stage = max(0, min(3, int(stage)))
        if stage != self._current_stage:
            self._current_stage = stage
            self._emit()

    @Slot("QVariantMap")
    def setConnectionInputs(self, values: Mapping[str, Any]) -> None:
        for key in ("supplierName", "mainUrl", "listingUrl", "detailUrl", "needsLogin"):
            if key in values:
                self._inputs[key] = values[key]
        self._emit()

    @Slot("QVariantMap")
    def setLoginInputs(self, values: Mapping[str, Any]) -> None:
        for key in ("loginUrl", "username", "password"):
            if key in values:
                self._inputs[key] = str(values[key] or "")
        self._emit()

    @Slot(bool)
    def setAdvancedEditorOpen(self, open_: bool) -> None:
        self._advanced_editor_open = bool(open_)
        self._emit()

    def _task_start(self, key: str, label: str, stage: str) -> None:
        self._busy = True
        if self._app:
            self._app.start_task(key, label)
            self._app.update_task(stage)
        self._emit()

    def _can_start_operation(self) -> bool:
        return not self._shutting_down and not self._busy and self._worker is None

    def _connect_worker(self, worker, *, finished, key: str, label: str, stage: str) -> bool:
        if not self._can_start_operation():
            return False
        self._operation_id += 1
        operation_id = self._operation_id
        self._worker = worker
        worker.finished.connect(lambda *args: self._dispatch_finished(operation_id, finished, *args))
        worker.error.connect(lambda message: self._dispatch_error(operation_id, message))
        if hasattr(worker, "cancelled"):
            worker.cancelled.connect(lambda: self._dispatch_cancelled(operation_id))
        if hasattr(worker, "progress"):
            worker.progress.connect(lambda message: self._dispatch_progress(operation_id, stage, message))
        self._task_start(key, label, stage)
        worker.start()
        return True

    def _operation_is_current(self, operation_id: int) -> bool:
        return operation_id == self._operation_id and operation_id not in self._cancelled_operations

    def _dispatch_finished(self, operation_id: int, callback, *args) -> None:
        if self._operation_is_current(operation_id):
            callback(*args)

    def _dispatch_error(self, operation_id: int, message: str) -> None:
        if self._operation_is_current(operation_id):
            self._operation_error(message)

    def _dispatch_cancelled(self, operation_id: int) -> None:
        if self._operation_is_current(operation_id):
            self._cancel("작업 취소됨")

    def _dispatch_progress(self, operation_id: int, stage: str, message: str) -> None:
        if self._operation_is_current(operation_id):
            self._task_progress(stage, message)

    def _task_progress(self, stage: str, message: str) -> None:
        if self._app:
            self._app.update_task(stage, -1.0, sanitize_diagnostic(message))

    def _operation_done(self) -> None:
        self._busy = False
        self._retire_current_worker()
        if self._app:
            self._app.complete_task()
        self._emit()

    def _operation_error(self, message: str) -> None:
        self._busy = False
        self._retire_current_worker()
        self.set_field_errors({"form": sanitize_diagnostic(message)})
        if self._app:
            self._app.fail_task(sanitize_diagnostic(message))
        self._emit()

    def _retire_current_worker(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is None:
            return
        self._retired_workers.append(worker)
        self._cleanup_retired_workers()

    def _cleanup_retired_workers(self) -> None:
        self._retired_workers = [
            worker for worker in self._retired_workers
            if not hasattr(worker, "isRunning") or worker.isRunning()
        ]
        if self._retired_workers:
            QTimer.singleShot(25, self._cleanup_retired_workers)

    @Slot()
    def probe(self) -> bool:
        if not self._can_start_operation():
            return False
        name = str(self._inputs["supplierName"]).strip()
        url = str(self._inputs["mainUrl"]).strip()
        errors = {}
        if not name:
            errors["supplierName"] = "도매처명을 입력하세요."
        if not url:
            errors["mainUrl"] = "URL을 입력하세요."
        elif not url.startswith(("http://", "https://")):
            errors["mainUrl"] = "URL은 http:// 또는 https://로 시작해야 합니다."
        if errors:
            self.set_field_errors(errors)
            return False
        credentials = (self._inputs["loginUrl"], self._inputs["username"], self._inputs["password"])
        if self._inputs["needsLogin"] and all(credentials):
            try:
                save_supplier_credentials(self._credential_key(), str(credentials[1]), str(credentials[2]))
            except Exception as exc:
                self._inputs["username"] = self._inputs["password"] = ""
                self.set_field_errors({"form": f"로그인 정보 저장 실패: {sanitize_diagnostic(exc)}"})
                return False
        request = ProbeRequest(
            url, self._inputs["listingUrl"] or None, self._inputs["detailUrl"] or None,
            *(credentials if self._inputs["needsLogin"] else (None, None, None)),
        )
        worker = self._factories["probe"](request)
        self._inputs["username"] = self._inputs["password"] = ""
        self.set_field_errors({})
        return self._connect_worker(
            worker, finished=self._probe_finished, key="adapter-probe",
            label="사이트 분석", stage="analyze",
        )

    def _probe_finished(self, result) -> None:
        self._probe_result = result
        self._probe_summary = {
            "finalUrl": result.final_url, "encoding": result.encoding,
            "needsLogin": result.needs_login, "categoryCount": len(result.categories or []),
            "sampleProducts": list(result.sample_products or []),
            "hasAllProducts": result.has_all_products,
        }
        self._current_stage = 1
        self._operation_done()

    @Slot()
    def cancelProbe(self) -> None:
        self._cancel("사이트 분석 취소")

    @Slot()
    def generate(self) -> bool:
        if not self._can_start_operation():
            return False
        if self._probe_result is None:
            self.set_field_errors({"form": "먼저 사이트 분석을 실행하세요."})
            return False
        config = load_config()
        worker = self._factories["generate"](GenerateRequest(
            self._probe_result, str(self._inputs["supplierName"]), config.llm_provider,
            config.auto_fallback_enabled, list(self._mapping_hints),
        ))
        return self._connect_worker(
            worker, finished=lambda text, *_: self._generated(text),
            key="adapter-generate", label="수집 설정 생성", stage="generate",
        )

    def _generated(self, text: str) -> None:
        self.acceptGeneratedYaml(text)
        self._operation_done()

    @Slot()
    def cancelGenerate(self) -> None:
        self._cancel("설정 생성 취소")

    def _cancel(self, message: str) -> None:
        operation_id = self._operation_id
        self._cancelled_operations.add(operation_id)
        if self._worker is not None and hasattr(self._worker, "requestInterruption"):
            self._worker.requestInterruption()
        self._retire_current_worker()
        self._busy = False
        if self._app:
            self._app.cancel_task(message)
        self._emit()

    @Slot(str)
    def acceptGeneratedYaml(self, text: str) -> None:
        self._yaml_text = str(text)
        self._yaml_dirty = True
        self._validated_hash = None
        self._validation_summary = None
        self._validation_stale = True
        self._clear_save_warning()
        self._current_stage = 2
        self._refresh_mapping_rows()
        self._emit()

    @Slot(str)
    def setYamlText(self, text: str) -> None:
        if text == self._yaml_text:
            return
        self._yaml_text = str(text)
        self._yaml_dirty = True
        self._validation_stale = self._validated_hash != yaml_content_hash(self._yaml_text)
        self._clear_save_warning()
        self._refresh_mapping_rows()
        self._emit()

    def _refresh_mapping_rows(self) -> None:
        try:
            rows = get_product_field_mappings(load_adapter_from_text(self._yaml_text))
        except Exception:
            rows = []
        self._mapping_rows.resetRows([{**row, "testValue": "", "testOk": False} for row in rows])

    @Slot(result=str)
    def beginValidation(self) -> str:
        return yaml_content_hash(self._yaml_text)

    @Slot("QVariantMap", str)
    def acceptValidation(self, raw_results: Mapping[str, Any], tested_yaml_hash: str) -> None:
        self._validation_summary = build_validation_summary(dict(raw_results))
        self._validated_hash = str(tested_yaml_hash)
        self._validation_stale = yaml_content_hash(self._yaml_text) != self._validated_hash
        self._clear_save_warning()
        self._current_stage = 3
        self._apply_test_results(raw_results)
        self._emit()

    def _apply_test_results(self, raw_results: Mapping[str, Any]) -> None:
        try:
            rows = get_product_field_mappings(load_adapter_from_text(self._yaml_text))
        except Exception:
            return
        updated = []
        for row in rows:
            entries = raw_results.get(row["key"], [])
            hits = [entry.get("value") for entry in entries if entry.get("value")]
            updated.append({**row, "testValue": str(hits[0])[:100] if hits else "", "testOk": bool(hits)})
        self._mapping_rows.resetRows(updated)

    @Slot(str)
    def testSingle(self, field_key: str) -> bool:
        return self._start_test([field_key])

    @Slot()
    def testAll(self) -> bool:
        return self._start_test(None)

    def _start_test(self, fields: list[str] | None) -> bool:
        if not self._can_start_operation():
            return False
        try:
            load_adapter_from_text(self._yaml_text)
        except Exception as exc:
            self.set_field_errors({"yamlText": f"YAML 오류: {exc}"})
            return False
        urls = [str(item.get("url")) for item in self._probe_summary.get("sampleProducts", []) if item.get("url")]
        if not urls:
            detail = str(self._inputs["detailUrl"] or "").strip()
            urls = [detail] if detail else []
        if not urls:
            self.set_field_errors({"form": "테스트할 상품 URL이 없습니다."})
            return False
        tested_hash = self.beginValidation()
        username = password = None
        if self._inputs["needsLogin"]:
            loaded = self._load_transient_credentials()
            if loaded:
                username, password = loaded
        request = AdapterTestRequest(
            self._yaml_text, urls[:3], tested_hash, self._inputs["loginUrl"] or None,
            username, password, tuple(fields) if fields else None,
        )
        worker = self._factories["test"](request)
        self._inputs["username"] = self._inputs["password"] = ""
        return self._connect_worker(
            worker, finished=lambda result: self._test_finished(result, tested_hash),
            key="adapter-test", label="필드 검증", stage="validate",
        )

    def _test_finished(self, result: dict, tested_hash: str) -> None:
        raw = dict(result).get("__raw_results__", {})
        self.acceptValidation(raw, tested_hash)
        self._operation_done()

    @Slot(str)
    def pickElement(self, field_path: str) -> bool:
        if not self._can_start_operation():
            return False
        target = str(self._inputs["detailUrl"] or self._inputs["mainUrl"])
        username = password = None
        if self._inputs["needsLogin"]:
            loaded = self._load_transient_credentials()
            if loaded:
                username, password = loaded
        worker = self._factories["picker"](PickerRequest(
            field_path, target, self._inputs["loginUrl"] or None, username, password,
            self._adapter_login_config(),
        ))
        return self._connect_worker(
            worker, finished=self._picked, key="adapter-pick",
            label="요소 선택", stage="map",
        )

    def _load_transient_credentials(self) -> tuple[str, str] | None:
        try:
            return load_supplier_credentials(self._credential_key())
        except Exception as exc:
            self.set_field_errors({"form": f"로그인 정보 불러오기 실패: {sanitize_diagnostic(exc)}"})
            return None

    def _credential_key(self) -> str:
        return studio_credential_key(
            str(self._inputs["supplierName"]), str(self._inputs["mainUrl"])
        )

    @Slot()
    def shutdown(self) -> None:
        self._shutting_down = True
        if self._worker is not None:
            worker = self._worker
            self._worker = None
            if worker not in self._retired_workers:
                self._retired_workers.append(worker)
        workers = list(dict.fromkeys(self._retired_workers))
        for worker in workers:
            if hasattr(worker, "requestInterruption"):
                worker.requestInterruption()
            self._clear_worker_secret(worker)
        timer = QElapsedTimer()
        timer.start()
        for worker in workers:
            if hasattr(worker, "isRunning") and worker.isRunning() and hasattr(worker, "wait"):
                remaining = max(0, 500 - timer.elapsed())
                worker.wait(remaining)
        self._retired_workers = [
            worker for worker in workers
            if not hasattr(worker, "isRunning") or worker.isRunning()
        ]
        for worker in self._retired_workers:
            if worker not in _SHUTDOWN_WORKERS:
                _SHUTDOWN_WORKERS.append(worker)
        self._busy = False
        self._emit()

    @staticmethod
    def _clear_worker_secret(worker) -> None:
        request = getattr(worker, "request", None)
        if request is None and getattr(worker, "args", None):
            request = worker.args[0]
        if request is not None and hasattr(request, "password"):
            request.password = None

    def _adapter_login_config(self) -> dict[str, str] | None:
        try:
            login = load_adapter_from_text(self._yaml_text).adapter.login
            config: dict[str, str] = {}
            if login.login_url:
                config["login_url"] = login.login_url
            if login.fields:
                config["id_selector"] = login.fields.id
                config["password_selector"] = login.fields.password
            if login.submit:
                config["submit_selector"] = login.submit
            if login.success_indicator:
                config["success_indicator"] = login.success_indicator
            return config or None
        except Exception:
            return None

    @Slot()
    def pickAllProducts(self) -> bool:
        return self.pickElement("adapter.categories.all_products.url")

    def _picked(self, picked, field_path: str) -> None:
        self._pending_hint = (picked, field_path)
        self._operation_done()

    @Slot()
    def acceptPickedHint(self) -> bool:
        if not self._pending_hint:
            return False
        picked, field_path = self._pending_hint
        defaults = suggest_defaults_for_field(field_path, picked)
        hint = MappingHint(
            page_kind="listing" if "listing" in field_path or "all_products" in field_path else "detail",
            field_path=field_path, chosen_selector=defaults.pop("selector"), url=picked.url,
            selector_candidates=list(picked.selector_candidates), **defaults,
        )
        self._mapping_hints.append(hint)
        if self._yaml_text:
            try:
                raw = yaml.safe_load(self._yaml_text)
                apply_locked_hints_to_yaml_dict(raw, [hint])
                self.setYamlText(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))
            except Exception as exc:
                self.set_field_errors({"yamlText": f"YAML 오류: {exc}"})
                return False
        self._pending_hint = None
        self._emit()
        return True

    @Slot(result=bool)
    def save(self) -> bool:
        try:
            load_adapter_from_text(self._yaml_text)
        except Exception as exc:
            self.set_field_errors({"yamlText": f"YAML 오류: {exc}"})
            return False
        if not self._can_save():
            decision = get_save_gate_decision(self._validation_summary, self._validation_stale)
            self._save_warning = {
                "reason": decision.reason, "message": decision.message,
                "failedFields": list(decision.failed_fields),
                "allowContinue": decision.allow_continue,
            }
            self.set_field_errors({})
            self._emit()
            return False
        slug = _slugify(str(self._inputs["supplierName"]).strip())
        if not slug:
            self.set_field_errors({"supplierName": "저장할 영문 도매처명을 입력하세요."})
            return False
        try:
            save_adapter(slug, self._yaml_text)
        except Exception as exc:
            self.set_field_errors({"form": f"저장 실패: {sanitize_diagnostic(exc)}"})
            return False
        self._yaml_dirty = False
        self.set_field_errors({})
        self._emit()
        return True

    @Slot()
    def acknowledgeSaveWarning(self) -> None:
        decision = get_save_gate_decision(self._validation_summary, self._validation_stale)
        if decision.should_warn and decision.allow_continue:
            self._warning_ack = (yaml_content_hash(self._yaml_text), decision.reason)
            self._save_warning = {}
            self._emit()
