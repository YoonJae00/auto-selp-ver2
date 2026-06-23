from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.credentials.store import (
    delete_supplier_credentials,
    load_supplier_credentials,
    save_supplier_credentials,
)
from app.crawlers.registry import adapter_exists, list_adapters
from app.db.models import Supplier
from app.db.session import get_session
from app.ui.tabs.base_tab import BaseTab


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "", name.lower().replace(" ", "-"))


class SupplierDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, supplier: Supplier | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("도매처 편집" if supplier else "새 도매처 추가")
        self.setMinimumWidth(480)
        self._supplier = supplier
        self._build_ui()
        if supplier:
            self._load_supplier(supplier)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)

        self.name_edit = QLineEdit(self)
        self.name_edit.setPlaceholderText("예: 아이토픽")
        self.name_edit.setToolTip("크롤링할 도매처 사이트의 이름을 입력하세요.")
        form.addRow("도매처명", self.name_edit)

        self.url_edit = QLineEdit(self)
        self.url_edit.setPlaceholderText("https://www.example.com")
        self.url_edit.setToolTip("도매처 사이트의 메인 주소를 입력하세요.")
        form.addRow("웹사이트 주소", self.url_edit)

        self.login_checkbox = QCheckBox("로그인이 필요한 사이트입니다", self)
        self.login_checkbox.setToolTip("체크하면 로그인 후 크롤링합니다. 계정 정보는 안전하게 시스템 키체인에 저장됩니다.")
        form.addRow("", self.login_checkbox)

        self.username_edit = QLineEdit(self)
        self.username_edit.setToolTip("도매처 사이트 로그인에 사용하는 아이디입니다.")
        form.addRow("로그인 아이디", self.username_edit)

        self.password_edit = QLineEdit(self)
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setToolTip("도매처 사이트 로그인에 사용하는 비밀번호입니다. 암호화되어 저장됩니다.")
        form.addRow("로그인 비밀번호", self.password_edit)

        self.adapter_combo = QComboBox(self)
        self.adapter_combo.addItem("(없음 - 신규 사이트 등록에서 생성)", "")
        for slug in list_adapters():
            self.adapter_combo.addItem(slug, slug)
        self.adapter_combo.setToolTip("이 도매처에 사용할 사이트 분석 설정을 선택하세요. 없으면 '신규 사이트 등록' 탭에서 생성하세요.")
        form.addRow("사이트 분석 설정", self.adapter_combo)

        self.delay_spin = QSpinBox(self)
        self.delay_spin.setRange(0, 60)
        self.delay_spin.setSuffix(" 초")
        self.delay_spin.setSpecialValueText("전역 설정 사용")
        self.delay_spin.setToolTip("이 도매처만의 페이지 대기 시간입니다. 0이면 설정 탭의 전역 값을 따릅니다.")
        form.addRow("수집 대기 시간", self.delay_spin)

        self.monitor_checkbox = QCheckBox("재고 모니터링 사용", self)
        self.monitor_checkbox.setToolTip("체크하면 주기적으로 사이트를 확인하여 품절, 복구, 가격 변동을 알려줍니다.")
        form.addRow("", self.monitor_checkbox)

        self.interval_spin = QSpinBox(self)
        self.interval_spin.setRange(1, 168)
        self.interval_spin.setSuffix(" 시간")
        self.interval_spin.setValue(12)
        self.interval_spin.setToolTip("몇 시간마다 재고를 확인할지 설정합니다. 기본 12시간.")
        form.addRow("확인 주기", self.interval_spin)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_supplier(self, supplier: Supplier) -> None:
        self.name_edit.setText(supplier.name)
        self.url_edit.setText(supplier.base_url)
        self.login_checkbox.setChecked(supplier.needs_login)
        if supplier.adapter_file:
            idx = self.adapter_combo.findData(supplier.adapter_file)
            if idx >= 0:
                self.adapter_combo.setCurrentIndex(idx)
        if supplier.default_delay_seconds is not None:
            self.delay_spin.setValue(supplier.default_delay_seconds)
        self.monitor_checkbox.setChecked(supplier.monitor_enabled)
        self.interval_spin.setValue(supplier.monitor_interval_hours)

        if supplier.credential_key:
            creds = load_supplier_credentials(supplier.credential_key)
            if creds:
                self.username_edit.setText(creds[0])
                self.password_edit.setText(creds[1])

    def _on_accept(self) -> None:
        name = self.name_edit.text().strip()
        url = self.url_edit.text().strip()
        if not name or not url:
            QMessageBox.warning(self, "입력 오류", "도매처명과 URL을 입력하세요.")
            return
        self.accept()

    def get_values(self) -> dict:
        slug = _slugify(self.name_edit.text().strip())
        return {
            "name": self.name_edit.text().strip(),
            "base_url": self.url_edit.text().strip(),
            "needs_login": self.login_checkbox.isChecked(),
            "username": self.username_edit.text().strip() or None,
            "password": self.password_edit.text() or None,
            "adapter_file": self.adapter_combo.currentData() or None,
            "default_delay_seconds": self.delay_spin.value() if self.delay_spin.value() > 0 else None,
            "monitor_enabled": self.monitor_checkbox.isChecked(),
            "monitor_interval_hours": self.interval_spin.value(),
            "credential_key": slug if self.login_checkbox.isChecked() else None,
        }


