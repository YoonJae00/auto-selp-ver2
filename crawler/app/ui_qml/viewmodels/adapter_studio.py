from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any

import yaml
from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot

from app.analyzer.adapter_schema import (
    FIELD_LABELS_KO,
    OPTION_PRICES_FIELD_PATH,
    OPTION_PRICES_ROW_KEY,
    OPTION_VALUES_FIELD_PATH,
    OPTION_VALUES_ROW_KEY,
    get_product_field_mappings,
)
from app.analyzer.element_picker import suggest_defaults_for_field
from app.analyzer.mapping_hints import MappingHint, apply_locked_hints_to_yaml_dict
from app.analyzer.validation_summary import (
    build_validation_summary,
    get_save_gate_decision,
    is_field_value_ok,
)
from app.config import load_config
from app.analyzer.session_store import clear_session_state, save_session_state
from app.credentials.store import (
    delete_supplier_credentials,
    load_supplier_credentials,
    save_supplier_credentials,
)
from app.crawlers.registry import load_adapter_from_text, save_adapter
from app.ui_qml.models.list_model import ListModel
from app.ui_qml.viewmodels.base import BaseViewModel, sanitize_diagnostic
from app.workers.adapter import (
    AdapterTestRequest, AdapterTestWorker, CategoryMenuProbeRequest, CategoryMenuProbeWorker,
    GenerateRequest, GenerateWorker,
    MappingPreviewJob, MappingPreviewRequest,
    PickerJob, PickerRequest, PickerValidateRequest, PickerValidateWorker,
    PickerWorker, ProbeRequest, ProbeWorker,
    SoldoutCompareRequest, SoldoutCompareWorker,
    close_picker_session, stop_picker_thread,
)
from app.workers.lifecycle import stop_workers


