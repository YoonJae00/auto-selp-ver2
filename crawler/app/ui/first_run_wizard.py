from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWidgets import QWizard, QWizardPage

from app.credentials.store import save_llm_api_key
from app.paths import config_dir, data_dir


class WelcomePage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Auto-Selp Crawler 설치 환영")
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        intro = QLabel(
            "Auto-Selp Crawler는 도매처 사이트에서 상품 데이터를 자동 수집하고\n"
            "재고 변동을 모니터링하는 데스크톱 앱입니다.\n\n"
            "시작하려면 AI 분석에 사용할 API 키와 브라우저 설정이 필요합니다.\n"
            "약 1분이면 완료됩니다.",
            self,
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)


class LlmKeyPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("AI 분석용 API 키 설정")
        self.setSubTitle("신규 사이트 분석에 사용합니다. 키는 시스템 키체인에 안전하게 저장됩니다.")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel("AI 제공자", self))
        self.provider_combo = QComboBox(self)
        self.provider_combo.addItem("Gemini (권장 - 비용 저렴, 분석 품질 우수)", "gemini")
        self.provider_combo.addItem("OpenAI", "openai")
        self.provider_combo.setToolTip("신규 사이트 분석에 사용할 AI 제공자를 선택하세요.")
        layout.addWidget(self.provider_combo)

        layout.addWidget(QLabel("API 키", self))
        self.key_edit = QLineEdit(self)
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("API 키를 입력하세요")
        self.key_edit.setToolTip("선택한 AI 제공자의 API 키를 입력하세요.\nGemini: https://aistudio.google.com/apikey\nOpenAI: https://platform.openai.com/api-keys")
        self.key_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.key_edit)

        hint = QLabel("Gemini API 키는 Google AI Studio에서 무료로 발급받을 수 있습니다.", self)
        hint.setProperty("caption", True)
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def _on_text_changed(self) -> None:
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return bool(self.key_edit.text().strip())

    def validatePage(self) -> bool:
        provider = self.provider_combo.currentData()
        api_key = self.key_edit.text().strip()
        if not api_key:
            return False
        save_llm_api_key(provider, api_key)
        return True


class BrowserPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("브라우저 및 데이터 경로 확인")
        self.setSubTitle("크롤링에 사용할 브라우저와 데이터 저장 위치를 확인합니다.")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel("브라우저", self))
        self.browser_combo = QComboBox(self)
        self.browser_combo.addItem("Microsoft Edge (시스템 설치 권장)", "msedge")
        self.browser_combo.addItem("Google Chrome (시스템 설치)", "chrome")
        self.browser_combo.addItem("Playwright Chromium (자동 다운로드)", "chromium")
        self.browser_combo.setToolTip("크롤링에 사용할 브라우저를 선택하세요.\nWindows에서는 Edge를 권장합니다. (기본 설치됨)")
        layout.addWidget(self.browser_combo)

        layout.addWidget(QLabel("데이터 저장 위치", self))
        path_label = QLabel(str(data_dir()), self)
        path_label.setWordWrap(True)
        path_label.setProperty("caption", True)
        path_label.setToolTip("수집된 상품 데이터와 설정 파일이 저장되는 위치입니다.")
        layout.addWidget(path_label)

    def validatePage(self) -> bool:
        (config_dir() / ".first_run_done").touch()
        return True
