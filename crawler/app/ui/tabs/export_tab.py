from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)

from app.db.models import Supplier
from app.db.session import get_session
from app.exporters.excel import export_to_excel
from app.paths import exports_dir
from app.ui.tabs.base_tab import BaseTab


class ExportTab(BaseTab):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._refresh_suppliers()

    def default_title(self) -> str:
        return "엑셀 저장"

    def default_subtitle(self) -> str:
        return "수집된 상품 데이터를 엑셀 파일로 저장합니다. 저장 후 Auto-Selp 업로드 페이지에서 바로 사용할 수 있습니다."

    def _build_ui(self) -> None:
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        toolbar.addWidget(QLabel("도매처", self))
        self.supplier_combo = QComboBox(self)
        self.supplier_combo.addItem("전체 도매처", None)
        self.supplier_combo.setMinimumWidth(200)
        self.supplier_combo.setToolTip("특정 도매처의 상품만 저장하려면 선택하세요.")
        toolbar.addWidget(self.supplier_combo, stretch=1)

        self.export_btn = QPushButton("엑셀 파일로 저장", self)
        self.export_btn.setToolTip("수집된 상품 데이터를 표준 형식의 엑셀 파일로 저장합니다.\n저장된 파일은 Auto-Selp 업로드 페이지에서 업로드할 수 있습니다.")
        self.export_btn.clicked.connect(self._on_export)
        toolbar.addWidget(self.export_btn)
        self.body_layout().addLayout(toolbar)

        self.sync_btn = QPushButton("서버 직접 연동 (준비 중)", self)
        self.sync_btn.setEnabled(False)
        self.sync_btn.setProperty("secondary", True)
        self.sync_btn.setToolTip("향후 Auto-Selp 서버에 직접 상품 데이터를 전송하는 기능입니다. 현재는 엑셀 저장 후 업로드 페이지를 이용하세요.")
        self.body_layout().addWidget(self.sync_btn)

        self.recent_label = QLabel("최근 저장한 파일", self)
        self.recent_label.setProperty("section", True)
        self.body_layout().addWidget(self.recent_label)

        self.recent_table = QTableWidget(0, 2, self)
        self.recent_table.setHorizontalHeaderLabels(["파일명", "저장 시간"])
        self.recent_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.recent_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.recent_table.setAlternatingRowColors(True)
        self.recent_table.setToolTip("최근 저장한 엑셀 파일 목록입니다.")
        self.body_layout().addWidget(self.recent_table, stretch=1)

        refresh_row = QHBoxLayout()
        refresh_row.addStretch()
        refresh_btn = QPushButton("새로고침", self)
        refresh_btn.setProperty("secondary", True)
        refresh_btn.setToolTip("파일 목록을 새로고침합니다.")
        refresh_btn.clicked.connect(self._refresh_recent)
        refresh_row.addWidget(refresh_btn)
        self.body_layout().addLayout(refresh_row)

    def _refresh_suppliers(self) -> None:
        self.supplier_combo.clear()
        self.supplier_combo.addItem("전체 도매처", None)
        session = get_session()
        try:
            for s in session.query(Supplier).order_by(Supplier.name).all():
                self.supplier_combo.addItem(s.name, s.id)
        finally:
            session.close()

    def _refresh_recent(self) -> None:
        self.recent_table.setRowCount(0)
        files = sorted(exports_dir().glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]
        for row, f in enumerate(files):
            self.recent_table.insertRow(row)
            self.recent_table.setItem(row, 0, QTableWidgetItem(f.name))
            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            self.recent_table.setItem(row, 1, QTableWidgetItem(mtime))

    def _on_export(self) -> None:
        supplier_id = self.supplier_combo.currentData()
        supplier_name = self.supplier_combo.currentText() or "all"

        default_name = f"{supplier_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        default_path = exports_dir() / default_name

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "엑셀 파일 저장",
            str(default_path),
            "Excel Files (*.xlsx)",
        )
        if not file_path:
            return

        from pathlib import Path

        output_path = Path(file_path)
        session = get_session()
        try:
            result = export_to_excel(session, supplier_id, output_path)
            QMessageBox.information(
                self,
                "내보내기 완료",
                f"엑셀 파일이 저장되었습니다:\n{result}\n\n이 파일을 Auto-Selp /upload 페이지에서 업로드하세요.",
            )
            self._refresh_recent()
        except Exception as exc:
            QMessageBox.critical(self, "내보내기 오류", str(exc))
        finally:
            session.close()
