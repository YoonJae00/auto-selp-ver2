from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Property, Signal, Slot

from app.config import AppConfig, load_config, save_config
from app.credentials.store import (
    delete_llm_api_key,
    load_llm_api_key,
    save_llm_api_key,
)
from app.diagnostics import sanitize_diagnostic
from app.ui_qml.viewmodels.base import BaseViewModel


Section = dict[str, object]


class SettingsViewModel(BaseViewModel):
    settingsChanged = Signal()

    _SECTIONS: tuple[Section, ...] = (
        {
            "id": "llm",
            "title": "LLM / AI",
            "titleKo": "AI 제공자",
            "description": "Provider and write-only API key settings",
            "descriptionKo": "제공자와 쓰기 전용 API 키 설정",
            "keywords": "llm ai provider api key gemini openai 모델 제공자 키",
        },
        {
            "id": "browser",
            "title": "Browser",
            "titleKo": "브라우저",
            "description": "Default automation browser channel",
            "descriptionKo": "자동화에 사용할 기본 브라우저",
            "keywords": "browser channel edge msedge chrome chromium 브라우저 채널 엣지 크롬",
        },
        {
            "id": "behavior",
            "title": "Behavior",
            "titleKo": "동작",
            "description": "Delay, update checks, and fallback behavior",
            "descriptionKo": "대기 시간, 업데이트 확인, 자동 대체 동작",
            "keywords": "delay updates fallback behavior 대기 업데이트 자동 대체 동작",
        },
    )

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        config_loader: Callable[[], AppConfig] = load_config,
        config_saver: Callable[[AppConfig], None] = save_config,
        key_loader: Callable[[str], str | None] = load_llm_api_key,
        key_saver: Callable[[str, str], None] = save_llm_api_key,
        key_deleter: Callable[[str], None] = delete_llm_api_key,
    ) -> None:
        super().__init__(parent)
        self._config_loader = config_loader
        self._config_saver = config_saver
        self._key_loader = key_loader
        self._key_saver = key_saver
        self._key_deleter = key_deleter
        self._config = self._load_config()

    def _load_config(self) -> AppConfig:
        try:
            return self._config_loader()
        except Exception as exc:  # pragma: no cover - defensive UI fallback
            self.set_field_errors({"form": sanitize_diagnostic(exc)})
            return AppConfig()

    llmProvider = Property(str, lambda self: self._config.llm_provider, notify=settingsChanged)
    browserChannel = Property(str, lambda self: self._config.browser_channel, notify=settingsChanged)
    globalDelaySeconds = Property(int, lambda self: int(self._config.global_delay_seconds), notify=settingsChanged)
    checkUpdatesOnStart = Property(bool, lambda self: bool(self._config.check_updates_on_start), notify=settingsChanged)
    autoFallbackEnabled = Property(bool, lambda self: bool(self._config.auto_fallback_enabled), notify=settingsChanged)
    pickerAiValidation = Property(bool, lambda self: bool(self._config.picker_ai_validation), notify=settingsChanged)
    appVersion = Property(str, lambda self: self._config.app_version, notify=settingsChanged)
    sections = Property("QVariantList", lambda self: [dict(section) for section in self._SECTIONS], constant=True)

    geminiKeyConfigured = Property(
        bool,
        lambda self: bool(self._safe_load_key("gemini")),
        notify=settingsChanged,
    )
    openaiKeyConfigured = Property(
        bool,
        lambda self: bool(self._safe_load_key("openai")),
        notify=settingsChanged,
    )

    def _safe_load_key(self, provider: str) -> str | None:
        try:
            return self._key_loader(provider)
        except Exception as exc:  # pragma: no cover - depends on host keyring
            self.set_field_errors({"credentials": sanitize_diagnostic(exc)})
            return None

    @Slot(str, result="QVariantList")
    def filterSections(self, query: str) -> list[Section]:
        normalized = (query or "").strip().casefold()
        if not normalized:
            return [dict(section) for section in self._SECTIONS]
        matches: list[Section] = []
        for section in self._SECTIONS:
            haystack = " ".join(str(value) for value in section.values()).casefold()
            if normalized in haystack:
                matches.append(dict(section))
        return matches

    @Slot(str, result=bool)
    def removeApiKey(self, provider: str) -> bool:
        provider = (provider or "").strip().casefold()
        if provider not in {"gemini", "openai"}:
            self.set_field_errors({"apiKey": "지원하지 않는 제공자입니다."})
            return False
        try:
            self._key_deleter(provider)
        except Exception:
            self.set_field_errors({"apiKey": "API 키 삭제에 실패했습니다."})
            return False
        self.set_field_errors({})
        self.settingsChanged.emit()
        self.changed.emit()
        return True

    @Slot(str, str, int, bool, bool, bool, str, str, result=bool)
    def save(
        self,
        llm_provider: str,
        browser_channel: str,
        global_delay_seconds: int,
        check_updates_on_start: bool,
        auto_fallback_enabled: bool,
        picker_ai_validation: bool,
        gemini_api_key: str,
        openai_api_key: str,
    ) -> bool:
        provider = (llm_provider or "").strip().casefold()
        browser = (browser_channel or "").strip().casefold()
        errors: dict[str, str] = {}
        if provider not in {"gemini", "openai"}:
            errors["llmProvider"] = "제공자를 선택하세요."
        if browser not in {"msedge", "chrome", "chromium"}:
            errors["browserChannel"] = "브라우저를 선택하세요."
        if int(global_delay_seconds) < 0:
            errors["globalDelaySeconds"] = "0초 이상이어야 합니다."
        if errors:
            self.set_field_errors(errors)
            return False

        next_config = AppConfig(
            llm_provider=provider,
            browser_channel=browser,
            global_delay_seconds=int(global_delay_seconds),
            check_updates_on_start=bool(check_updates_on_start),
            app_version=self._config.app_version,
            auto_fallback_enabled=bool(auto_fallback_enabled),
            picker_ai_validation=bool(picker_ai_validation),
        )
        try:
            self._config_saver(next_config)
        except Exception as exc:
            self.set_field_errors({"form": sanitize_diagnostic(exc)})
            return False
        try:
            if gemini_api_key:
                self._key_saver("gemini", gemini_api_key)
            if openai_api_key:
                self._key_saver("openai", openai_api_key)
        except Exception:
            self.set_field_errors({"apiKey": "API 키 저장에 실패했습니다."})
            return False

        self._config = next_config
        self.set_field_errors({})
        self.settingsChanged.emit()
        self.changed.emit()
        return True
