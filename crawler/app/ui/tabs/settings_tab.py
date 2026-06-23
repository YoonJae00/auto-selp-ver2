from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.config import AppConfig, load_config, save_config
from app.credentials.store import delete_llm_api_key, load_llm_api_key, save_llm_api_key
from app.paths import data_dir
from app.ui.tabs.base_tab import BaseTab
from app.update.checker import get_latest_release, is_newer


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setStyleSheet("""
        QFrame {
            background-color: #ffffff;
            border: 1px solid #e8e8ed;
            border-radius: 12px;
        }
    """)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(12)

    label = QLabel(title)
    label.setProperty("section", True)
    layout.addWidget(label)

    return frame, layout


class SettingsTab(BaseTab):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config: AppConfig = load_config()
        self._build_ui()
        self._load_values()

    def default_title(self) -> str:
        return "설정"

    def default_subtitle(self) -> str:
        return "LLM 제공자, 브라우저, 크롤링 지연, 업데이트를 관리합니다."

    def _build_ui(self) -> None:
        # LLM Card
        llm_card, llm_layout = _card("LLM 설정")

        form1 = QFormLayout()
        form1.setSpacing(10)

        self.provider_combo = QComboBox(self)
        self.provider_combo.addItem("Gemini (권장 - 비용 저렴)", "gemini")
        self.provider_combo.addItem("OpenAI", "openai")
        self.provider_combo.setToolTip("신규 사이트 분석에 사용할 기본 AI 제공자를 선택하세요.")
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        form1.addRow("기본 AI 제공자", self.provider_combo)

        # Gemini API key
        self.gemini_key_edit = QLineEdit(self)
        self.gemini_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.gemini_key_edit.setPlaceholderText("Gemini API 키")
        self.gemini_key_edit.setToolTip("Google AI Studio(https://aistudio.google.com/apikey)에서 무료 발급 가능합니다.")
        form1.addRow("Gemini API 키", self.gemini_key_edit)

        # OpenAI API key
        self.openai_key_edit = QLineEdit(self)
        self.openai_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_key_edit.setPlaceholderText("OpenAI API 키")
        self.openai_key_edit.setToolTip("OpenAI Platform(https://platform.openai.com/api-keys)에서 발급 가능합니다.")
        form1.addRow("OpenAI API 키", self.openai_key_edit)

        # Auto-fallback checkbox
        self.fallback_checkbox = QCheckBox("할당량 초과 시 다른 AI로 자동 전환")
        self.fallback_checkbox.setToolTip("기본 AI의 사용량이 초과되면 자동으로 다른 AI로 전환하여 분석을 계속합니다.")
        self.fallback_checkbox.setChecked(True)
        form1.addRow("", self.fallback_checkbox)

        llm_layout.addLayout(form1)

        self.body_layout().addWidget(llm_card)

        # Browser Card
        browser_card, browser_layout = _card("브라우저 설정")

        form2 = QFormLayout()
        form2.setSpacing(10)

        self.browser_combo = QComboBox(self)
        self.browser_combo.addItem("Microsoft Edge (시스템 설치)", "msedge")
        self.browser_combo.addItem("Google Chrome (시스템 설치)", "chrome")
        self.browser_combo.addItem("Playwright Chromium (자동 다운로드)", "chromium")
        self.browser_combo.setToolTip("크롤링에 사용할 브라우저를 선택하세요.\nWindows에서는 Edge를 권장합니다. (기본 설치됨)")
        form2.addRow("브라우저", self.browser_combo)

        browser_layout.addLayout(form2)
        self.body_layout().addWidget(browser_card)

        # Crawl Delay Card
        delay_card, delay_layout = _card("크롤링 지연 설정")

        form3 = QFormLayout()
        form3.setSpacing(10)

        self.delay_spin = QSpinBox(self)
        self.delay_spin.setRange(0, 10)
        self.delay_spin.setSuffix(" 초")
        self.delay_spin.setToolTip("페이지/상품 사이의 대기 시간입니다.\n소상공인 사이트는 0초도 무방합니다.\n도매처별로 다르게 설정할 수도 있습니다.")
        form3.addRow("전역 대기 시간", self.delay_spin)

        delay_layout.addLayout(form3)
        self.body_layout().addWidget(delay_card)

        # Misc Card
        misc_card, misc_layout = _card("기타")

        self.update_checkbox = QCheckBox("시작 시 업데이트 확인", self)
        self.update_checkbox.setToolTip("앱 시작 시 최신 버전이 있는지 확인하고 알려줍니다.")
        misc_layout.addWidget(self.update_checkbox)

        update_row = QHBoxLayout()
        self.update_check_btn = QPushButton("지금 업데이트 확인", self)
        self.update_check_btn.setProperty("secondary", True)
        self.update_check_btn.setToolTip("최신 버전이 있는지 확인합니다.")
        self.update_check_btn.clicked.connect(self._on_check_update)
        update_row.addWidget(self.update_check_btn)
        update_row.addStretch()
        misc_layout.addLayout(update_row)

        data_label = QLabel(str(data_dir()), self)
        data_label.setWordWrap(True)
        data_label.setProperty("caption", True)
        misc_layout.addWidget(QLabel("데이터 저장 위치", self))
        misc_layout.addWidget(data_label)

        self.body_layout().addWidget(misc_card)

        # Save button (saves everything: API keys + settings)
        save_row = QHBoxLayout()
        save_row.addStretch()
        self.save_btn = QPushButton("모두 저장", self)
        self.save_btn.setToolTip("API 키와 모든 설정을 함께 저장합니다.")
        self.save_btn.clicked.connect(self._on_save_all)
        save_row.addWidget(self.save_btn)
        self.body_layout().addLayout(save_row)

    def _load_values(self) -> None:
        idx = self.provider_combo.findData(self.config.llm_provider)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)

        gemini_key = load_llm_api_key("gemini")
        if gemini_key:
            self.gemini_key_edit.setText(gemini_key)

        openai_key = load_llm_api_key("openai")
        if openai_key:
            self.openai_key_edit.setText(openai_key)

        idx = self.browser_combo.findData(self.config.browser_channel)
        if idx >= 0:
            self.browser_combo.setCurrentIndex(idx)

        self.delay_spin.setValue(self.config.global_delay_seconds)
        self.update_checkbox.setChecked(self.config.check_updates_on_start)
        self.fallback_checkbox.setChecked(self.config.auto_fallback_enabled)

    def _on_provider_changed(self) -> None:
        """Auto-save provider selection when changed."""
        self.config.llm_provider = self.provider_combo.currentData()
        save_config(self.config)

    def _on_save_all(self) -> None:
        """Save everything: API keys to keyring + settings to config file."""
        # Save API keys
        gemini_key = self.gemini_key_edit.text().strip()
        openai_key = self.openai_key_edit.text().strip()
        if gemini_key:
            save_llm_api_key("gemini", gemini_key)
        if openai_key:
            save_llm_api_key("openai", openai_key)

        # Save settings
        self.config.llm_provider = self.provider_combo.currentData()
        self.config.browser_channel = self.browser_combo.currentData()
        self.config.global_delay_seconds = self.delay_spin.value()
        self.config.check_updates_on_start = self.update_checkbox.isChecked()
        self.config.auto_fallback_enabled = self.fallback_checkbox.isChecked()
        save_config(self.config)

        # Build success message
        saved_parts = []
        if gemini_key:
            saved_parts.append("Gemini 키")
        if openai_key:
            saved_parts.append("OpenAI 키")
        saved_parts.append("설정")

        QMessageBox.information(self, "저장됨", f"{' + '.join(saved_parts)}이(가) 저장되었습니다.")

    def _on_check_update(self) -> None:
        release = get_latest_release()
        if not release:
            QMessageBox.information(self, "업데이트 확인", "현재 버전 정보를 가져올 수 없습니다.")
            return
        if is_newer(self.config.app_version, release.tag):
            QMessageBox.information(
                self,
                "업데이트 가능",
                f"새 버전 {release.tag}이(가) 있습니다.\n\n{release.name}\n\n{release.url}",
            )
        else:
            QMessageBox.information(self, "업데이트 확인", f"최신 버전입니다. (현재: v{self.config.app_version})")