class SuppliersTab(BaseTab):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._refresh_table()

    def default_title(self) -> str:
        return "도매처 관리"

    def default_subtitle(self) -> str:
        return "크롤링할 도매처 사이트와 로그인 계정을 관리합니다."

    def _build_ui(self) -> None:
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        add_btn = QPushButton("+ 새 도매처 추가", self)
        add_btn.setToolTip("새로운 도매처 사이트를 등록합니다. 로그인 정보는 안전하게 시스템에 저장됩니다.")
        add_btn.clicked.connect(self._on_add)
        toolbar.addWidget(add_btn)

        edit_btn = QPushButton("편집", self)
        edit_btn.setProperty("secondary", True)
        edit_btn.setToolTip("선택한 도매처의 정보를 수정합니다.")
        edit_btn.clicked.connect(self._on_edit)
        toolbar.addWidget(edit_btn)

        del_btn = QPushButton("삭제", self)
        del_btn.setProperty("danger", True)
        del_btn.setToolTip("선택한 도매처와 관련된 모든 상품 데이터를 삭제합니다.")
        del_btn.clicked.connect(self._on_delete)
        toolbar.addWidget(del_btn)

        toolbar.addStretch()

        refresh_btn = QPushButton("새로고침", self)
        refresh_btn.setProperty("secondary", True)
        refresh_btn.setToolTip("도매처 목록을 새로고침합니다.")
        refresh_btn.clicked.connect(self._refresh_table)
        toolbar.addWidget(refresh_btn)

        self.body_layout().addLayout(toolbar)

        self.table = QTableWidget(0, 6, self)
        self.table.setHorizontalHeaderLabels(["도매처명", "주소", "로그인", "사이트 설정", "재고 모니터", "확인 주기"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setToolTip("등록된 도매처 목록입니다. 행을 클릭하여 선택한 후 편집 또는 삭제할 수 있습니다.")
        self.body_layout().addWidget(self.table)

        self.empty_label = self.create_empty_label("아직 등록된 도매처가 없습니다.\n+ 새 도매처 추가 버튼을 눌러 시작하세요.")
        self.empty_label.setVisible(False)
        self.body_layout().addWidget(self.empty_label)

    def _refresh_table(self) -> None:
        session = get_session()
        try:
            suppliers = session.query(Supplier).order_by(Supplier.name).all()
            has_data = len(suppliers) > 0
            self.table.setVisible(has_data)
            self.empty_label.setVisible(not has_data)

            self.table.setRowCount(len(suppliers))
            for row, s in enumerate(suppliers):
                self.table.setItem(row, 0, QTableWidgetItem(s.name))
                self.table.setItem(row, 1, QTableWidgetItem(s.base_url))
                self.table.setItem(row, 2, QTableWidgetItem("필요" if s.needs_login else "불필요"))
                self.table.setItem(row, 3, QTableWidgetItem(s.adapter_file or "(없음)"))
                self.table.setItem(row, 4, QTableWidgetItem("사용" if s.monitor_enabled else "미사용"))
                self.table.setItem(row, 5, QTableWidgetItem(f"{s.monitor_interval_hours}시간"))
                self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, s.id)
        finally:
            session.close()

    def _selected_supplier_id(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _on_add(self) -> None:
        dialog = SupplierDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            values = dialog.get_values()
            session = get_session()
            try:
                slug = _slugify(values["name"])
                if values["username"] and values["password"]:
                    save_supplier_credentials(slug, values["username"], values["password"])
                supplier = Supplier(
                    name=values["name"],
                    base_url=values["base_url"],
                    needs_login=values["needs_login"],
                    adapter_file=values["adapter_file"],
                    default_delay_seconds=values["default_delay_seconds"],
                    monitor_enabled=values["monitor_enabled"],
                    monitor_interval_hours=values["monitor_interval_hours"],
                    credential_key=slug if values["needs_login"] else None,
                )
                session.add(supplier)
                session.commit()
                self._refresh_table()
            finally:
                session.close()

    def _on_edit(self) -> None:
        supplier_id = self._selected_supplier_id()
        if not supplier_id:
            QMessageBox.information(self, "선택 필요", "편집할 도매처를 선택하세요.")
            return
        session = get_session()
        try:
            supplier = session.get(Supplier, supplier_id)
            if not supplier:
                return
            dialog = SupplierDialog(self, supplier)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                values = dialog.get_values()
                slug = _slugify(values["name"])
                if values["username"] and values["password"]:
                    save_supplier_credentials(slug, values["username"], values["password"])
                supplier.name = values["name"]
                supplier.base_url = values["base_url"]
                supplier.needs_login = values["needs_login"]
                supplier.adapter_file = values["adapter_file"]
                supplier.default_delay_seconds = values["default_delay_seconds"]
                supplier.monitor_enabled = values["monitor_enabled"]
                supplier.monitor_interval_hours = values["monitor_interval_hours"]
                supplier.credential_key = slug if values["needs_login"] else None
                session.commit()
                self._refresh_table()
        finally:
            session.close()

    def _on_delete(self) -> None:
        supplier_id = self._selected_supplier_id()
        if not supplier_id:
            QMessageBox.information(self, "선택 필요", "삭제할 도매처를 선택하세요.")
            return
        confirm = QMessageBox.question(
            self,
            "삭제 확인",
            "이 도매처와 관련된 모든 상품 데이터가 삭제됩니다. 계속하시겠습니까?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        session = get_session()
        try:
            supplier = session.get(Supplier, supplier_id)
            if supplier and supplier.credential_key:
                delete_supplier_credentials(supplier.credential_key)
            if supplier:
                session.delete(supplier)
                session.commit()
                self._refresh_table()
        finally:
            session.close()
