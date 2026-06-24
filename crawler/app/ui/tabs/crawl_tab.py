from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from app.config import load_config
from app.crawlers.registry import adapter_exists
from app.db.models import Supplier
from app.db.session import get_session
from app.ui.tabs.base_tab import BaseTab
from app.workers.crawl import (
    CategoryDiscoveryRequest,
    CategoryDiscoveryWorker,
    CrawlRequest,
    CrawlWorker,
)


class CrawlTab(BaseTab):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: CrawlWorker | None = None
        self._discovery_worker: CategoryDiscoveryWorker | None = None
        self._build_ui()
        self._refresh_suppliers()

    def default_title(self) -> str:
        return "상품 수집"

    def default_subtitle(self) -> str:
        return "도매처와 카테고리를 선택하여 상품 데이터를 자동으로 수집합니다."

    def _build_ui(self) -> None:
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        toolbar.addWidget(QLabel("도매처", self))
        self.supplier_combo = QComboBox(self)
        self.supplier_combo.currentIndexChanged.connect(self._on_supplier_changed)
        self.supplier_combo.setMinimumWidth(200)
        self.supplier_combo.setToolTip("수집할 도매처를 선택하세요. 도매처는 '도매처 관리' 탭에서 등록할 수 있습니다.")
        toolbar.addWidget(self.supplier_combo, stretch=1)

        self.discover_btn = QPushButton("카테고리 불러오기", self)
        self.discover_btn.setProperty("secondary", True)
        self.discover_btn.setToolTip("선택한 도매처의 카테고리 목록을 사이트에서 불러옵니다.")
        self.discover_btn.clicked.connect(self._on_discover)
        toolbar.addWidget(self.discover_btn)

        self.body_layout().addLayout(toolbar)

        self.category_tree = QTreeWidget(self)
        self.category_tree.setHeaderLabels(["카테고리", "ID"])
        self.category_tree.setColumnWidth(0, 300)
        self.category_tree.setToolTip("수집할 카테고리를 체크하세요. 대분류를 체크하면 하위 분류도 모두 수집됩니다.")
        self.body_layout().addWidget(self.category_tree, stretch=1)

        params = QHBoxLayout()
        params.setSpacing(10)
        params.addWidget(QLabel("최대 페이지", self))
        self.max_pages_spin = QSpinBox(self)
        self.max_pages_spin.setRange(1, 500)
        self.max_pages_spin.setValue(50)
        self.max_pages_spin.setToolTip("한 카테고리에서 수집할 최대 페이지 수입니다. 너무 크면 오래 걸립니다.")
        params.addWidget(self.max_pages_spin)

        params.addSpacing(12)
        params.addWidget(QLabel("대기 시간", self))
        self.delay_spin = QSpinBox(self)
        self.delay_spin.setRange(0, 60)
        self.delay_spin.setSuffix(" 초")
        self.delay_spin.setSpecialValueText("전역 설정")
        self.delay_spin.setToolTip("페이지 사이의 대기 시간입니다. 0이면 설정 탭의 전역 값을 따릅니다. 소상공인 사이트는 0초도 괜찮습니다.")
        params.addWidget(self.delay_spin)
        params.addStretch()

        self.start_btn = QPushButton("수집 시작", self)
        self.start_btn.setToolTip("선택한 카테고리의 상품 데이터 수집을 시작합니다.")
        self.start_btn.clicked.connect(self._on_start)
        params.addWidget(self.start_btn)

        self.cancel_btn = QPushButton("취소", self)
        self.cancel_btn.setProperty("secondary", True)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setToolTip("진행 중인 수집을 취소합니다.")
        self.cancel_btn.clicked.connect(self._on_cancel)
        params.addWidget(self.cancel_btn)

        self.body_layout().addLayout(params)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setVisible(False)
        self.body_layout().addWidget(self.progress_bar)

        self.log_text = QPlainTextEdit(self)
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(180)
        self.body_layout().addWidget(self.log_text)

        self.preview_table = QTableWidget(0, 3, self)
        self.preview_table.setHorizontalHeaderLabels(["상품명", "상품코드", "옵션 수"])
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.body_layout().addWidget(self.preview_table, stretch=1)

    def _refresh_suppliers(self) -> None:
        self.supplier_combo.clear()
        session = get_session()
        try:
            suppliers = session.query(Supplier).order_by(Supplier.name).all()
            for s in suppliers:
                self.supplier_combo.addItem(
                    s.name,
                    (s.id, s.adapter_file, s.credential_key, s.default_delay_seconds),
                )
        finally:
            session.close()

    def _on_supplier_changed(self) -> None:
        self.category_tree.clear()

    def _on_discover(self) -> None:
        data = self.supplier_combo.currentData()
        if not data:
            return
        supplier_id, adapter_file, credential_key, _supplier_delay = data
        if not adapter_file or not adapter_exists(adapter_file):
            QMessageBox.warning(self, "어댑터 없음", "이 도매처에 어댑터가 지정되지 않았습니다.")
            return

        self.log_text.appendPlainText("카테고리 불러오는 중...")
        self._discovery_worker = CategoryDiscoveryWorker(CategoryDiscoveryRequest(
            self.supplier_combo.currentText(), adapter_file, credential_key,
        ))
        self._discovery_worker.categories_found.connect(self._on_discover_finished)
        self._discovery_worker.error.connect(self._on_discover_error)
        self._discovery_worker.start()

    def _on_discover_finished(self, categories: list) -> None:
        self.category_tree.clear()
        for cat in categories:
            item = QTreeWidgetItem([cat.name, cat.category_id])
            item.setData(0, Qt.ItemDataRole.UserRole, (cat.category_id, cat.path))
            for child in cat.children:
                child_item = QTreeWidgetItem([child.name, child.category_id])
                child_item.setData(0, Qt.ItemDataRole.UserRole, (child.category_id, child.path))
                item.addChild(child_item)
            self.category_tree.addTopLevelItem(item)
        self.log_text.appendPlainText(f"카테고리 {len(categories)}개 발견")

    def _on_discover_error(self, msg: str) -> None:
        self.log_text.appendPlainText(f"\n카테고리 불러오기 오류: {msg}")
        QMessageBox.warning(self, "오류", f"카테고리를 불러오지 못했습니다:\n\n{msg}")

    def _collect_selected_categories(self) -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        root = self.category_tree.invisibleRootItem()
        for i in range(root.childCount()):
            self._collect_from_item(root.child(i), result)
        return result

    def _collect_from_item(self, item: QTreeWidgetItem, result: list[tuple[str, str]]) -> None:
        if item.checkState(0) == Qt.CheckState.Checked:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data:
                result.append(data)
        for i in range(item.childCount()):
            self._collect_from_item(item.child(i), result)

    def _on_start(self) -> None:
        data = self.supplier_combo.currentData()
        if not data:
            QMessageBox.warning(self, "선택 필요", "도매처를 선택하세요.")
            return
        supplier_id, adapter_file, credential_key, supplier_delay = data
        if not adapter_file or not adapter_exists(adapter_file):
            QMessageBox.warning(self, "어댑터 없음", "어댑터가 지정되지 않았습니다.")
            return

        selected = self._collect_selected_categories()
        if not selected:
            QMessageBox.warning(self, "카테고리 필요", "크롤링할 카테고리를 선택하세요.")
            return

        config = load_config()
        delay = (
            self.delay_spin.value()
            if self.delay_spin.value() > 0
            else supplier_delay if supplier_delay is not None
            else config.global_delay_seconds
        )
        supplier_name = self.supplier_combo.currentText()
        self._worker = CrawlWorker(CrawlRequest(
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            adapter_file=adapter_file,
            categories=selected,
            max_pages=self.max_pages_spin.value(),
            delay_seconds=delay,
            credential_key=credential_key,
        ))
        self._worker.progress.connect(self._on_progress)
        self._worker.product_found.connect(lambda name, code, _options: self._on_product_found(name, code))
        self._worker.finished.connect(self._on_finished)
        self._worker.cancelled.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.log_text.clear()
        self.preview_table.setRowCount(0)

    def _on_cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self.log_text.appendPlainText("취소 요청됨...")

    def _on_progress(self, msg: str) -> None:
        self.log_text.appendPlainText(msg)

    def _on_product_found(self, name: str, code: str) -> None:
        row = self.preview_table.rowCount()
        self.preview_table.insertRow(row)
        self.preview_table.setItem(row, 0, QTableWidgetItem(name))
        self.preview_table.setItem(row, 1, QTableWidgetItem(code))

    def _on_finished(self, products: int, options: int) -> None:
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.log_text.appendPlainText(f"\n완료: 상품 {products}개, 옵션 {options}개")
        self._refresh_suppliers()

    def _on_error(self, msg: str) -> None:
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.log_text.appendPlainText(f"\n오류: {msg}")