MAPPING_ROLES = (
    "key", "label", "fieldPath", "selector", "attribute", "transform", "status",
    "testValue", "testOk", "urlPattern", "urlParam", "urlAllowed", "testable", "extraEnabled",
)
IMAGE_PICKER_FIELD_PATHS = {"adapter.product.detail_content", "adapter.product.extra_image_urls"}


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
            "picker": PickerJob, "test": AdapterTestWorker,
            "picker_validate": PickerValidateWorker,
            "category_probe": CategoryMenuProbeWorker,
            "soldout_compare": SoldoutCompareWorker,
            **dict(worker_factories or {}),
        }
        self._current_stage = 0
        self._yaml_text = ""
        self._yaml_dirty = False
        self._validated_hash: str | None = None
        self._validation_stale = True
        self._validation_summary = None
        self._validation_raw: dict[str, list[dict]] = {}
        self._extra_test_urls: list[str] = []
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
        self._task_owner: object | None = None
        self._cancelled_operations: set[int] = set()
        self._shutting_down = False
        self._active_credential_key: str | None = None
        self._active_credential_identity: tuple[str, str, str, bool] | None = None
        self._active_credential_is_studio = False
        self._active_credentials: tuple[str, str] | None = None
        self._pending_hint = None
        self._picker_active = False
        self._picker_field_label = ""
        self._picker_field_hint = ""
        self._picker_field_path = ""
        self._picker_session_open = False
        self._has_pending_hint = False
        self._pending_hint_preview = ""
        self._picker_validation_active = False
        self._picker_validation_confidence = ""
        self._picker_validation_note = ""
        self._picker_validation_selector = ""
        self._pending_validation: dict[str, Any] | None = None
        self._excluded_urls: set[str] = set()
        self._category_analysis_ready = False
        self._category_analysis_message = "사이트 분석 후 카테고리 메뉴를 확인하세요."
        self._current_progress = -1.0
        self._current_progress_label = ""
        self._mapping_hints: list[MappingHint] = []
        self._needs_mapping_login = False
        self._manual_login_pending = False
        self._preview_active = False
        self._auto_preview_token = 0
        self._soldout_url = ""
        self._soldout_suggestion: dict[str, Any] = {}
        self._soldout_compare_open = False
        self._inputs = {
            "supplierName": "", "mainUrl": "", "listingUrl": "", "detailUrl": "",
            "needsLogin": False, "loginUrl": "", "username": "", "password": "",
        }

    currentStage = Property(int, lambda self: self._current_stage, notify=stateChanged)
    yamlText = Property(str, lambda self: self._yaml_text, notify=stateChanged)
    yamlDirty = Property(bool, lambda self: self._yaml_dirty, notify=stateChanged)
    validationStale = Property(bool, lambda self: self._validation_stale, notify=stateChanged)
    validationSummary = Property("QVariantMap", lambda self: self._summary_map(), notify=stateChanged)
    validationProducts = Property("QVariantList", lambda self: self._build_validation_products(), notify=stateChanged)
    testUrls = Property("QVariantList", lambda self: self._available_test_urls(), notify=stateChanged)
    needsMoreTestUrls = Property(bool, lambda self: len(self._available_test_urls()) < 3, notify=stateChanged)
    mappingRows = Property(QObject, lambda self: self._mapping_rows, constant=True)
    probeSummary = Property("QVariantMap", lambda self: self._probe_summary_with_checks(), notify=stateChanged)
    allProductsAutoDetected = Property(bool, lambda self: bool(self._probe_summary.get("hasAllProducts")), notify=stateChanged)
    canSave = Property(bool, lambda self: self._can_save(), notify=stateChanged)
    saveWarning = Property("QVariantMap", lambda self: dict(self._save_warning), notify=stateChanged)
    advancedEditorOpen = Property(bool, lambda self: self._advanced_editor_open, notify=stateChanged)
    busy = Property(bool, lambda self: self._busy, notify=stateChanged)
    currentProgress = Property(float, lambda self: self._current_progress, notify=stateChanged)
    currentProgressLabel = Property(str, lambda self: self._current_progress_label, notify=stateChanged)
    connectionInputs = Property("QVariantMap", lambda self: {k: v for k, v in self._inputs.items() if k not in {"username", "password"}}, notify=stateChanged)
    previewActive = Property(bool, lambda self: self._preview_active, notify=stateChanged)
    pickerActive = Property(bool, lambda self: self._picker_active, notify=stateChanged)
    pickerFieldLabel = Property(str, lambda self: self._picker_field_label, notify=stateChanged)
    pickerFieldPath = Property(str, lambda self: self._picker_field_path, notify=stateChanged)
    pickerFieldHint = Property(str, lambda self: self._picker_field_hint, notify=stateChanged)
    pickerSessionOpen = Property(bool, lambda self: self._picker_session_open, notify=stateChanged)
    hasPendingHint = Property(bool, lambda self: self._has_pending_hint, notify=stateChanged)
    pendingHintPreview = Property(str, lambda self: self._pending_hint_preview, notify=stateChanged)
    needsMappingLogin = Property(bool, lambda self: self._needs_mapping_login, notify=stateChanged)
    manualLoginPending = Property(bool, lambda self: self._manual_login_pending, notify=stateChanged)
    pickerValidationActive = Property(bool, lambda self: self._picker_validation_active, notify=stateChanged)
    pickerValidationConfidence = Property(str, lambda self: self._picker_validation_confidence, notify=stateChanged)
    pickerValidationNote = Property(str, lambda self: self._picker_validation_note, notify=stateChanged)
    pickerValidationSelector = Property(str, lambda self: self._picker_validation_selector, notify=stateChanged)
    categoryAnalysisReady = Property(bool, lambda self: self._category_analysis_ready, notify=stateChanged)
    categoryAnalysisMessage = Property(str, lambda self: self._category_analysis_message, notify=stateChanged)
    canAcceptPickedHint = Property(bool, lambda self: bool(self._pending_hint) and not self._picker_validation_active, notify=stateChanged)
    soldoutUrl = Property(str, lambda self: self._soldout_url, notify=stateChanged)
    soldoutSuggestion = Property("QVariantMap", lambda self: dict(self._soldout_suggestion), notify=stateChanged)
    soldoutCompareOpen = Property(bool, lambda self: self._soldout_compare_open, notify=stateChanged)

    def _probe_summary_with_checks(self) -> dict:
        result = dict(self._probe_summary)
        if "categories" in result:
            kept = [
                c for c in (result["categories"] or [])
                if c.get("url") not in self._excluded_urls
            ]
            result["categories"] = kept
            result["categoryCount"] = len(kept)
        return result

    @Slot(str, bool)
    def setCategoryExcluded(self, url: str, excluded: bool) -> None:
        if excluded:
            self._excluded_urls.add(url)
        else:
            self._excluded_urls.discard(url)
        self._emit()

    def _field_label_for_path(self, field_path: str) -> str:
        if field_path == "adapter.categories.all_products.url":
            return "전체상품 링크"
        if field_path == "adapter.categories.navigation.menu_selector":
            return "카테고리 메뉴"
        if field_path == OPTION_VALUES_FIELD_PATH:
            return "옵션값"
        if field_path == OPTION_PRICES_FIELD_PATH:
            return "옵션가격"
        key = field_path.split(".")[-1]
        return FIELD_LABELS_KO.get(key, key)

    def _hint_text_for_path(self, field_path: str) -> str:
        hints = {
            "adapter.categories.all_products.url": "사이트의 '전체상품' 또는 'ALL' 메뉴 링크를 클릭하세요.",
            "adapter.categories.navigation.menu_selector": "카테고리 메뉴 안의 대표 항목 하나(예: 의류, 상의)를 클릭하세요. 이 선택은 AI 설정 생성의 카테고리 힌트로 사용됩니다.",
            "adapter.listing.product_link": "상품 카드 안의 상세페이지 링크를 클릭하세요.",
            "adapter.product.main_image_url": "상품 대표 이미지를 클릭하세요.",
            "adapter.product.extra_image_urls": "추가 이미지/갤러리 영역 박스를 클릭하세요. AI가 이미지 선택자를 분석하고, 결과는 4단계 검증에서 확인됩니다.",
            "adapter.product.raw_product_name": "상품명 텍스트를 클릭하세요.",
            "adapter.product.supply_price": "공급가격 텍스트를 클릭하세요.",
            "adapter.product.detail_content": "상세 이미지들이 들어있는 영역 박스를 클릭하세요. AI가 이미지 선택자를 분석하고, 결과는 4단계 검증에서 확인됩니다.",
            OPTION_VALUES_FIELD_PATH: "옵션값 하나를 클릭하세요. 같은 그룹의 값을 자동으로 함께 수집합니다.",
            OPTION_PRICES_FIELD_PATH: "옵션가격 하나를 클릭하세요. 같은 순서의 가격들을 자동으로 함께 수집합니다.",
        }
        return hints.get(field_path, "수집할 요소를 클릭하세요.")

    def _hint_preview(self, picked) -> str:
        value = (
            picked.attribute_values.get("href")
            or picked.attribute_values.get("src")
            or picked.text
            or picked.selector
        )
        return str(value or "")[:120]

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
            # Close picker session when leaving stages 1-2 (analyze, map)
            if self._current_stage in (1, 2) and stage not in (1, 2):
                close_picker_session()
                self._picker_session_open = False
            self._current_stage = stage
            self._emit()

    @Slot("QVariantMap")
    def setConnectionInputs(self, values: Mapping[str, Any]) -> None:
        previous_identity = self._credential_identity()
        for key in ("supplierName", "mainUrl", "listingUrl", "detailUrl", "needsLogin"):
            if key in values:
                self._inputs[key] = values[key]
        self._invalidate_credentials_for_identity_change(previous_identity)
        self._emit()

    def _picker_target_url(self) -> str:
        """상품 필드 선택/미리보기가 이동할 URL. 사용자가 지정한 샘플 상품 URL을
        우선하고, 없으면 분석에서 찾은 첫 상품, 그것도 없으면 메인 URL."""
        target = str(self._inputs.get("detailUrl") or "").strip()
        if not target:
            sample_products = self._probe_summary.get("sampleProducts") or []
            if sample_products and sample_products[0].get("url"):
                target = str(sample_products[0]["url"])
        if not target:
            target = str(self._inputs.get("mainUrl") or "").strip()
        return target

    @Slot(str)
    def setDetailUrl(self, url: str) -> None:
        next_url = str(url or "").strip()
        if next_url == self._inputs.get("detailUrl"):
            return
        self._inputs["detailUrl"] = next_url
        self._clear_mapping_preview_values()
        if self._current_stage == 2 and self._yaml_text:
            self._schedule_mapping_preview()
        else:
            self._auto_preview_token += 1
        self._emit()

    @Slot(str)
    def setSoldoutUrl(self, url: str) -> None:
        next_url = str(url or "").strip()
        if next_url == self._soldout_url:
            return
        self._soldout_url = next_url
        self._soldout_suggestion = {}
        self._emit()

    @Slot(bool)
    def setSoldoutCompareOpen(self, open_: bool) -> None:
        self._soldout_compare_open = bool(open_)
        if not self._soldout_compare_open:
            self._soldout_suggestion = {}
        self._emit()

    @Slot("QVariantMap")
    def setLoginInputs(self, values: Mapping[str, Any]) -> None:
        previous_identity = self._credential_identity()
        for key in ("loginUrl", "username", "password"):
            if key in values:
                self._inputs[key] = str(values[key] or "")
        self._invalidate_credentials_for_identity_change(previous_identity)
        self._emit()

    def _credential_identity(self) -> tuple[str, str, str, bool]:
        normalize = lambda value: unicodedata.normalize("NFKC", str(value)).strip().casefold()
        return (
            normalize(self._inputs["supplierName"]),
            normalize(self._inputs["mainUrl"]),
            normalize(self._inputs["loginUrl"]),
            bool(self._inputs["needsLogin"]),
        )

    def _invalidate_credentials_for_identity_change(
        self, previous_identity: tuple[str, str, str, bool]
    ) -> None:
        current_identity = self._credential_identity()
        if previous_identity == current_identity:
            return
        if self._active_credential_key is None:
            return
        if self._active_credential_is_studio and self._active_credential_key.startswith("studio-"):
            try:
                delete_supplier_credentials(self._active_credential_key)
            except Exception:
                pass
            # 세션 state도 함께 삭제 (사용자/로그인 정보 변경 시 이전 세션 재사용 방지)
            try:
                clear_session_state(self._active_credential_key)
            except Exception:
                pass
        self._active_credential_key = None
        self._active_credential_identity = None
        self._active_credential_is_studio = False
        self._active_credentials = None

    @Slot(bool)
    def setAdvancedEditorOpen(self, open_: bool) -> None:
        self._advanced_editor_open = bool(open_)
        self._emit()

    def _task_start(self, key: str, label: str, stage: str, owner: object) -> bool:
        self._busy = True
        if self._app:
            if not self._app.acquire_task(key, label, owner):
                self._busy = False
                return False
            self._app.update_owned_task(owner, stage)
        self._emit()
        return True

    def _can_start_operation(self, key: str | None = None) -> bool:
        local = not self._shutting_down and not self._busy and self._worker is None
        return local and (not self._app or key is None or self._app.can_acquire_task(key, object()))

    def _guard_operation(self, key: str) -> bool:
        if self._can_start_operation(key):
            return True
        if self._app and not self._app.can_acquire_task(key, object()):
            self.set_field_errors({"form": "다른 작업이 진행 중입니다. 완료 후 다시 시도하세요."})
        return False

    def _connect_worker(self, worker, *, finished, key: str, label: str, stage: str) -> bool:
        if not self._can_start_operation(key):
            return False
        self._operation_id += 1
        operation_id = self._operation_id
        owner = object()
        self._task_owner = owner
        self._worker = worker
        worker.finished.connect(lambda *args: self._dispatch_finished(operation_id, finished, *args))
        worker.error.connect(lambda message: self._dispatch_error(operation_id, message))
        if hasattr(worker, "cancelled"):
            worker.cancelled.connect(lambda: self._dispatch_cancelled(operation_id))
        if hasattr(worker, "login_required"):
            worker.login_required.connect(lambda: self._dispatch_login_required(operation_id))
        if hasattr(worker, "progress"):
            worker.progress.connect(lambda message: self._dispatch_progress(operation_id, stage, message))
        if not self._task_start(key, label, stage, owner):
            self._worker = None
            self._task_owner = None
            return False
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

    def _dispatch_login_required(self, operation_id: int) -> None:
        if self._operation_is_current(operation_id):
            self._on_login_required()

    def _on_login_required(self) -> None:
        self._manual_login_pending = True
        self._emit()

    def _dispatch_progress(self, operation_id: int, stage: str, message: str) -> None:
        if self._operation_is_current(operation_id):
            self._task_progress(stage, message)

    def _task_progress(self, stage: str, message: str) -> None:
        progress = -1.0
        clean_message = message
        if message.startswith("[progress:"):
            end = message.find("]")
            if end > 0:
                try:
                    progress = float(message[len("[progress:"):end])
                    clean_message = message[end + 1 :].strip()
                except ValueError:
                    pass
        self._current_progress = progress
        self._current_progress_label = sanitize_diagnostic(clean_message)
        if self._app and self._task_owner is not None:
            self._app.update_owned_task(self._task_owner, stage, progress, self._current_progress_label)
        self._emit()

    def _clear_progress(self) -> None:
        self._current_progress = -1.0
        self._current_progress_label = ""

    def _operation_done(self) -> None:
        self._busy = False
        self._retire_current_worker()
        if self._app and self._task_owner is not None:
            self._app.complete_owned_task(self._task_owner)
        self._task_owner = None
        self._clear_progress()
        self._emit()

    def _operation_error(self, message: str) -> None:
        self._busy = False
        self._retire_current_worker()
        self._picker_active = False
        self._pending_hint = None
        self._picker_field_label = ""
        self._picker_field_hint = ""
        self._picker_field_path = ""
        self._has_pending_hint = False
        self._pending_hint_preview = ""
        self._pending_validation = None
        self._picker_validation_active = False
        self._picker_validation_confidence = ""
        self._picker_validation_note = ""
        self._picker_validation_selector = ""
        self._needs_mapping_login = False
        self._manual_login_pending = False
        self._preview_active = False
        if self._category_analysis_message == "카테고리 메뉴 분석 중...":
            self._category_analysis_ready = False
            self._category_analysis_message = "카테고리를 찾지 못했습니다. 다시 시도하세요."
        self._clear_progress()
        self.set_field_errors({"form": sanitize_diagnostic(message)})
        if self._app and self._task_owner is not None:
            self._app.fail_owned_task(self._task_owner, sanitize_diagnostic(message))
        self._task_owner = None
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
        if not self._guard_operation("adapter-probe"):
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
        detail = str(self._inputs.get("detailUrl") or "").strip()
        if not detail:
            errors["detailUrl"] = "샘플 상품 URL을 입력하세요. (필드 매핑에 사용됩니다)"
        elif not detail.startswith(("http://", "https://")):
            errors["detailUrl"] = "샘플 상품 URL은 http:// 또는 https://로 시작해야 합니다."
        if errors:
            self.set_field_errors(errors)
            return False
        if self._inputs["needsLogin"]:
            login_missing = not str(self._inputs.get("loginUrl") or "").strip()
            user_missing = not str(self._inputs.get("username") or "").strip()
            pw_missing = not str(self._inputs.get("password") or "").strip()
            if login_missing or user_missing or pw_missing:
                missing = []
                if login_missing:
                    missing.append("loginUrl")
                if user_missing:
                    missing.append("username")
                if pw_missing:
                    missing.append("password")
                labels = {"loginUrl": "로그인 URL", "username": "아이디", "password": "비밀번호"}
                self.set_field_errors({k: f"{labels[k]}을(를) 입력하세요." for k in missing})
                return False
        login_url = str(self._inputs["loginUrl"] or "").strip() or url
        credentials = (login_url, self._inputs["username"], self._inputs["password"])
        if self._inputs["needsLogin"] and all(credentials):
            self._remember_studio_credentials(str(credentials[1]), str(credentials[2]))
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
        self._excluded_urls = set()
        self._extra_test_urls = []
        self._validation_raw = {}
        self._probe_result = result
        self._probe_summary = {
            "finalUrl": result.final_url, "encoding": result.encoding,
            "needsLogin": result.needs_login, "categoryCount": len(result.categories or []),
            "categories": list(result.categories or []),
            "sampleProducts": list(result.sample_products or []),
            "hasAllProducts": result.has_all_products,
        }
        self._category_analysis_ready = bool(result.categories or result.has_all_products)
        self._category_analysis_message = (
            "카테고리 분석 완료"
            if self._category_analysis_ready
            else "카테고리 자동 분석 실패: 브라우저에서 카테고리 메뉴를 지정하세요."
        )
        # 로그인 세션 저장: 1단계에서 추출한 storage_state를 매핑/테스트 단계에서 재사용
        if getattr(result, "storage_state", None) and self._inputs["needsLogin"]:
            try:
                save_session_state(self._credential_key(), result.storage_state)
            except Exception:
                pass
        self._current_stage = 1
        self._operation_done()

    @Slot()
    def cancelProbe(self) -> None:
        self._cancel("사이트 분석 취소")

    @Slot()
    def generate(self) -> bool:
        if not self._guard_operation("adapter-generate"):
            return False
        if self._probe_result is None:
            self.set_field_errors({"form": "먼저 사이트 분석을 실행하세요."})
            return False
        if not self._category_analysis_ready:
            self.set_field_errors({"form": "카테고리 메뉴를 수동 지정하고 Yes로 확인하세요."})
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
        self._picker_active = False
        self._picker_session_open = False
        self._needs_mapping_login = False
        self._manual_login_pending = False
        self._preview_active = False
        close_picker_session()
        self._pending_hint = None
        self._picker_field_label = ""
        self._picker_field_hint = ""
        self._picker_field_path = ""
        self._has_pending_hint = False
        self._pending_hint_preview = ""
        self._pending_validation = None
        self._picker_validation_active = False
        self._picker_validation_confidence = ""
        self._picker_validation_note = ""
        self._picker_validation_selector = ""
        if self._app and self._task_owner is not None:
            self._app.cancel_owned_task(self._task_owner, message)
        self._task_owner = None
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
        self._schedule_mapping_preview()
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

    def _clear_mapping_preview_values(self) -> None:
        if self._yaml_text:
            self._refresh_mapping_rows()

    def _schedule_mapping_preview(self) -> None:
        self._auto_preview_token += 1
        token = self._auto_preview_token
        QTimer.singleShot(450, lambda: self._run_scheduled_mapping_preview(token))

    def _run_scheduled_mapping_preview(self, token: int) -> None:
        if token != self._auto_preview_token:
            return
        if self._current_stage != 2 or self._busy or not self._yaml_text:
            return
        target = self._picker_target_url()
        if not target.startswith(("http://", "https://")):
            return
        try:
            if not self._extract_preview_fields():
                return
        except Exception:
            return
        self.previewMapping()

    @Slot(result=str)
    def beginValidation(self) -> str:
        return yaml_content_hash(self._yaml_text)

    @Slot("QVariantMap", str)
    def acceptValidation(self, raw_results: Mapping[str, Any], tested_yaml_hash: str) -> None:
        self._validation_raw = dict(raw_results)
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

    def _preview_field(self, key: str, label: str, extractor) -> dict:
        return {
            "key": key,
            "label": label,
            "selector": extractor.selector or "",
            "attribute": extractor.attribute or "",
            "fallback_attribute": extractor.fallback_attribute or "",
            "html": bool(extractor.html),
            "multiple": bool(extractor.multiple),
            "transform": extractor.transform or "strip",
            "fallback": extractor.fallback or "",
            "fallback_from": extractor.fallback_from or "none",
            "url_param": extractor.url_param or "",
            "url_pattern": extractor.url_pattern or "",
        }

    def _extract_preview_fields(self) -> list[dict]:
        adapter = load_adapter_from_text(self._yaml_text)
        product = adapter.adapter.product
        fields = []
        for key, label in FIELD_LABELS_KO.items():
            extractor = getattr(product, key, None)
            if extractor and (
                extractor.selector.strip()
                or extractor.url_param
                or extractor.url_pattern
                or extractor.fallback_from not in (None, "", "none")
            ):
                fields.append(self._preview_field(key, label, extractor))
        option_group = adapter.adapter.options.groups[0] if adapter.adapter.options.groups else None
        if option_group and option_group.values_selector.strip():
            attribute = option_group.value_attribute if option_group.value_text == "attribute" else (
                "value" if option_group.value_text == "value" else ""
            )
            fields.append({
                "key": OPTION_VALUES_ROW_KEY,
                "label": "옵션값",
                "selector": option_group.values_selector,
                "attribute": attribute or "",
                "fallback_attribute": "",
                "html": False,
                "multiple": True,
                "transform": "strip",
                "fallback": "",
                "fallback_from": "none",
                "url_param": "",
                "url_pattern": "",
            })
        option_price = adapter.adapter.options.option_price_delta
        if option_price and option_price.selector.strip():
            fields.append(self._preview_field(OPTION_PRICES_ROW_KEY, "옵션가격", option_price))
        return fields

    @Slot()
    def previewMapping(self) -> bool:
        if not self._guard_operation("adapter-preview"):
            return False
        try:
            fields = self._extract_preview_fields()
        except Exception as exc:
            self.set_field_errors({"yamlText": f"YAML 오류: {exc}"})
            return False
        if not fields:
            self.set_field_errors({"form": "매핑된 필드가 없습니다."})
            return False
        target = self._picker_target_url()
        if not target:
            self.set_field_errors({"form": "미리보기할 상품 URL이 없습니다."})
            return False
        username = password = None
        if self._inputs["needsLogin"]:
            loaded = self._load_transient_credentials()
            if loaded:
                username, password = loaded
        login_url = str(self._inputs.get("loginUrl") or "").strip() or str(self._inputs.get("mainUrl") or "").strip() or None
        request = MappingPreviewRequest(
            yaml_text=self._yaml_text, target_url=target, fields=fields,
            login_url=login_url, username=username, password=password,
            supplier_key=self._credential_key() if self._inputs["needsLogin"] else None,
        )
        worker = MappingPreviewJob(request)
        self._preview_active = True
        self._picker_session_open = True
        return self._connect_worker(
            worker, finished=lambda result: self._preview_finished(result),
            key="adapter-preview", label="매핑 미리보기", stage="map",
        )

    def _preview_finished(self, result: dict) -> None:
        self._apply_preview_result(result)
        self._operation_done()

    def _apply_preview_result(self, result: Mapping[str, Any]) -> None:
        values = dict(result.get("values") or {})
        found = set(result.get("found") or [])
        try:
            rows = get_product_field_mappings(load_adapter_from_text(self._yaml_text))
        except Exception:
            return
        self._mapping_rows.resetRows([
            {
                **row,
                "testValue": str(values.get(row["key"], ""))[:100],
                "testOk": row["key"] in found and bool(values.get(row["key"])),
            }
            for row in rows
        ])

    @Slot()
    def closePreview(self) -> None:
        close_picker_session()
        self._preview_active = False
        self._picker_session_open = False
        self._emit()

    @Slot(str, str)
    def setFieldUrlPattern(self, field_key: str, pattern: str) -> None:
        """Set or clear url_pattern (advanced regex) for a product field and update YAML."""
        try:
            raw = yaml.safe_load(self._yaml_text)
            product = raw.get("adapter", {}).get("product", {})
            field = product.get(field_key)
            if field is None:
                field = {}
                product[field_key] = field
            if pattern:
                field["url_pattern"] = pattern
                field["fallback_from"] = "url"
                field.pop("selector", None)
            else:
                field.pop("url_pattern", None)
                if field.get("fallback_from") == "url" and not field.get("url_param"):
                    field["fallback_from"] = "none"
            self.setYamlText(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))
        except Exception as exc:
            self.set_field_errors({"yamlText": f"YAML 오류: {exc}"})

    @Slot(str, str)
    def setFieldUrlParam(self, field_key: str, param_name: str) -> None:
        """Set or clear url_param (query-parameter name) for a product field and update YAML."""
        try:
            raw = yaml.safe_load(self._yaml_text)
            product = raw.get("adapter", {}).get("product", {})
            field = product.get(field_key)
            if field is None:
                field = {}
                product[field_key] = field
            if param_name:
                field["url_param"] = param_name
                field["fallback_from"] = "url"
                field.pop("selector", None)
                field.pop("url_pattern", None)
            else:
                field.pop("url_param", None)
                if field.get("fallback_from") == "url" and not field.get("url_pattern"):
                    field["fallback_from"] = "none"
            self.setYamlText(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))
        except Exception as exc:
            self.set_field_errors({"yamlText": f"YAML 오류: {exc}"})

    @Slot(result="QVariantList")
    def urlParamOptions(self) -> list[dict[str, str]]:
        """샘플 상품 URL의 쿼리 파라미터를 [{name, value, display}, ...]로 반환. 없으면 빈 리스트."""
        from urllib.parse import parse_qsl, urlparse
        target = self._picker_target_url()
        if not target:
            return []
        options: list[dict[str, str]] = []
        for name, value in parse_qsl(urlparse(target).query):
            options.append({"name": name, "value": value, "display": f"{name} = {value}"})
        return options

    def _available_test_urls(self) -> list[str]:
        """검증에 쓸 상품 URL: 분석에서 찾은 샘플 + 사용자가 추가한 URL(중복 제거)."""
        urls = [str(item["url"]) for item in self._probe_summary.get("sampleProducts", []) if item.get("url")]
        if not urls:
            detail = str(self._inputs["detailUrl"] or "").strip()
            if detail:
                urls = [detail]
        for extra in self._extra_test_urls:
            if extra not in urls:
                urls.append(extra)
        return urls

    @Slot(str, result=bool)
    def addTestUrl(self, url: str) -> bool:
        url = str(url or "").strip()
        if not url.startswith(("http://", "https://")):
            self.set_field_errors({"extraTestUrl": "URL은 http:// 또는 https://로 시작해야 합니다."})
            return False
        if url not in self._available_test_urls():
            self._extra_test_urls.append(url)
        self.set_field_errors({})
        self._emit()
        return True

    @Slot(str)
    def removeTestUrl(self, url: str) -> None:
        url = str(url or "").strip()
        if url in self._extra_test_urls:
            self._extra_test_urls.remove(url)
            self._emit()

    @Slot(result=bool)
    def compareSoldoutStatus(self) -> bool:
        if not self._guard_operation("adapter-soldout-compare"):
            return False
        try:
            load_adapter_from_text(self._yaml_text)
        except Exception as exc:
            self.set_field_errors({"yamlText": f"YAML 오류: {exc}"})
            return False
        available_url = self._picker_target_url()
        soldout_url = str(self._soldout_url or "").strip()
        if not available_url.startswith(("http://", "https://")):
            self.set_field_errors({"detailUrl": "판매중 상품 URL을 먼저 입력하세요."})
            return False
        if not soldout_url.startswith(("http://", "https://")):
            self.set_field_errors({"soldoutUrl": "품절 상품 URL은 http:// 또는 https://로 시작해야 합니다."})
            return False
        if soldout_url == available_url:
            self.set_field_errors({"soldoutUrl": "판매중 상품과 다른 품절 상품 URL을 입력하세요."})
            return False
        username = password = None
        if self._inputs["needsLogin"]:
            loaded = self._load_transient_credentials()
            if loaded:
                username, password = loaded
        login_url = str(self._inputs["loginUrl"] or "").strip() or str(self._inputs["mainUrl"] or "").strip() or None
        request = SoldoutCompareRequest(
            self._yaml_text,
            available_url,
            soldout_url,
            login_url,
            username,
            password,
            supplier_key=self._credential_key() if self._inputs["needsLogin"] else None,
        )
        worker = self._factories["soldout_compare"](request)
        self._inputs["username"] = self._inputs["password"] = ""
        self._soldout_suggestion = {}
        self.set_field_errors({})
        return self._connect_worker(
            worker,
            finished=self._soldout_compare_finished,
            key="adapter-soldout-compare",
            label="품절 상태 비교",
            stage="map",
        )

    def _soldout_compare_finished(self, result: dict) -> None:
        self._soldout_suggestion = dict(result or {})
        if self._soldout_suggestion.get("confidence") == "low":
            self.set_field_errors({"soldoutUrl": "품절 요소를 확신하지 못했습니다. 판매 상태 행에서 수동으로 선택하세요."})
        self._operation_done()

    @Slot(result=bool)
    def acceptSoldoutSuggestion(self) -> bool:
        suggestion = dict(self._soldout_suggestion or {})
        if not suggestion:
            return False
        if suggestion.get("confidence") == "low":
            self.set_field_errors({"soldoutUrl": "신뢰도가 낮은 제안은 자동 적용하지 않습니다."})
            return False
        selector = str(suggestion.get("selector") or "").strip()
        fallback_from = str(suggestion.get("fallback_from") or "none").strip()
        if fallback_from not in {"none", "cart_button", "maxq"}:
            fallback_from = "none"
        if not selector and fallback_from == "none":
            self.set_field_errors({"soldoutUrl": "적용할 선택자나 fallback 규칙이 없습니다."})
            return False
        try:
            raw = yaml.safe_load(self._yaml_text) or {}
            product = raw.setdefault("adapter", {}).setdefault("product", {})
            field: dict[str, Any] = {}
            if selector:
                field["selector"] = selector
                if "img" in selector.lower():
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
            product["status_mapping"] = {
                "mapping": mapping,
                "default": suggestion.get("default") or "available",
            }
            self._soldout_suggestion = {}
            self._soldout_compare_open = False
            self.set_field_errors({})
            self.setYamlText(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))
            self._emit()
            return True
        except Exception as exc:
            self.set_field_errors({"yamlText": f"YAML 오류: {exc}"})
            return False

    @Slot()
    def rejectSoldoutSuggestion(self) -> None:
        self._soldout_suggestion = {}
        self._soldout_compare_open = False
        self._emit()

    def _build_validation_products(self) -> list[dict[str, Any]]:
        """검증 raw 결과를 상품별로 피벗: [{index, url, name, imageUrl, fields:[{key,label,value,ok}]}]."""
        raw = self._validation_raw
        if not raw:
            return []
        count = max((len(entries) for entries in raw.values() if isinstance(entries, list)), default=0)
        labels = {**FIELD_LABELS_KO, "option_values": "옵션값", "option_prices": "옵션가격"}
        products: list[dict[str, Any]] = []
        for i in range(count):
            fields: list[dict[str, Any]] = []
            url = ""
            for key, label in labels.items():
                entries = raw.get(key)
                if not isinstance(entries, list) or i >= len(entries):
                    continue
                entry = entries[i]
                url = url or str(entry.get("url") or "")
                value = entry.get("value")
                fields.append({
                    "key": key,
                    "label": label,
                    "value": str(value or ""),
                    "ok": bool(value) and is_field_value_ok(key, entry),
                    "imageUrls": list(entry.get("imageUrls") or []),
                    "imageCount": int(entry.get("imageCount") or 0),
                })
            def field_value(key: str) -> str:
                entries = raw.get(key)
                if isinstance(entries, list) and i < len(entries):
                    return str(entries[i].get("value") or "")
                return ""
            products.append({
                "index": i + 1,
                "url": url,
                "name": field_value("raw_product_name"),
                "imageUrl": field_value("main_image_url"),
                "fields": fields,
            })
        return products

    @Slot(bool)
    def setExtraImagesEnabled(self, enabled: bool) -> None:
        try:
            raw = yaml.safe_load(self._yaml_text) or {}
            product = raw.setdefault("adapter", {}).setdefault("product", {})
            if enabled:
                product.setdefault("extra_image_urls", {
                    "selector": "",
                    "attribute": "src",
                    "fallback_attribute": "data-src",
                    "multiple": True,
                    "optional": True,
                })
            else:
                product.pop("extra_image_urls", None)
            self.setYamlText(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))
        except Exception as exc:
            self.set_field_errors({"yamlText": f"YAML 오류: {exc}"})

    @Slot(str)
    def testSingle(self, field_key: str) -> bool:
        return self._start_test([field_key])

    @Slot()
    def testAll(self) -> bool:
        return self._start_test(None)

    def _start_test(self, fields: list[str] | None) -> bool:
        if not self._guard_operation("adapter-test"):
            return False
        try:
            load_adapter_from_text(self._yaml_text)
        except Exception as exc:
            self.set_field_errors({"yamlText": f"YAML 오류: {exc}"})
            return False
        urls = self._available_test_urls()
        if not urls:
            self.set_field_errors({"form": "테스트할 상품 URL이 없습니다."})
            return False
        tested_hash = self.beginValidation()
        username = password = None
        if self._inputs["needsLogin"]:
            loaded = self._load_transient_credentials()
            if loaded:
                username, password = loaded
        login_url = str(self._inputs["loginUrl"] or "").strip() or str(self._inputs["mainUrl"] or "").strip() or None
        request = AdapterTestRequest(
            self._yaml_text, urls[:3], tested_hash, login_url,
            username, password, tuple(fields) if fields else None,
            supplier_key=self._credential_key() if self._inputs["needsLogin"] else None,
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
        if not self._guard_operation("adapter-pick"):
            return False
        if self._inputs["needsLogin"] and not self._mapping_credentials_available():
            self._picker_field_path = field_path
            self._picker_field_label = self._field_label_for_path(field_path)
            self._picker_field_hint = self._hint_text_for_path(field_path)
            self._needs_mapping_login = True
            self._picker_active = False
            self._emit()
            return False
        self._needs_mapping_login = False
        self._pending_hint = None
        self._has_pending_hint = False
        self._pending_hint_preview = ""
        self._picker_active = True
        self._picker_session_open = True
        self._picker_field_path = field_path
        self._picker_field_label = self._field_label_for_path(field_path)
        self._picker_field_hint = self._hint_text_for_path(field_path)
        target = self._picker_target_url()
        username = password = None
        if self._inputs["needsLogin"]:
            loaded = self._load_transient_credentials()
            if loaded:
                username, password = loaded
        login_url = str(self._inputs["loginUrl"] or "").strip() or str(self._inputs["mainUrl"] or "").strip() or None
        worker = self._factories["picker"](PickerRequest(
            field_path, target, login_url, username, password,
            self._adapter_login_config(),
            field_label=self._picker_field_label,
            field_hint=self._picker_field_hint,
            supplier_key=self._credential_key() if self._inputs["needsLogin"] else None,
        ))
        ok = self._connect_worker(
            worker, finished=self._picked, key="adapter-pick",
            label="요소 선택", stage="map",
        )
        if not ok:
            self._picker_active = False
            self._emit()
        return ok

    @Slot("QVariantMap")
    def submitMappingLogin(self, values: Mapping[str, Any]) -> bool:
        """Accept login credentials entered in the mapping stage, store them, and resume the pending pick."""
        previous_identity = self._credential_identity()
        for key in ("loginUrl", "username", "password"):
            if key in values:
                self._inputs[key] = str(values[key] or "")
        self._invalidate_credentials_for_identity_change(previous_identity)
        login_url = str(self._inputs["loginUrl"] or "").strip() or str(self._inputs["mainUrl"] or "").strip()
        credentials = (login_url, self._inputs["username"], self._inputs["password"])
        if self._inputs["needsLogin"] and all(credentials):
            self._remember_studio_credentials(str(credentials[1]), str(credentials[2]))
        self._inputs["username"] = self._inputs["password"] = ""
        self._needs_mapping_login = False
        self.set_field_errors({})
        self._emit()
        pending = self._picker_field_path
        if pending:
            return self.pickElement(pending)
        return True

    @Slot()
    def confirmManualLogin(self) -> None:
        """User logged in manually in the browser — tell the worker to resume."""
        self._manual_login_pending = False
        worker = self._worker
        if worker is not None and hasattr(worker, "confirmManualLogin"):
            worker.confirmManualLogin()
        self._emit()

    @Slot()
    def cancelManualLogin(self) -> None:
        """User cancelled the manual-login prompt — tell the worker to abort."""
        self._manual_login_pending = False
        worker = self._worker
        if worker is not None and hasattr(worker, "cancelManualLogin"):
            worker.cancelManualLogin()
        self._emit()

    def _mapping_credentials_available(self) -> bool:
        """Non-side-effecting check: are login credentials loadable for mapping/test?"""
        if not self._inputs["needsLogin"]:
            return True
        if (
            self._active_credential_key is None
            or self._active_credential_identity != self._credential_identity()
        ):
            return False
        key = self._active_credential_key
        try:
            if load_supplier_credentials(key) is not None:
                return True
        except Exception:
            pass
        if self._active_credentials is not None:
            return True
        # keychain 없어도 저장된 브라우저 세션이 있으면 picker 진행 가능
        try:
            from app.analyzer.session_store import load_session_state
            return load_session_state(key) is not None
        except Exception:
            return False

    def _load_transient_credentials(self) -> tuple[str, str] | None:
        if not self._inputs["needsLogin"]:
            return None
        if (
            self._active_credential_key is None
            or self._active_credential_identity != self._credential_identity()
        ):
            return None
        try:
            key = self._active_credential_key
            credentials = load_supplier_credentials(key)
            return credentials or self._active_credentials
        except Exception:
            return self._active_credentials

    def _credential_key(self) -> str:
        return studio_credential_key(
            str(self._inputs["supplierName"]), str(self._inputs["mainUrl"])
        )

    def _remember_studio_credentials(self, username: str, password: str) -> None:
        credential_key = self._credential_key()
        clear_session_state(credential_key)
        self._active_credential_key = credential_key
        self._active_credential_identity = self._credential_identity()
        self._active_credential_is_studio = True
        self._active_credentials = (username, password)
        try:
            save_supplier_credentials(credential_key, username, password)
        except Exception:
            pass

    @Slot()
    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        close_picker_session()
        self._picker_session_open = False
        previous_operation = self._operation_id
        self._operation_id += 1
        self._cancelled_operations.add(previous_operation)
        self._task_owner = None
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
        self._retired_workers = stop_workers(workers)
        stop_picker_thread()
        self._busy = False
        self._emit()

    @Slot()
    def closePickerSession(self) -> None:
        close_picker_session()
        self._picker_session_open = False
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

    @Slot()
    def pickCategoryMenu(self) -> bool:
        return self.pickElement("adapter.categories.navigation.menu_selector")

    def _picked(self, picked, field_path: str) -> None:
        self._pending_hint = (picked, field_path)
        self._picker_active = False
        self._has_pending_hint = False
        self._pending_hint_preview = self._hint_preview(picked)
        self._pending_validation = None
        self._picker_validation_active = False
        self._picker_validation_confidence = ""
        self._picker_validation_note = ""
        self._picker_validation_selector = ""
        self._operation_done()
        if field_path == "adapter.categories.navigation.menu_selector":
            self._start_category_menu_analysis(picked)
        elif field_path in IMAGE_PICKER_FIELD_PATHS:
            if not self._start_picker_validation(picked, field_path):
                self.acceptPickedHint()
        else:
            # 브라우저의 Yes(이 요소가 맞나요?)가 곧 확인이다 — 앱 모달 없이
            # 바로 적용하고 브라우저 세션을 닫는다.
            self.acceptPickedHint()

    def _start_category_menu_analysis(self, picked) -> bool:
        # Fast path: links already captured from the visible browser — skip headless probe.
        if picked.container_links:
            self._category_analysis_ready = False
            self._category_analysis_message = "카테고리 메뉴 분석 중..."
            self.set_field_errors({})
            close_picker_session()
            self._picker_session_open = False
            self._category_menu_analysis_finished({"categories": list(picked.container_links)})
            return True

        defaults = suggest_defaults_for_field("adapter.categories.navigation.menu_selector", picked)
        selector = str(defaults.get("selector") or picked.selector or "").strip()
        if not selector:
            self._pending_hint = None
            self._category_analysis_ready = False
            self._category_analysis_message = "카테고리 메뉴 선택자를 찾지 못했습니다. 다시 시도하세요."
            self.set_field_errors({"form": self._category_analysis_message})
            self._emit()
            return False
        self._category_analysis_ready = False
        self._category_analysis_message = "카테고리 메뉴 분석 중..."
        self.set_field_errors({})
        close_picker_session()
        self._picker_session_open = False
        worker = self._factories["category_probe"](CategoryMenuProbeRequest(
            url=picked.url or str(self._inputs["mainUrl"] or "").strip(),
            selector=selector,
            selector_candidates=list(picked.selector_candidates or []),
            supplier_key=self._credential_key() if self._inputs["needsLogin"] else None,
        ))
        return self._connect_worker(
            worker, finished=self._category_menu_analysis_finished,
            key="adapter-category-probe", label="카테고리 메뉴 분석", stage="probe",
        )

    def _category_menu_analysis_finished(self, result: dict) -> None:
        self._excluded_urls = set()
        categories = list(result.get("categories") or [])
        if not categories:
            self._pending_hint = None
            self._category_analysis_ready = False
            self._category_analysis_message = "카테고리를 찾지 못했습니다. 다시 시도하세요."
            self.set_field_errors({"form": self._category_analysis_message})
            self._operation_done()
            return
        if self._probe_result is not None:
            self._probe_result.categories = categories
        self._probe_summary["categories"] = list(categories)
        self._probe_summary["categoryCount"] = len(categories)
        if self.acceptPickedHint():
            self._category_analysis_ready = True
            self._category_analysis_message = f"카테고리 {len(categories)}개 발견"
        self._operation_done()

    def _start_picker_validation(self, picked, field_path: str) -> bool:
        label = self._field_label_for_path(field_path)
        request = PickerValidateRequest(
            picked_element=picked,
            field_path=field_path,
            field_label=label,
        )
        worker = self._factories["picker_validate"](request)
        self._picker_validation_active = True
        self._picker_validation_confidence = ""
        self._picker_validation_note = ""
        self._picker_validation_selector = ""
        ok = self._connect_worker(
            worker, finished=self._picker_validation_finished,
            key="adapter-pick-validate", label="AI 선택자 검증", stage="map",
        )
        if not ok:
            self._picker_validation_active = False
        return ok

    def _picker_validation_finished(self, result: dict) -> None:
        self._pending_validation = result
        self._picker_validation_active = False
        self._picker_validation_selector = str(result.get("validated_selector", ""))
        self._picker_validation_confidence = str(result.get("confidence", ""))
        self._picker_validation_note = str(result.get("note", ""))
        self._operation_done()
        if self._pending_hint and self._pending_hint[1] in IMAGE_PICKER_FIELD_PATHS:
            self.acceptPickedHint()

    @Slot()
    def rejectPickedHint(self) -> None:
        self._pending_hint = None
        self._has_pending_hint = False
        self._pending_hint_preview = ""
        self._pending_validation = None
        self._picker_validation_active = False
        self._picker_validation_confidence = ""
        self._picker_validation_note = ""
        self._picker_validation_selector = ""
        # 피커 취소 시 브라우저 세션 닫기 (다시 선택 시 새 세션 열림)
        close_picker_session()
        self._picker_session_open = False
        self._emit()

    @Slot(result=bool)
    def reselectPickedHint(self) -> bool:
        if not self._pending_hint:
            return False
        _, field_path = self._pending_hint
        self._pending_hint = None
        self._has_pending_hint = False
        self._pending_hint_preview = ""
        self._pending_validation = None
        self._picker_validation_active = False
        self._picker_validation_confidence = ""
        self._picker_validation_note = ""
        self._picker_validation_selector = ""
        self._emit()
        return self.pickElement(field_path)

    @Slot(result=bool)
    def acceptPickedHint(self) -> bool:
        if not self._pending_hint:
            return False
        if self._picker_validation_active:
            self.set_field_errors({"form": "AI가 카테고리 메뉴를 분석 중입니다. 완료 후 Yes를 눌러주세요."})
            return False
        picked, field_path = self._pending_hint
        defaults = suggest_defaults_for_field(field_path, picked)
        # AI 검증 결과가 있고 신뢰도 high/medium이면 검증된 선택자로 교체
        validation = self._pending_validation
        if validation and validation.get("confidence") in {"high", "medium"}:
            validated = str(validation.get("validated_selector", "")).strip()
            if validated:
                defaults["selector"] = validated
            if field_path in IMAGE_PICKER_FIELD_PATHS:
                attribute = str(validation.get("attribute") or "").strip()
                if attribute in {"src", "data-src"}:
                    defaults["attribute"] = attribute
                defaults["multiple"] = bool(validation.get("multiple", True))
                if field_path == "adapter.product.detail_content":
                    defaults["html"] = False
        elif validation and field_path in IMAGE_PICKER_FIELD_PATHS:
            note = str(validation.get("note") or "AI 이미지 분석 신뢰도가 낮아 기존 선택자로 저장했습니다.").strip()
            self.set_field_errors({"form": note[:160]})
        # 선택자가 비어 있으면 후보 중 하나로 폴백; 그래도 없으면 사용자에게 안내
        if not str(defaults.get("selector", "")).strip():
            fallback = next((c for c in (picked.selector_candidates or []) if str(c).strip()), "")
            if fallback:
                defaults["selector"] = fallback
            else:
                self.set_field_errors({"form": "선택된 요소의 CSS 선택자를 추출하지 못했습니다. 다른 요소를 클릭해 다시 선택해 주세요."})
                self._has_pending_hint = True
                self._emit()
                return False
        hint = MappingHint(
            page_kind="listing" if "listing" in field_path or "all_products" in field_path else "detail",
            field_path=field_path, chosen_selector=defaults.pop("selector"), url=picked.url,
            selector_candidates=list(picked.selector_candidates or []), **defaults,
        )
        self._mapping_hints.append(hint)
        if self._yaml_text:
            try:
                raw = yaml.safe_load(self._yaml_text)
                apply_locked_hints_to_yaml_dict(raw, [hint])
                self.setYamlText(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))
            except Exception as exc:
                if field_path != "adapter.categories.navigation.menu_selector":
                    self.set_field_errors({"yamlText": f"YAML 오류: {exc}"})
                    return False
        if field_path in {
            "adapter.categories.navigation.menu_selector",
            "adapter.categories.all_products.url",
        }:
            self._category_analysis_ready = True
            self._category_analysis_message = "카테고리 메뉴 수동 분석 완료"
        self._pending_hint = None
        self._picker_field_label = ""
        self._picker_field_hint = ""
        self._picker_field_path = ""
        self._has_pending_hint = False
        self._pending_hint_preview = ""
        self._pending_validation = None
        self._picker_validation_active = False
        self._picker_validation_confidence = ""
        self._picker_validation_note = ""
        self._picker_validation_selector = ""
        # 피커 적용 시 브라우저 세션 닫기 (누적 방지)
        close_picker_session()
        self._picker_session_open = False
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
        if not self._migrate_credentials_to_runtime_slug(slug):
            return False
        self._yaml_dirty = False
        self.set_field_errors({})
        self._emit()
        return True

    def _migrate_credentials_to_runtime_slug(self, slug: str) -> bool:
        if not self._inputs["needsLogin"]:
            return True
        if (
            self._active_credential_key is None
            or self._active_credential_identity != self._credential_identity()
        ):
            return True
        source_key = self._active_credential_key
        if source_key == slug:
            return True
        try:
            credentials = load_supplier_credentials(source_key)
        except Exception as exc:
            self.set_field_errors({
                "form": "어댑터 파일은 저장되었지만 로그인 정보 연결에 실패했습니다: "
                f"{sanitize_diagnostic(exc)}"
            })
            self._emit()
            return False
        if not credentials:
            return True
        try:
            save_supplier_credentials(slug, credentials[0], credentials[1])
        except Exception as exc:
            self.set_field_errors({
                "form": "어댑터 파일은 저장되었지만 로그인 정보 연결에 실패했습니다: "
                f"{sanitize_diagnostic(exc)}"
            })
            self._emit()
            return False
        try:
            delete_supplier_credentials(source_key)
        except Exception:
            pass
        self._active_credential_key = slug
        self._active_credential_identity = self._credential_identity()
        self._active_credential_is_studio = False
        return True

    @Slot()
    def acknowledgeSaveWarning(self) -> None:
        decision = get_save_gate_decision(self._validation_summary, self._validation_stale)
        if decision.should_warn and decision.allow_continue:
            self._warning_ack = (yaml_content_hash(self._yaml_text), decision.reason)
            self._save_warning = {}
            self._emit()
