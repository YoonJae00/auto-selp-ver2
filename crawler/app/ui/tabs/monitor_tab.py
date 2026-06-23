from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.db.models import Product, StockChange, Supplier
from app.db.session import get_session
from app.ui.tabs.base_tab import BaseTab


class MonitorTab(BaseTab):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._refresh()

    def default_title(self) -> str:
        return "재고 모니터링"

    def default_subtitle(self) -> str:
        return "도매처 상품의 품절, 복구, 가격 변동 이력을 추적합니다."

    def _build_ui(self) -> None:
        filters = QHBoxLayout()
        filters.setSpacing(10)

        filters.addWidget(QLabel("도매처", self))
        self.supplier_combo = QComboBox(self)
        self.supplier_combo.addItem("전체", None)
        self.supplier_combo.setMinimumWidth(150)
        self.supplier_combo.setToolTip("특정 도매처의 변동만 보려면 선택하세요.")
        filters.addWidget(self.supplier_combo)

        filters.addSpacing(8)
        filters.addWidget(QLabel("변동 유형", self))
        self.type_combo = QComboBox(self)
        self.type_combo.addItem("전체", None)
        self.type_combo.addItem("품절", "sold_out")
        self.type_combo.addItem("복구", "restocked")
        self.type_combo.addItem("가격 변동", "price_changed")
        self.type_combo.addItem("재고 변동", "stock_changed")
        self.type_combo.setToolTip("특정 유형의 변동만 보려면 선택하세요.")
        filters.addWidget(self.type_combo)

        filters.addStretch()

        refresh_btn = QPushButton("새로고침", self)
        refresh_btn.setProperty("secondary", True)
        refresh_btn.setToolTip("변동 이력을 새로고침합니다.")
        refresh_btn.clicked.connect(self._refresh)
        filters.addWidget(refresh_btn)

        ack_btn = QPushButton("선택 읽음", self)
        ack_btn.setProperty("secondary", True)
        ack_btn.setToolTip("선택한 변동 알림을 읽음으로 표시합니다.")
        ack_btn.clicked.connect(self._on_acknowledge)
        filters.addWidget(ack_btn)

        ack_all_btn = QPushButton("전체 읽음", self)
        ack_all_btn.setProperty("secondary", True)
        ack_all_btn.setToolTip("모든 변동 알림을 읽음으로 표시합니다.")
        ack_all_btn.clicked.connect(self._on_acknowledge_all)
        filters.addWidget(ack_all_btn)

        self.body_layout().addLayout(filters)

        self.table = QTableWidget(0, 6, self)
        self.table.setHorizontalHeaderLabels(["시간", "도매처", "상품코드", "변동 유형", "이전값", "새값"])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setToolTip("도매처 상품의 변동 이력입니다. 빨간색 텍스트는 아직 읽지 않은 알림입니다.")
        self.body_layout().addWidget(self.table, stretch=1)

        self.empty_label = self.create_empty_label("아직 기록된 변동이 없습니다.\n도매처 등록 시 재고 모니터링을 활성화하세요.")
        self.empty_label.setVisible(False)
        self.body_layout().addWidget(self.empty_label)

    def _refresh(self) -> None:
        self.supplier_combo.clear()
        self.supplier_combo.addItem("전체", None)
        session = get_session()
        try:
            suppliers = session.query(Supplier).order_by(Supplier.name).all()
            for s in suppliers:
                self.supplier_combo.addItem(s.name, s.id)
        finally:
            session.close()

        session = get_session()
        try:
            supplier_filter = self.supplier_combo.currentData()
            type_filter = self.type_combo.currentData()

            stmt = (
                select(StockChange, Product, Supplier)
                .join(Product, StockChange.product_id == Product.id)
                .join(Supplier, Product.supplier_id == Supplier.id)
                .order_by(StockChange.detected_at.desc())
            )
            if supplier_filter:
                stmt = stmt.where(Supplier.id == supplier_filter)
            if type_filter:
                stmt = stmt.where(StockChange.change_type == type_filter)

            results = session.execute(stmt).all()
            has_data = len(results) > 0
            self.table.setVisible(has_data)
            self.empty_label.setVisible(not has_data)
            self.table.setRowCount(len(results))
            for row, (change, product, supplier) in enumerate(results):
                time_str = change.detected_at.strftime("%Y-%m-%d %H:%M") if change.detected_at else ""
                self.table.setItem(row, 0, QTableWidgetItem(time_str))
                self.table.setItem(row, 1, QTableWidgetItem(supplier.name))
                self.table.setItem(row, 2, QTableWidgetItem(product.supplier_product_code))
                self.table.setItem(row, 3, QTableWidgetItem(change.change_type))
                self.table.setItem(row, 4, QTableWidgetItem(change.previous_value or ""))
                self.table.setItem(row, 5, QTableWidgetItem(change.new_value or ""))
                self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, change.id)
                if not change.acknowledged:
                    for col in range(6):
                        item = self.table.item(row, col)
                        if item:
                            item.setForeground(Qt.GlobalColor.red)
        finally:
            session.close()

    def _on_acknowledge(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        change_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        session = get_session()
        try:
            change = session.get(StockChange, change_id)
            if change:
                change.acknowledged = True
                change.acknowledged_at = datetime.now()
                session.commit()
                self._refresh()
        finally:
            session.close()

    def _on_acknowledge_all(self) -> None:
        session = get_session()
        try:
            changes = session.query(StockChange).filter_by(acknowledged=False).all()
            for change in changes:
                change.acknowledged = True
                change.acknowledged_at = datetime.now()
            session.commit()
            self._refresh()
        finally:
            session.close()
