from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QMainWindow,
    QStatusBar,
    QTabWidget,
    QWizard,
)

from app.config import AppConfig, load_config, save_config
from app.paths import assets_dir, config_dir
from app.ui.first_run_wizard import BrowserPage, LlmKeyPage, WelcomePage
from app.ui.tabs.adapter_builder_tab import AdapterBuilderTab
from app.ui.tabs.crawl_tab import CrawlTab
from app.ui.tabs.export_tab import ExportTab
from app.ui.tabs.monitor_tab import MonitorTab
from app.ui.tabs.settings_tab import SettingsTab
from app.ui.tabs.suppliers_tab import SuppliersTab
from app.workers.lifecycle import install_shutdown_hook


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        install_shutdown_hook()
        self.config: AppConfig = load_config()

        self.setWindowTitle("Auto-Selp Crawler")
        self.setMinimumSize(900, 600)
        self.resize(1100, 850)
        self._apply_icon()
        self._apply_stylesheet()

        if not self.first_run_marker_path().exists():
            self._run_first_run_wizard()

        tabs = QTabWidget(self)
        tabs.addTab(SuppliersTab(self), "도매처 관리")
        tabs.addTab(AdapterBuilderTab(self), "신규 사이트 등록")
        self.crawl_tab = CrawlTab(self)
        tabs.addTab(self.crawl_tab, "상품 수집")
        tabs.addTab(MonitorTab(self), "재고 모니터링")
        tabs.addTab(ExportTab(self), "엑셀 저장")
        tabs.addTab(SettingsTab(self), "설정")
        tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.setCentralWidget(tabs)

        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("준비됨")

    def _run_first_run_wizard(self) -> None:
        wizard = QWizard(self)
        wizard.setWindowTitle("Auto-Selp Crawler 초기 설정")
        wizard.setMinimumWidth(520)
        welcome = WelcomePage()
        llm_page = LlmKeyPage()
        browser_page = BrowserPage()
        wizard.addPage(welcome)
        wizard.addPage(llm_page)
        wizard.addPage(browser_page)
        if wizard.exec() == QDialog.DialogCode.Accepted:
            self.config.browser_channel = browser_page.browser_combo.currentData() or "msedge"
            self.config.llm_provider = llm_page.provider_combo.currentData() or "gemini"
            save_config(self.config)

    def _apply_icon(self) -> None:
        icon_path = assets_dir() / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _apply_stylesheet(self) -> None:
        qss_path = Path(__file__).resolve().parent / "styles" / "global.qss"
        if qss_path.exists():
            from PySide6.QtWidgets import QApplication

            QApplication.instance().setStyleSheet(qss_path.read_text(encoding="utf-8"))

    def first_run_marker_path(self) -> Path:
        return config_dir() / ".first_run_done"

    def show_status(self, message: str) -> None:
        self.statusBar().showMessage(message)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.crawl_tab.shutdown()
        event.accept()
