from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, Property, Signal, Slot

from app.config import AppConfig, save_config
from app.credentials.store import load_llm_api_key, save_llm_api_key
from app.diagnostics import sanitize_diagnostic
from app.paths import config_dir
from app.ui_qml.viewmodels.base import BaseViewModel


def _quit_application() -> None:
    application = QCoreApplication.instance()
    if application is not None:
        application.quit()


class FirstRunViewModel(BaseViewModel):
    requiredChanged = Signal()

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        marker_dir: Callable[[], Path] = config_dir,
        config_saver: Callable[[AppConfig], None] = save_config,
        key_loader: Callable[[str], str | None] = load_llm_api_key,
        key_saver: Callable[[str, str], None] = save_llm_api_key,
        app_quitter: Callable[[], None] = _quit_application,
    ) -> None:
        super().__init__(parent)
        self._marker_dir = marker_dir
        self._config_saver = config_saver
        self._key_loader = key_loader
        self._key_saver = key_saver
        self._app_quitter = app_quitter
        self._required = not self._marker_path().exists()

    required = Property(bool, lambda self: self._required, notify=requiredChanged)

    def _marker_path(self) -> Path:
        return self._marker_dir() / ".first_run_done"

    def _set_required(self, required: bool) -> None:
        if self._required != required:
            self._required = required
            self.requiredChanged.emit()
            self.changed.emit()

    def _has_key(self, provider: str) -> bool:
        try:
            return bool(self._key_loader(provider))
        except Exception as exc:
            self.set_field_errors({"apiKey": sanitize_diagnostic(exc)})
            return False

    @Slot(str, str, result=bool)
    def complete(self, browser_channel: str, api_key: str) -> bool:
        # LLM 제공사는 OpenAI 단일 — 제공사 선택 없음.
        provider = "openai"
        browser = (browser_channel or "").strip().casefold()
        secret = api_key or ""
        errors: dict[str, str] = {}
        if browser not in {"msedge", "chrome", "chromium"}:
            errors["browserChannel"] = "브라우저를 선택하세요."
        if not secret and not self._has_key(provider):
            errors["apiKey"] = "API 키를 입력하세요."
        if errors:
            self.set_field_errors(errors)
            return False

        try:
            self._config_saver(AppConfig(llm_provider=provider, browser_channel=browser))
            if secret:
                try:
                    self._key_saver(provider, secret)
                except Exception:
                    self.set_field_errors({"apiKey": "API 키 저장에 실패했습니다."})
                    return False
            marker = self._marker_path()
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("done\n", encoding="utf-8")
        except Exception as exc:
            self.set_field_errors({"form": sanitize_diagnostic(exc)})
            return False

        self.set_field_errors({})
        self._set_required(False)
        return True

    @Slot()
    def cancel(self) -> None:
        self._app_quitter()
