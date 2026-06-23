from __future__ import annotations

import hashlib
import re

from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.analyzer.element_picker import PickedElement, suggest_defaults_for_field
from app.analyzer.mapping_hints import MappingHint
from app.analyzer.adapter_schema import (
    Adapter,
    FIELD_LABELS_KO,
    get_product_field_mappings,
    get_category_summary,
    get_pagination_summary,
    get_login_summary,
    get_options_summary,
)
from app.analyzer.site_probe import ProbeResult
from app.analyzer.validation_summary import ValidationSummary, build_validation_summary, get_save_gate_decision
from app.config import load_config
from app.credentials.store import save_supplier_credentials
from app.crawlers.registry import load_adapter_from_text, save_adapter
from app.ui.tabs.base_tab import BaseTab
from app.workers.adapter import (
    AdapterTestRequest, GenerateRequest, GenerateWorker, PickerRequest,
    PickerWorker, ProbeRequest, ProbeWorker, TestWorker,
)


HINT_FIELD_CHOICES = [
    ("상품명", "adapter.product.raw_product_name"),
    ("상품코드", "adapter.product.supplier_product_code"),
    ("상품ID", "adapter.product.supplier_product_id"),
    ("공급가", "adapter.product.supply_price"),
    ("원산지", "adapter.product.origin"),
    ("대표이미지", "adapter.product.main_image_url"),
    ("상세페이지", "adapter.product.detail_content"),
    ("판매상태", "adapter.product.supplier_status"),
    ("상품링크", "adapter.listing.product_link"),
]


# ====== Worker threads ======


# ====== Module-level helpers ======


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "", name.lower().replace(" ", "-"))


def _test_value_success(value: object) -> bool:
    return bool(value) and not str(value).startswith("0/")


def _card(title: str, subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setProperty("card", True)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(10)

    title_label = QLabel(title)
    title_label.setProperty("section", True)
    layout.addWidget(title_label)

    if subtitle:
        sub = QLabel(subtitle)
        sub.setProperty("subheading", True)
        sub.setWordWrap(True)
        layout.addWidget(sub)

    return frame, layout


def _make_inset_frame(label_text: str) -> tuple[QFrame, QLabel]:
    """Build a cardInset frame with a caption label and a value label."""
    frame = QFrame()
    frame.setProperty("cardInset", True)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(4)

    cap = QLabel(label_text)
    cap.setProperty("caption", True)
    layout.addWidget(cap)

    val = QLabel("(미설정)")
    val.setWordWrap(True)
    layout.addWidget(val)

    return frame, val


# ====== Tab class ======


class AdapterBuilderTab(BaseTab):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._probe_result: ProbeResult | None = None
        self._probe_worker: ProbeWorker | None = None
        self._generate_worker: GenerateWorker | None = None
        self._test_worker: QThread | None = None
        self._picker_worker: QThread | None = None
        self._last_test_raw_results: dict[str, list[dict]] = {}
        self._last_validation_yaml_hash: str | None = None
        self._last_validation_urls: list[str] = []
        self._last_validation_summary: ValidationSummary | None = None
        self._validation_stale = False
        self._mapping_hints: list[MappingHint] = []
        self._build_ui()

    # ---------- default labels ----------

    def default_title(self) -> str:
        return "신규 사이트 등록"

    def default_subtitle(self) -> str:
        return "AI가 도매처 사이트 구조를 자동으로 분석하여 상품 수집 설정을 생성합니다."

    # ---------- UI construction ----------

    def _build_ui(self) -> None:
        self._build_input_card()
        self._build_probe_result_card()
        self._build_ai_card()
        self._build_result_card()
        self.add_stretch()

    # --- 1단계: 사이트 정보 입력 ---

    def _build_input_card(self) -> None:
        input_card, input_layout = _card(
            "1단계: 사이트 정보 입력",
            "분석할 도매처 사이트의 주소를 입력하세요.",
        )

        form_layout = QVBoxLayout()
        form_layout.setSpacing(10)

        # 도매처명
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_label = QLabel("도매처명")
        name_label.setMinimumWidth(100)
        name_label.setToolTip("크롤링할 도매처 사이트의 이름을 입력하세요. 예: 아이토픽")
        name_row.addWidget(name_label)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("예: 아이토픽")
        self.name_edit.setToolTip("크롤링할 도매처 사이트의 이름을 입력하세요. 예: 아이토픽")
        name_row.addWidget(self.name_edit, stretch=1)
        form_layout.addLayout(name_row)

        # 메인 주소
        url_row = QHBoxLayout()
        url_row.setSpacing(8)
        url_label = QLabel("메인 주소")
        url_label.setMinimumWidth(100)
        url_label.setToolTip("도매처 사이트의 메인 주소를 입력하세요.")
        url_row.addWidget(url_label)
        self.main_url_edit = QLineEdit()
        self.main_url_edit.setPlaceholderText("http://www.example.com")
        self.main_url_edit.setToolTip("도매처 사이트의 메인 주소를 입력하세요.")
        url_row.addWidget(self.main_url_edit, stretch=1)
        form_layout.addLayout(url_row)

        # 상품 목록 주소
        list_row = QHBoxLayout()
        list_row.setSpacing(8)
        list_label = QLabel("상품 목록 주소")
        list_label.setMinimumWidth(100)
        list_label.setToolTip("상품 목록이 보이는 페이지 주소입니다. 비워두면 메인 페이지에서 자동 탐색합니다.")
        list_row.addWidget(list_label)
        self.listing_url_edit = QLineEdit()
        self.listing_url_edit.setPlaceholderText("비워도 됩니다. 예: http://www.example.com/shop/list")
        self.listing_url_edit.setToolTip("상품 목록이 보이는 페이지 주소입니다. 비워두면 메인 페이지에서 자동 탐색합니다.")
        list_row.addWidget(self.listing_url_edit, stretch=1)
        form_layout.addLayout(list_row)

        # 상품 상세 주소
        detail_row = QHBoxLayout()
        detail_row.setSpacing(8)
        detail_label = QLabel("상품 상세 주소")
        detail_label.setMinimumWidth(100)
        detail_label.setToolTip("개별 상품 페이지 주소입니다. 비워두면 목록에서 첫 상품을 자동 선택합니다.")
        detail_row.addWidget(detail_label)
        self.detail_url_edit = QLineEdit()
        self.detail_url_edit.setPlaceholderText("비워도 됩니다. 예: http://www.example.com/shop/goods/123")
        self.detail_url_edit.setToolTip("개별 상품 페이지 주소입니다. 비워두면 목록에서 첫 상품을 자동 선택합니다.")
        detail_row.addWidget(self.detail_url_edit, stretch=1)
        form_layout.addLayout(detail_row)

        # 로그인 섹션
        login_separator = QLabel("— 로그인이 필요한 사이트 —")
        login_separator.setProperty("caption", True)
        form_layout.addWidget(login_separator)

        login_check_row = QHBoxLayout()
        login_check_row.setSpacing(8)
        self.login_checkbox = QCheckBox("로그인이 필요한 사이트입니다")
        self.login_checkbox.setToolTip(
            "체크하면 로그인 후 사이트 구조를 분석합니다. "
            "가격이나 상품 정보가 로그인 후에만 보이는 도매처에서 필요합니다."
        )
        self.login_checkbox.toggled.connect(self._on_login_toggled)
        login_check_row.addWidget(self.login_checkbox)
        login_check_row.addStretch()
        form_layout.addLayout(login_check_row)

        # 로그인 필드 (초기 숨김)
        self.login_url_edit = QLineEdit()
        self.login_url_edit.setPlaceholderText("로그인 페이지 주소 (예: https://www.example.com/shop/login)")
        self.login_url_edit.setToolTip("도매처 사이트의 로그인 페이지 주소를 입력하세요.")
        self.login_url_edit.setVisible(False)
        login_url_label = QLabel("로그인 주소")
        login_url_label.setMinimumWidth(100)
        login_url_label.setVisible(False)
        self._login_url_label = login_url_label
        login_url_row = QHBoxLayout()
        login_url_row.setSpacing(8)
        login_url_row.addWidget(login_url_label)
        login_url_row.addWidget(self.login_url_edit, stretch=1)
        form_layout.addLayout(login_url_row)

        self.login_id_edit = QLineEdit()
        self.login_id_edit.setPlaceholderText("로그인 아이디")
        self.login_id_edit.setToolTip("도매처 사이트 로그인 아이디입니다. 안전하게 시스템 키체인에 저장됩니다.")
        self.login_id_edit.setVisible(False)
        login_id_label = QLabel("아이디")
        login_id_label.setMinimumWidth(100)
        login_id_label.setVisible(False)
        self._login_id_label = login_id_label
        login_id_row = QHBoxLayout()
        login_id_row.setSpacing(8)
        login_id_row.addWidget(login_id_label)
        login_id_row.addWidget(self.login_id_edit, stretch=1)
        form_layout.addLayout(login_id_row)

        self.login_pw_edit = QLineEdit()
        self.login_pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.login_pw_edit.setPlaceholderText("로그인 비밀번호")
        self.login_pw_edit.setToolTip("도매처 사이트 로그인 비밀번호입니다. 암호화되어 시스템 키체인에 저장됩니다.")
        self.login_pw_edit.setVisible(False)
        login_pw_label = QLabel("비밀번호")
        login_pw_label.setMinimumWidth(100)
        login_pw_label.setVisible(False)
        self._login_pw_label = login_pw_label
        login_pw_row = QHBoxLayout()
        login_pw_row.setSpacing(8)
        login_pw_row.addWidget(login_pw_label)
        login_pw_row.addWidget(self.login_pw_edit, stretch=1)
        form_layout.addLayout(login_pw_row)

        input_layout.addLayout(form_layout)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.probe_btn = QPushButton("2단계: 사이트 구조 분석")
        self.probe_btn.setToolTip(
            "사이트에 접속하여 상품 구조, 카테고리, 로그인 형태를 자동으로 파악합니다.\n"
            "약 10~20초 소요됩니다."
        )
        self.probe_btn.clicked.connect(self._on_probe)
        btn_row.addWidget(self.probe_btn)
        self.cancel_probe_btn = QPushButton("취소")
        self.cancel_probe_btn.setProperty("secondary", True)
        self.cancel_probe_btn.setEnabled(False)
        self.cancel_probe_btn.clicked.connect(self._on_cancel_probe)
        btn_row.addWidget(self.cancel_probe_btn)
        btn_row.addStretch()
        input_layout.addLayout(btn_row)

        self.body_layout().addWidget(input_card)

    # --- 프로브 결과 카드 (new) ---

    def _build_probe_result_card(self) -> None:
        self.probe_result_card, probe_layout = _card(
            "2단계: 프로브 결과",
            "사이트 구조 분석 결과입니다.",
        )
        self.probe_result_card.setVisible(False)

        # Badge row
        badges_row = QHBoxLayout()
        badges_row.setSpacing(8)

        self.badge_login = QLabel("로그인: -")
        self.badge_login.setProperty("badge", True)
        badges_row.addWidget(self.badge_login)

        self.badge_encoding = QLabel("인코딩: -")
        self.badge_encoding.setProperty("badge", True)
        badges_row.addWidget(self.badge_encoding)

        self.badge_all_products = QLabel("전체상품: -")
        self.badge_all_products.setProperty("badge", True)
        badges_row.addWidget(self.badge_all_products)

        badges_row.addStretch()
        probe_layout.addLayout(badges_row)

        # All-products page section
        all_products_section = QHBoxLayout()
        all_products_section.setSpacing(8)
        all_products_label = QLabel("전체상품 페이지:")
        all_products_label.setProperty("caption", True)
        all_products_section.addWidget(all_products_label)
        self.all_products_auto_label = QLabel("(분석 후 표시)")
        self.all_products_auto_label.setProperty("caption", True)
        all_products_section.addWidget(self.all_products_auto_label)
        self.all_products_pick_btn = QPushButton("브라우저에서 선택")
        self.all_products_pick_btn.setToolTip("전체상품 페이지 링크를 브라우저에서 직접 선택합니다.")
        self.all_products_pick_btn.clicked.connect(self._on_pick_all_products)
        all_products_section.addWidget(self.all_products_pick_btn)
        self.all_products_confirmed_label = QLabel("")
        self.all_products_confirmed_label.setProperty("caption", True)
        all_products_section.addWidget(self.all_products_confirmed_label, stretch=1)
        probe_layout.addLayout(all_products_section)

        # Categories table
        cat_label = QLabel("📂 발견된 카테고리")
        cat_label.setProperty("section", True)
        probe_layout.addWidget(cat_label)

        self.probe_cat_table = QTableWidget(0, 2, self)
        self.probe_cat_table.setHorizontalHeaderLabels(["카테고리명", "주소"])
        self.probe_cat_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.probe_cat_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.probe_cat_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.probe_cat_table.setMaximumHeight(200)
        self.probe_cat_table.setAlternatingRowColors(True)
        self.probe_cat_table.setToolTip("사이트에서 발견된 전체 카테고리 목록입니다.")
        probe_layout.addWidget(self.probe_cat_table)

        # Sample products table with thumbnails
        prod_label = QLabel("🔗 샘플 상품")
        prod_label.setProperty("section", True)
        probe_layout.addWidget(prod_label)

        self.probe_product_table = QTableWidget(0, 2, self)
        self.probe_product_table.setHorizontalHeaderLabels(["상품 이미지", "상품명"])
        self.probe_product_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.probe_product_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.probe_product_table.setColumnWidth(0, 60)
        self.probe_product_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.probe_product_table.setMaximumHeight(250)
        self.probe_product_table.setAlternatingRowColors(True)
        self.probe_product_table.setToolTip("사이트에서 발견된 샘플 상품입니다. 이미지와 이름으로 표시됩니다.")
        probe_layout.addWidget(self.probe_product_table)

        # Browser picker row for probe stage
        probe_pick_row = QHBoxLayout()
        probe_pick_row.setSpacing(8)
        self.probe_field_combo = QComboBox()
        for label, path in HINT_FIELD_CHOICES:
            self.probe_field_combo.addItem(label, path)
        self.probe_field_combo.setToolTip("브라우저에서 선택할 필드를 고르세요.")
        probe_pick_row.addWidget(self.probe_field_combo)
        self.probe_pick_btn = QPushButton("브라우저에서 선택")
        self.probe_pick_btn.setToolTip("선택한 필드를 브라우저에서 직접 클릭하여 매핑합니다.")
        self.probe_pick_btn.clicked.connect(self._on_probe_pick_element)
        probe_pick_row.addWidget(self.probe_pick_btn)
        probe_pick_row.addStretch()
        probe_layout.addLayout(probe_pick_row)

        # Collection estimate section
        estimate_label = QLabel("📊 수집 예상 정보")
        estimate_label.setProperty("section", True)
        probe_layout.addWidget(estimate_label)

        estimate_frame = QFrame()
        estimate_frame.setProperty("cardInset", True)
        estimate_layout = QVBoxLayout(estimate_frame)
        estimate_layout.setContentsMargins(16, 12, 16, 12)
        estimate_layout.setSpacing(6)

        self.estimate_info_label = QLabel("분석 후 예상 수집 정보가 표시됩니다.")
        self.estimate_info_label.setWordWrap(True)
        self.estimate_info_label.setProperty("caption", True)
        estimate_layout.addWidget(self.estimate_info_label)

        probe_layout.addWidget(estimate_frame)

        # Recognition checklist
        checklist_label = QLabel("✓ 인식 항목")
        checklist_label.setProperty("section", True)
        probe_layout.addWidget(checklist_label)

        self.checklist_table = QTableWidget(0, 3, self)
        self.checklist_table.setHorizontalHeaderLabels(["항목", "상태", "상세"])
        self.checklist_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.checklist_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.checklist_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.checklist_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.checklist_table.setMaximumHeight(200)
        self.checklist_table.setAlternatingRowColors(True)
        probe_layout.addWidget(self.checklist_table)

        self._probe_summary = QLabel("")
        self._probe_summary.setProperty("caption", True)
        self._probe_summary.setWordWrap(True)
        probe_layout.addWidget(self._probe_summary)

        self.body_layout().addWidget(self.probe_result_card)

    # --- 3단계: AI 자동 분석 ---

    def _build_ai_card(self) -> None:
        ai_card, ai_layout = _card(
            "3단계: AI 자동 분석",
            "분석된 사이트 구조를 바탕으로 AI가 상품 수집 설정을 자동으로 생성합니다.",
        )

        ai_btn_row = QHBoxLayout()
        ai_btn_row.setSpacing(10)

        self.generate_btn = QPushButton("AI로 수집 설정 생성")
        self.generate_btn.setEnabled(False)
        self.generate_btn.setToolTip(
            "분석된 사이트 구조를 바탕으로 AI가 상품 수집 설정(YAML)을 자동 생성합니다.\n"
            "설정에 사용할 LLM API 키가 필요합니다. (설정 탭에서 입력)"
        )
        self.generate_btn.clicked.connect(self._on_generate)
        ai_btn_row.addWidget(self.generate_btn)

        self.save_btn = QPushButton("4단계: 설정 저장")
        self.save_btn.setEnabled(False)
        self.save_btn.setToolTip("생성된 수집 설정을 저장하여 이후 상품 수집에 사용합니다.")
        self.save_btn.clicked.connect(self._on_save)
        ai_btn_row.addWidget(self.save_btn)

        ai_btn_row.addStretch()
        ai_layout.addLayout(ai_btn_row)

        modified_row = QHBoxLayout()
        self.modified_fields_label = QLabel("수정한 필드: 없음")
        self.modified_fields_label.setProperty("caption", True)
        modified_row.addWidget(self.modified_fields_label)
        self.reset_modified_btn = QPushButton("수정 초기화")
        self.reset_modified_btn.setEnabled(False)
        self.reset_modified_btn.clicked.connect(self._clear_mapping_hints)
        modified_row.addWidget(self.reset_modified_btn)
        modified_row.addStretch()
        ai_layout.addLayout(modified_row)

        ai_layout.addWidget(QLabel("진행 상황"))
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(160)
        self.log_text.setPlaceholderText("분석을 실행하면 진행 상황이 여기에 표시됩니다.")
        ai_layout.addWidget(self.log_text)

        self.status_label = QLabel("대기 중")
        self.status_label.setProperty("caption", True)
        ai_layout.addWidget(self.status_label)

        self.body_layout().addWidget(ai_card)

    # --- 수집 설정 결과 카드 (매핑 + YAML 탭) ---

    def _build_result_card(self) -> None:
        result_card, result_layout = _card(
            "수집 설정 결과",
            "AI가 생성한 설정입니다. 시각적 매핑을 확인하고 필드 추출을 테스트하세요.",
        )

        self.result_tabs = QTabWidget()

        # -- Tab 1: 매핑 결과 --
        mapping_tab = QWidget()
        mapping_layout = QVBoxLayout(mapping_tab)
        mapping_layout.setContentsMargins(8, 12, 8, 12)
        mapping_layout.setSpacing(10)

        # A. 상품 정보 매핑 테이블
        map_title = QLabel("상품 정보 매핑")
        map_title.setProperty("section", True)
        mapping_layout.addWidget(map_title)

        self.mapping_table = QTableWidget()
        self.mapping_table.setColumnCount(5)
        self.mapping_table.setHorizontalHeaderLabels(["항목", "추출 방법", "상태", "수정", "테스트"])
        self.mapping_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.mapping_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.mapping_table.verticalHeader().setVisible(False)
        mapping_layout.addWidget(self.mapping_table)

        # B. 사이트 설정 요약
        summary_title = QLabel("사이트 설정 요약")
        summary_title.setProperty("section", True)
        mapping_layout.addWidget(summary_title)

        sub_grid = QHBoxLayout()
        sub_grid.setSpacing(8)

        self._cat_inset, self.cat_label = _make_inset_frame("카테고리 설정")
        sub_grid.addWidget(self._cat_inset)

        self._pag_inset, self.pag_label = _make_inset_frame("페이지네이션")
        sub_grid.addWidget(self._pag_inset)

        mapping_layout.addLayout(sub_grid)

        sub_grid2 = QHBoxLayout()
        sub_grid2.setSpacing(8)

        self._login_inset, self.login_summary_label = _make_inset_frame("로그인 설정")
        sub_grid2.addWidget(self._login_inset)

        self._opt_inset, self.opt_label = _make_inset_frame("옵션 설정")
        sub_grid2.addWidget(self._opt_inset)

        mapping_layout.addLayout(sub_grid2)

        # C. 테스트 결과
        test_title = QLabel("테스트 결과")
        test_title.setProperty("section", True)
        mapping_layout.addWidget(test_title)

        self.test_results_table = QTableWidget()
        self.test_results_table.setColumnCount(3)
        self.test_results_table.setHorizontalHeaderLabels(["항목", "추출된 값", "상태"])
        self.test_results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.test_results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.test_results_table.verticalHeader().setVisible(False)
        self.test_results_table.setMaximumHeight(200)
        mapping_layout.addWidget(self.test_results_table)

        self.validation_status_label = QLabel("검증 상태: 테스트 필요")
        self.validation_status_label.setProperty("caption", True)
        mapping_layout.addWidget(self.validation_status_label)
        self.validation_failed_label = QLabel("")
        self.validation_failed_label.setProperty("caption", True)
        self.validation_failed_label.setWordWrap(True)
        mapping_layout.addWidget(self.validation_failed_label)

        # D. 테스트 버튼
        test_btn_row = QHBoxLayout()
        test_btn_row.setSpacing(10)

        self.test_all_btn = QPushButton("전체 테스트 실행")
        self.test_all_btn.setEnabled(False)
        self.test_all_btn.clicked.connect(self._on_test_all)
        test_btn_row.addWidget(self.test_all_btn)

        self.sample_test_btn = QPushButton("3개 상품 샘플 테스트")
        self.sample_test_btn.setEnabled(False)
        self.sample_test_btn.clicked.connect(lambda: self._test_sample_products(3))
        test_btn_row.addWidget(self.sample_test_btn)

        test_btn_row.addStretch()
        mapping_layout.addLayout(test_btn_row)

        mapping_layout.addStretch()
        self.result_tabs.addTab(mapping_tab, "매핑 결과")

        # -- Tab 2: YAML 직접 편집 (고급) --
        yaml_tab = QWidget()
        yaml_layout = QVBoxLayout(yaml_tab)
        yaml_layout.setContentsMargins(8, 12, 8, 12)
        yaml_layout.setSpacing(10)

        yaml_cap = QLabel("설정 내용 (YAML)")
        yaml_cap.setProperty("caption", True)
        yaml_layout.addWidget(yaml_cap)

        self.yaml_edit = QPlainTextEdit()
        font = QFont("Menlo", 11)
        self.yaml_edit.setFont(font)
        self.yaml_edit.setPlaceholderText("AI 분석을 실행하면 설정이 여기에 표시됩니다.")
        self.yaml_edit.textChanged.connect(self._on_yaml_text_changed)
        yaml_layout.addWidget(self.yaml_edit)

        summary_cap = QLabel("분석 요약")
        summary_cap.setProperty("caption", True)
        yaml_layout.addWidget(summary_cap)

        self.summary_text = QPlainTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setMaximumHeight(200)
        self.summary_text.setPlaceholderText("사이트 분석 요약이 여기에 표시됩니다.")
        yaml_layout.addWidget(self.summary_text)

        self.result_tabs.addTab(yaml_tab, "YAML 직접 편집 (고급)")

        result_layout.addWidget(self.result_tabs)
        self.body_layout().addWidget(result_card)

    # ---------- YAML text changed → update mapping ----------

    def _on_yaml_text_changed(self) -> None:
        yaml_text = self.yaml_edit.toPlainText().strip()
        current_hash = self._yaml_hash(yaml_text)
        if self._last_validation_yaml_hash and current_hash != self._last_validation_yaml_hash:
            self._mark_validation_stale("YAML 변경됨")
        if yaml_text and hasattr(self, "generate_btn"):
            self.generate_btn.setText("AI로 재생성")
        elif hasattr(self, "generate_btn"):
            self.generate_btn.setText("AI로 수집 설정 생성")
        if yaml_text:
            self._update_mapping_table(yaml_text)

    # ---------- Login toggle ----------

    def _on_login_toggled(self, checked: bool) -> None:
        self.login_url_edit.setVisible(checked)
        self._login_url_label.setVisible(checked)
        self.login_id_edit.setVisible(checked)
        self._login_id_label.setVisible(checked)
        self.login_pw_edit.setVisible(checked)
        self._login_pw_label.setVisible(checked)

    # ---------- Probe ----------

    def _on_probe(self) -> None:
        name = self.name_edit.text().strip()
        main_url = self.main_url_edit.text().strip()
        if not name or not main_url:
            QMessageBox.warning(self, "입력 필요", "도매처명과 메인 주소를 입력하세요.")
            return

        self.log_text.clear()
        self.summary_text.clear()
        self._mapping_hints.clear()
        self._clear_validation_state(stale=False)
        self._refresh_modified_fields_label()
        self.log_text.appendPlainText(f"사이트 구조 분석 시작: {main_url}")
        self.probe_btn.setEnabled(False)
        self.cancel_probe_btn.setEnabled(True)
        self.status_label.setText("분석 중... 잠시만 기다려 주세요.")

        listing_url = self.listing_url_edit.text().strip() or None
        detail_url = self.detail_url_edit.text().strip() or None

        login_url = self.login_url_edit.text().strip() if self.login_checkbox.isChecked() else None
        username = self.login_id_edit.text().strip() if self.login_checkbox.isChecked() else None
        password = self.login_pw_edit.text() if self.login_checkbox.isChecked() else None

        # Save credentials to keyring for later use by crawler
        if login_url and username and password:
            slug = _slugify(self.name_edit.text().strip())
            if slug:
                save_supplier_credentials(slug, username, password)

        worker = ProbeWorker(ProbeRequest(
            main_url, listing_url, detail_url, login_url, username, password
        ))
        worker.progress.connect(self._on_probe_progress)
        worker.finished.connect(self._on_probe_finished)
        worker.error.connect(self._on_probe_error)
        worker.cancelled.connect(lambda: self._on_probe_error("취소됨"))
        worker.start()
        self._probe_worker = worker

    def _on_cancel_probe(self) -> None:
        self.log_text.appendPlainText("취소 요청됨. 브라우저 종료 중...")
        self.cancel_probe_btn.setEnabled(False)
        self.status_label.setText("취소 중...")
        if self._probe_worker:
            self._probe_worker.requestInterruption()

    def _on_probe_progress(self, msg: str) -> None:
        self.log_text.appendPlainText(msg)

    def _on_probe_finished(self, result: ProbeResult) -> None:
        self._probe_result = result
        self.probe_btn.setEnabled(True)
        self.cancel_probe_btn.setEnabled(False)
        self.generate_btn.setEnabled(True)
        self.status_label.setText("구조 분석 완료. AI 수집 설정 생성을 누르세요.")

        # Summary text (in YAML advanced tab)
        lines = [
            f"사이트 주소: {result.final_url}",
            f"문자 인코딩: {result.encoding}",
            f"로그인 필요: {'예' if result.needs_login else '아니오'}",
            f"전체 상품 메뉴: {'있음' if result.has_all_products else '없음'}",
            f"발견된 카테고리: {len(result.categories)}개",
            f"발견된 상품 링크: {len(result.sample_products)}개",
            f"동적 요청(AJAX): {len(result.ajax_requests)}개",
            f"카테고리 메뉴 HTML: {len(result.category_menu_html)}자",
            f"목록 페이지 HTML: {len(result.listing_html)}자",
            f"상세 페이지 HTML: {len(result.detail_html)}자",
        ]
        self.summary_text.setPlainText("\n".join(lines))

        self.log_text.appendPlainText("\n구조 분석 완료")

        # Populate probe result card
        self._populate_probe_result_card(result)

    def _populate_probe_result_card(self, result: ProbeResult) -> None:
        self.probe_result_card.setVisible(True)

        # Badges
        self.badge_login.setText(f"로그인: {'필요' if result.needs_login else '불필요'}")
        self.badge_encoding.setText(f"인코딩: {result.encoding}")
        self.badge_all_products.setText(f"전체상품: {'있음' if result.has_all_products else '없음'}")
        if result.has_all_products:
            all_products_url = getattr(result, 'has_all_products_url', '') or ''
            self.all_products_auto_label.setText(f"자동 인식: 있음" + (f" ({all_products_url})" if all_products_url else ""))
        else:
            self.all_products_auto_label.setText("자동 인식: 없음")

        # Category tree -> now uses QTableWidget
        categories = result.categories or []
        self.probe_cat_table.setRowCount(len(categories))
        for row, cat in enumerate(categories):
            self.probe_cat_table.setItem(row, 0, QTableWidgetItem(cat.get("name", "")))
            self.probe_cat_table.setItem(row, 1, QTableWidgetItem(cat.get("url", "")))

        # Sample products table with thumbnails
        products = result.sample_products or []
        self.probe_product_table.setRowCount(len(products))
        for row, prod in enumerate(products):
            # Image will be loaded async
            image_url = prod.get("image_url", "")
            if image_url:
                self._load_image_async(image_url, self.probe_product_table, row)
            else:
                no_img_label = QLabel("(이미지 없음)")
                no_img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                no_img_label.setProperty("caption", True)
                self.probe_product_table.setCellWidget(row, 0, no_img_label)

            self.probe_product_table.setItem(row, 1, QTableWidgetItem(prod.get("name", "(이름 없음)")))

        self._probe_summary.setText(
            f"카테고리 {len(categories)}개, 상품 {len(products)}개, AJAX 요청 {len(result.ajax_requests)}개"
        )

        # Populate collection estimate
        total_count = (getattr(result, "total_product_count", None) or 0)
        per_page = (getattr(result, "products_per_page", None) or 0)
        total_pages = (getattr(result, "total_pages", None) or 0)
        cat_count = len(categories)

        # Calculate estimated time (rough estimate: 2 seconds per product, 3 seconds per page)
        if total_count > 0:
            est_minutes = max(1, (total_count * 2 + total_pages * 3) // 60)
            est_text = (
                f"총 상품 수: {total_count}개\n"
                f"페이지당: {per_page}개 | 총 페이지: {total_pages}페이지\n"
                f"카테고리 수: {cat_count}개\n"
                f"⏱ 예상 소요 시간: 약 {est_minutes}분"
            )
        else:
            est_text = (
                f"카테고리 수: {cat_count}개\n"
                f"총 상품 수: (확인되지 않음)\n"
                f"페이지당: {per_page}개" if per_page else ""
            )
        self.estimate_info_label.setText(est_text)
        self.estimate_info_label.setProperty("caption", False)

        # Populate recognition checklist
        checklist_items = []

        # Categories
        if cat_count > 0:
            checklist_items.append(("카테고리", "✓ 인식됨", f"{cat_count}개 발견"))
        else:
            checklist_items.append(("카테고리", "⚠ 미인식", "카테고리 메뉴를 찾지 못했습니다"))

        # Pagination
        if total_pages and total_pages > 0:
            checklist_items.append(("페이지네이션", "✓ 인식됨", f"페이지 번호 방식, {total_pages}페이지"))
        else:
            checklist_items.append(("페이지네이션", "⚠ 미인식", "페이지 구조를 파악하지 못했습니다"))

        # Product links
        if len(products) > 0:
            checklist_items.append(("상품 링크", "✓ 인식됨", f"{len(products)}개 샘플 발견"))
        else:
            checklist_items.append(("상품 링크", "⚠ 미인식", "상품 링크를 찾지 못했습니다"))

        # Product name
        detail_html = getattr(result, "detail_html", None) or ""
        if detail_html and "MK_brandname" in detail_html:
            checklist_items.append(("상품명", "✓ 인식됨", "#MK_brandname"))
        elif detail_html:
            checklist_items.append(("상품명", "⚠ 미확인", "프로브에서 확인 필요"))
        else:
            checklist_items.append(("상품명", "✗ 미인식", "상세 페이지 분석 실패"))

        # Price
        if detail_html and ("mk_price" in detail_html or "price" in detail_html.lower()):
            checklist_items.append(("가격", "✓ 인식됨", ".mk_price (로그인 후 표시)"))
        else:
            checklist_items.append(("가격", "⚠ 미확인", "로그인 후 확인 필요"))

        # Images
        if detail_html and "shopimages" in detail_html:
            checklist_items.append(("이미지", "✓ 인식됨", "img[src*='shopimages']"))
        else:
            checklist_items.append(("이미지", "⚠ 미확인", "이미지 구조 확인 필요"))

        # Status
        si = getattr(result, "status_indicators", None) or {}
        if si:
            if si.get("has_explicit_status"):
                checklist_items.append(("판매 상태", "✓ 인식됨", "명시적 상태 표시 있음"))
            elif si.get("has_soldout_image"):
                checklist_items.append(("판매 상태", "✓ 인식됨", "품절 이미지로 판단 가능"))
            elif si.get("has_cart_button"):
                maxq = si.get("maxq_value", "?")
                checklist_items.append(("판매 상태", "⚠ 간접 판단", f"장바구니 버튼 + maxq={maxq}로 유추 가능"))
            else:
                checklist_items.append(("판매 상태", "✗ 미인식", "상태 표시를 찾지 못했습니다"))
        else:
            checklist_items.append(("판매 상태", "⚠ 미확인", "상세 페이지 분석 필요"))

        # Origin
        if detail_html and ("원산지" in detail_html or "origin" in detail_html.lower()):
            checklist_items.append(("원산지", "✓ 인식됨", "상세 페이지에 원산지 정보 있음"))
        else:
            checklist_items.append(("원산지", "⚠ 미확인", "원산지 정보 확인 필요"))

        # Options
        ajax_requests = getattr(result, "ajax_requests", None) or []
        if ajax_requests:
            checklist_items.append(("옵션", "⚠ 동적 로딩", f"AJAX 요청 {len(ajax_requests)}개 감지"))
        else:
            checklist_items.append(("옵션", "ℹ 정적", "동적 옵션 로딩 미감지"))

        self.checklist_table.setRowCount(len(checklist_items))
        for row, (item, status, detail) in enumerate(checklist_items):
            self.checklist_table.setItem(row, 0, QTableWidgetItem(item))

            status_item = QTableWidgetItem(status)
            if "✓" in status:
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            elif "⚠" in status:
                status_item.setForeground(Qt.GlobalColor.darkYellow)
            elif "✗" in status:
                status_item.setForeground(Qt.GlobalColor.red)
            self.checklist_table.setItem(row, 1, status_item)

            self.checklist_table.setItem(row, 2, QTableWidgetItem(detail))

    def _load_image_async(self, url: str, table: QTableWidget, row: int) -> None:
        """Load an image asynchronously and set it in the table cell."""
        if not url:
            return
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QPixmap
            from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

            if not hasattr(self, '_nam'):
                from PySide6.QtCore import QObject
                self._nam = QNetworkAccessManager(self)

            request = QNetworkRequest(QUrl(url))
            reply = self._nam.get(request)

            def on_finished():
                try:
                    data = reply.readAll()
                    pixmap = QPixmap()
                    pixmap.loadFromData(data)
                    if not pixmap.isNull():
                        scaled = pixmap.scaled(50, 50, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                        label = QLabel()
                        label.setPixmap(scaled)
                        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        table.setCellWidget(row, 0, label)
                except Exception:
                    pass
                reply.deleteLater()

            reply.finished.connect(on_finished)
        except Exception:
            pass

    def _on_probe_error(self, msg: str) -> None:
        self.probe_btn.setEnabled(True)
        self.cancel_probe_btn.setEnabled(False)
        self.status_label.setText(f"오류: {msg}")
        self.log_text.appendPlainText(f"\n오류 발생: {msg}")
        QMessageBox.critical(self, "분석 오류", f"사이트 분석 중 오류가 발생했습니다:\n\n{msg}")

    # ---------- Mapping hint helpers ----------

    def _key_to_field_path(self, key: str) -> str:
        """Map product field key to allowed hint field_path."""
        mapping = {
            "raw_product_name": "adapter.product.raw_product_name",
            "supplier_product_code": "adapter.product.supplier_product_code",
            "supplier_product_id": "adapter.product.supplier_product_id",
            "supply_price": "adapter.product.supply_price",
            "origin": "adapter.product.origin",
            "main_image_url": "adapter.product.main_image_url",
            "detail_content": "adapter.product.detail_content",
            "supplier_status": "adapter.product.supplier_status",
        }
        return mapping.get(key, "")

    def _get_hint_for_field(self, key: str) -> MappingHint | None:
        field_path = self._key_to_field_path(key)
        for hint in self._mapping_hints:
            if hint.field_path == field_path:
                return hint
        return None

    def _refresh_modified_fields_label(self) -> None:
        if not hasattr(self, "modified_fields_label"):
            return
        field_keys = {hint.field_path for hint in self._mapping_hints}
        label_by_path = {path: label for label, path in HINT_FIELD_CHOICES}
        label_by_path["adapter.categories.all_products.url"] = "전체상품"
        names = [label_by_path.get(fp, fp.split(".")[-1]) for fp in sorted(field_keys)]
        if names:
            self.modified_fields_label.setText(f"수정한 필드: {', '.join(names)}")
            self.reset_modified_btn.setEnabled(True)
        else:
            self.modified_fields_label.setText("수정한 필드: 없음")
            self.reset_modified_btn.setEnabled(False)

    def _clear_mapping_hints(self) -> None:
        self._mapping_hints.clear()
        self._mark_validation_stale("힌트 전체 삭제")
        self._refresh_modified_fields_label()
        if hasattr(self, "all_products_confirmed_label"):
            self.all_products_confirmed_label.setText("")
        yaml_text = self.yaml_edit.toPlainText().strip()
        if yaml_text:
            self._update_mapping_table(yaml_text)

    def _add_hint_from_pick(self, field_path: str, defaults: dict) -> None:
        """Add or update a locked MappingHint for the given field after browser pick."""
        selector = defaults.get("selector", "")
        if not selector:
            return
        page_kind = "listing" if field_path == "adapter.listing.product_link" else "product"
        try:
            hint = MappingHint(
                page_kind=page_kind,
                field_path=field_path,
                chosen_selector=selector,
                url=defaults.get("url", ""),
                attribute=defaults.get("attribute") or None,
                html=defaults.get("html") if defaults.get("html") else None,
                transform=defaults.get("transform") or None,
                observed_value=defaults.get("observed_value", ""),
                locked=True,
            )
        except ValueError:
            return
        # Replace existing hint for same field_path, or append
        for i, existing in enumerate(self._mapping_hints):
            if existing.field_path == field_path:
                self._mapping_hints[i] = hint
                break
        else:
            self._mapping_hints.append(hint)
        self._mark_validation_stale("브라우저 선택")
        self._refresh_modified_fields_label()

    def _default_hint_url(self, field_path: str) -> str:
        if not self._probe_result:
            return self.main_url_edit.text().strip()
        if field_path in ("adapter.listing.product_link", "adapter.categories.all_products.url"):
            return self.listing_url_edit.text().strip() or self._probe_result.final_url or self._probe_result.main_url
        return (self._probe_result.sample_links[0] if self._probe_result.sample_links else "") or self.detail_url_edit.text().strip() or self._probe_result.final_url or self._probe_result.main_url

    def _set_mapping_table_buttons_enabled(self, enabled: bool) -> None:
        """Enable/disable picker buttons in both probe card and mapping table."""
        self.probe_field_combo.setEnabled(enabled)
        self.probe_pick_btn.setEnabled(enabled)
        self.all_products_pick_btn.setEnabled(enabled)
        for row in range(self.mapping_table.rowCount()):
            for col in (3, 4):
                widget = self.mapping_table.cellWidget(row, col)
                if widget and isinstance(widget, QPushButton):
                    widget.setEnabled(enabled)

    def _on_pick_all_products(self) -> None:
        target_url = self._default_hint_url("adapter.categories.all_products.url")
        if not target_url:
            QMessageBox.warning(self, "선택 불가", "브라우저에서 열 URL이 없습니다.")
            return
        field_path = "adapter.categories.all_products.url"
        login_url, username, password = self._get_test_credentials()
        login_config = self._build_login_config_from_yaml()
        if login_config and login_config.get("login_url") and not login_url:
            login_url = login_config["login_url"]
        self._set_mapping_table_buttons_enabled(False)
        self.log_text.appendPlainText(f"전체상품 페이지 브라우저 선택 시작: {target_url}")
        worker = PickerWorker(PickerRequest(field_path, target_url, login_url, username, password, login_config))
        worker.finished.connect(self._on_picker_finished)
        worker.error.connect(self._on_picker_error)
        worker.start()
        self._picker_worker = worker

    def _on_probe_pick_element(self) -> None:
        field_path = self.probe_field_combo.currentData()
        target_url = self._default_hint_url(field_path)
        if not target_url:
            QMessageBox.warning(self, "선택 불가", "브라우저에서 열 URL이 없습니다. 샘플 링크나 상품 URL을 확인하세요.")
            return
        login_url, username, password = self._get_test_credentials()
        login_config = self._build_login_config_from_yaml()
        if login_config and login_config.get("login_url") and not login_url:
            login_url = login_config["login_url"]
        self._set_mapping_table_buttons_enabled(False)
        self.log_text.appendPlainText(f"프로브 단계 브라우저 선택 시작 ({field_path}): {target_url}")
        worker = PickerWorker(PickerRequest(field_path, target_url, login_url, username, password, login_config))
        worker.finished.connect(self._on_picker_finished)
        worker.error.connect(self._on_picker_error)
        worker.start()
        self._picker_worker = worker

    def _on_pick_element_for_field(self, field_path: str) -> None:
        target_url = self._default_hint_url(field_path)
        if not target_url:
            QMessageBox.warning(self, "선택 불가", "브라우저에서 열 URL이 없습니다. 샘플 링크나 상품 URL을 확인하세요.")
            return
        login_url, username, password = self._get_test_credentials()
        login_config = self._build_login_config_from_yaml()
        if login_config and login_config.get("login_url") and not login_url:
            login_url = login_config["login_url"]
        self._set_mapping_table_buttons_enabled(False)
        self.pick_element_field_path = field_path
        self.log_text.appendPlainText(f"브라우저 선택 시작 ({field_path}): {target_url}")
        worker = PickerWorker(PickerRequest(field_path, target_url, login_url, username, password, login_config))
        worker.finished.connect(self._on_picker_finished)
        worker.error.connect(self._on_picker_error)
        worker.start()
        self._picker_worker = worker

    def _on_picker_finished(self, picked: PickedElement, field_path: str) -> None:
        self._set_mapping_table_buttons_enabled(True)
        defaults = suggest_defaults_for_field(field_path, picked)
        if picked.url:
            defaults["url"] = picked.url
        self._add_hint_from_pick(field_path, defaults)
        label = {path: label for label, path in HINT_FIELD_CHOICES}.get(field_path, "전체상품 페이지")
        self.log_text.appendPlainText(f"{label} 선택 완료: {defaults.get('selector', picked.selector)}")
        # Update all-products confirmed label if applicable
        if field_path == "adapter.categories.all_products.url":
            confirmed_url = defaults.get("selector", defaults.get("observed_value", ""))
            self.all_products_confirmed_label.setText(f"✓ 사용자 확인: {confirmed_url}")
        yaml_text = self.yaml_edit.toPlainText().strip()
        if yaml_text:
            self._update_mapping_table(yaml_text)

    def _on_picker_error(self, msg: str) -> None:
        self._set_mapping_table_buttons_enabled(True)
        self.log_text.appendPlainText(f"브라우저 선택 오류: {msg}")
        QMessageBox.warning(self, "브라우저 선택 오류", msg)

    # ---------- Validation state ----------

    def _yaml_hash(self, text: str | None = None) -> str:
        payload = self.yaml_edit.toPlainText().strip() if text is None else text.strip()
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _clear_validation_state(self, stale: bool = True) -> None:
        self._last_test_raw_results = {}
        self._last_validation_yaml_hash = None
        self._last_validation_urls = []
        self._last_validation_summary = None
        self._validation_stale = stale
        self._render_validation_summary()

    def _mark_validation_stale(self, reason: str = "") -> None:
        if self._last_validation_summary:
            self._validation_stale = True
            self._render_validation_summary()

    def _render_validation_summary(self) -> None:
        if not hasattr(self, "validation_status_label"):
            return
        summary = self._last_validation_summary
        if not summary or not summary.has_validation:
            self.validation_status_label.setText("검증 상태: 테스트 필요")
            self.validation_failed_label.setText("저장 전 3개 상품 샘플 테스트를 권장합니다.")
            return
        if self._validation_stale:
            self.validation_status_label.setText("검증 상태: 확인 필요 (테스트 후 변경됨)")
        elif summary.failed_key_fields:
            self.validation_status_label.setText("검증 상태: 확인 필요")
        else:
            self.validation_status_label.setText(f"검증 상태: 저장 가능 ({summary.total_samples}개 샘플)")
        if summary.failed_key_fields:
            labels = [FIELD_LABELS_KO.get(f, "상품코드 또는 상품ID") for f in summary.failed_key_fields]
            self.validation_failed_label.setText("실패 필드: " + ", ".join(labels) + " · 브라우저에서 선택 → 힌트 추가 → AI 재생성을 권장합니다.")
        else:
            self.validation_failed_label.setText("필수 필드 검증 통과")

    def _build_login_config_from_yaml(self) -> dict[str, str] | None:
        yaml_text = self.yaml_edit.toPlainText().strip()
        if not yaml_text:
            return None
        try:
            adapter = load_adapter_from_text(yaml_text)
            login = adapter.adapter.login
            if not login.required or not login.login_url:
                return None
            cfg: dict[str, str] = {"login_url": login.login_url}
            fields = login.fields
            if fields:
                cfg["id_selector"] = fields.id
                cfg["password_selector"] = fields.password
            if login.submit:
                cfg["submit_selector"] = login.submit
            if login.success_indicator:
                cfg["success_indicator"] = login.success_indicator
            return cfg if len(cfg) > 1 else None
        except Exception:
            return None

    # ---------- AI generate ----------

    def _on_generate(self) -> None:
        if not self._probe_result:
            QMessageBox.warning(self, "분석 필요", "먼저 사이트 구조 분석을 실행하세요.")
            return

        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "입력 필요", "도매처명을 입력하세요.")
            return

        config = load_config()
        self.log_text.appendPlainText(f"\nAI 수집 설정 생성 중... (제공자: {config.llm_provider})")
        self.generate_btn.setEnabled(False)
        self.status_label.setText("AI 생성 중... 약 10~30초 소요됩니다.")

        probe = self._probe_result
        mapping_hints = list(self._mapping_hints)

        worker = GenerateWorker(GenerateRequest(
            probe, name, config.llm_provider, config.auto_fallback_enabled, mapping_hints
        ))
        worker.finished.connect(self._on_generate_finished)
        worker.error.connect(self._on_generate_error)
        worker.progress.connect(lambda msg: self.log_text.appendPlainText(msg))
        worker.start()
        self._generate_worker = worker

    def _on_generate_finished(self, yaml_text: str, provider: str, retries: int) -> None:
        self.yaml_edit.setPlainText(yaml_text)
        self._clear_validation_state(stale=True)
        self.generate_btn.setEnabled(True)
        self.generate_btn.setText("AI로 재생성")
        self.save_btn.setEnabled(True)
        self.test_all_btn.setEnabled(True)
        self.sample_test_btn.setEnabled(True)
        self.status_label.setText(f"생성 완료 (AI: {provider}). 매핑 표에서 틀린 부분을 브라우저에서 선택하여 수정한 후 AI로 재생성하세요.")
        self.log_text.appendPlainText(f"수집 설정 생성 완료 (AI: {provider})")
        self._update_mapping_table(yaml_text)
        self._refresh_modified_fields_label()

    def _on_generate_error(self, msg: str) -> None:
        self.generate_btn.setEnabled(True)
        self.status_label.setText(f"생성 오류: {msg}")
        self.log_text.appendPlainText(f"\n생성 오류: {msg}")
        QMessageBox.critical(self, "AI 생성 오류", f"AI 설정 생성 중 오류가 발생했습니다:\n\n{msg}")

    # ---------- Save ----------

    def _on_save(self) -> None:
        yaml_text = self.yaml_edit.toPlainText().strip()
        if not yaml_text:
            QMessageBox.warning(self, "설정 없음", "저장할 설정이 없습니다.")
            return

        decision = get_save_gate_decision(self._last_validation_summary, self._validation_stale or self._yaml_hash(yaml_text) != self._last_validation_yaml_hash)
        if decision.should_warn:
            details = ""
            if decision.failed_fields:
                labels = [FIELD_LABELS_KO.get(f, "상품코드 또는 상품ID") for f in decision.failed_fields]
                details = "\n실패 필드: " + ", ".join(labels)
            confirm = QMessageBox.warning(
                self,
                "검증 확인 필요",
                f"{decision.message}{details}\n\n그래도 저장하시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

        name = self.name_edit.text().strip()
        slug = _slugify(name)
        if not slug:
            QMessageBox.warning(self, "이름 오류", "도매처명에 영문 또는 숫자가 포함되어야 합니다.")
            return

        try:
            load_adapter_from_text(yaml_text)
        except Exception as exc:
            confirm = QMessageBox.question(
                self,
                "설정 검증 실패",
                f"설정 검증에 실패했습니다:\n{exc}\n\n그래도 저장하시겠습니까?",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

        path = save_adapter(slug, yaml_text)
        QMessageBox.information(self, "저장 완료", f"수집 설정이 저장되었습니다:\n{path.name}")
        self.status_label.setText(f"저장됨: {path.name}")
        self.log_text.appendPlainText(f"\n설정 저장 완료: {path}")

    # ---------- Mapping table ----------

    def _update_mapping_table(self, yaml_text: str) -> None:
        """Parse YAML and update the visual mapping table with per-row picker buttons."""
        try:
            adapter = load_adapter_from_text(yaml_text)

            # Update product field table
            mappings = get_product_field_mappings(adapter)
            self.mapping_table.setRowCount(len(mappings))
            for row, m in enumerate(mappings):
                self.mapping_table.setItem(row, 0, QTableWidgetItem(m["label"]))
                selector_display = m["selector"] if m["selector"] else "(미설정)"
                # Show hint-modified selector if exists
                field_key = m["key"]
                hint = self._get_hint_for_field(field_key)
                if hint:
                    selector_display = f"🔒 {hint.chosen_selector}"
                self.mapping_table.setItem(row, 1, QTableWidgetItem(selector_display))

                status_map = {"ok": "✓ 인식", "missing": "⚠️ 없음", "empty": "⚠️ 없음"}
                status_text = status_map.get(m["status"], "?")
                status_item = QTableWidgetItem(status_text)
                if m["status"] == "ok":
                    status_item.setForeground(Qt.GlobalColor.darkGreen)
                else:
                    status_item.setForeground(Qt.GlobalColor.darkYellow)
                self.mapping_table.setItem(row, 2, status_item)

                # Column 3: "브라우저에서 선택" button for every row
                field_path = self._key_to_field_path(field_key)
                if field_path:
                    pick_btn = QPushButton("브라우저에서 선택")
                    pick_btn.setToolTip(f"{m['label']} 선택자를 브라우저에서 직접 선택합니다.")
                    pick_btn.clicked.connect(lambda checked, fp=field_path: self._on_pick_element_for_field(fp))
                    self.mapping_table.setCellWidget(row, 3, pick_btn)
                else:
                    self.mapping_table.setItem(row, 3, QTableWidgetItem("-"))

                # Column 4: "시도" test button
                test_btn = QPushButton("시도")
                test_btn.setProperty("secondary", True)
                test_btn.clicked.connect(
                    lambda checked, fk=field_key: self._on_test_single(fk)
                )
                self.mapping_table.setCellWidget(row, 4, test_btn)

            # Update summary sections
            cat = get_category_summary(adapter)
            self.cat_label.setText(
                f"방식: {cat['mode']} | 메뉴: {cat['menu_selector']}\n"
                f"URL 패턴: {cat['url_template']}\n"
                f"최대 깊이: {cat['max_depth']}단계 | 전체상품: {cat['has_all_products']}"
            )

            pag = get_pagination_summary(adapter)
            self.pag_label.setText(
                f"방식: {pag['type']} | 파라미터: {pag['page_param']} | 최대: {pag['max_pages']}페이지"
            )

            login = get_login_summary(adapter)
            if login["required"] == "필요":
                self.login_summary_label.setText(f"로그인 필요: {login['login_url']}")
            else:
                self.login_summary_label.setText("로그인 불필요")

            opt = get_options_summary(adapter)
            self.opt_label.setText(
                f"감지: {opt['detection']} | 유형: {opt['type']} | "
                f"그룹: {opt['groups_count']}개 | 의존옵션: {opt['dependent_enabled']}"
            )

            self.test_all_btn.setEnabled(True)
            self.sample_test_btn.setEnabled(True)
        except Exception as exc:
            self.log_text.appendPlainText(f"매핑 테이블 업데이트 오류: {exc}")

    # ---------- Field testing ----------

    def _get_test_credentials(self) -> tuple[str | None, str | None, str | None]:
        """Return (login_url, username, password) based on current form state."""
        if not self.login_checkbox.isChecked():
            return None, None, None
        login_url = self.login_url_edit.text().strip() or None
        username = self.login_id_edit.text().strip() or None
        password = self.login_pw_edit.text() or None
        return login_url, username, password

    def _get_test_url(self) -> str | None:
        """Return the first sample link as a full URL, or None."""
        if not self._probe_result or not self._probe_result.sample_links:
            return None
        link = self._probe_result.sample_links[0]
        if not link.startswith("http"):
            from urllib.parse import urljoin

            link = urljoin(self._probe_result.main_url, link)
        return link

    def _on_test_single(self, field_key: str) -> None:
        """Test a single field extraction."""
        test_url = self._get_test_url()
        if not test_url:
            QMessageBox.warning(self, "테스트 불가", "샘플 상품 링크가 없습니다.")
            return

        yaml_text = self.yaml_edit.toPlainText().strip()
        if not yaml_text:
            return

        login_url, username, password = self._get_test_credentials()

        self.log_text.appendPlainText(f"필드 테스트 시작: {field_key}")
        self.status_label.setText(f"테스트 중: {field_key}...")

        tested_yaml_hash = self._yaml_hash(yaml_text)
        worker = TestWorker(AdapterTestRequest(yaml_text, [test_url], tested_yaml_hash, login_url, username, password))
        worker.finished.connect(
            lambda results, h=tested_yaml_hash: self._on_test_finished(results, single_field=field_key, tested_yaml_hash=h)
        )
        worker.error.connect(self._on_test_error)
        worker.progress.connect(lambda msg: self.log_text.appendPlainText(msg))
        worker.start()
        self._test_worker = worker
    def _on_test_all(self) -> None:
        """Test all fields."""
        test_url = self._get_test_url()
        if not test_url:
            QMessageBox.warning(self, "테스트 불가", "샘플 상품 링크가 없습니다.")
            return

        yaml_text = self.yaml_edit.toPlainText().strip()
        if not yaml_text:
            return

        login_url, username, password = self._get_test_credentials()

        self.log_text.appendPlainText("전체 필드 테스트 시작...")
        self.status_label.setText("전체 테스트 중...")
        self.test_results_table.setRowCount(0)

        tested_yaml_hash = self._yaml_hash(yaml_text)
        worker = TestWorker(AdapterTestRequest(yaml_text, [test_url], tested_yaml_hash, login_url, username, password))
        worker.finished.connect(lambda results, h=tested_yaml_hash: self._on_test_finished(results, tested_yaml_hash=h))
        worker.error.connect(self._on_test_error)
        worker.progress.connect(lambda msg: self.log_text.appendPlainText(msg))
        worker.start()
        self._test_worker = worker

    def _on_test_finished(self, results: dict, single_field: str | None = None, tested_yaml_hash: str | None = None) -> None:
        """Display test results in the results table or a message box."""
        self.status_label.setText("테스트 완료")
        self._last_test_raw_results = results.pop("__raw_results__", {}) if isinstance(results, dict) else {}
        if self._last_test_raw_results:
            self._last_validation_summary = build_validation_summary(self._last_test_raw_results)
            urls: list[str] = []
            for entries in self._last_test_raw_results.values():
                for entry in entries:
                    url = str(entry.get("url") or "")
                    if url and url not in urls:
                        urls.append(url)
            self._last_validation_urls = urls
            self._last_validation_yaml_hash = tested_yaml_hash or self._yaml_hash()
            self._validation_stale = self._yaml_hash() != self._last_validation_yaml_hash
            self._render_validation_summary()

        if single_field:
            value = results.get(single_field)
            label = FIELD_LABELS_KO.get(single_field, single_field)
            if value:
                QMessageBox.information(self, "테스트 성공", f"{label}: {value[:200]}")
            else:
                QMessageBox.warning(
                    self,
                    "테스트 실패",
                    f"{label}: 값을 추출하지 못했습니다.\n선택자를 확인하세요.",
                )
            self.log_text.appendPlainText(f"  {label}: {value or '(추출 실패)'}")
        else:
            self.test_results_table.setRowCount(len(results))
            for row, (key, value) in enumerate(results.items()):
                label = FIELD_LABELS_KO.get(key, key)
                self.test_results_table.setItem(row, 0, QTableWidgetItem(label))
                self.test_results_table.setItem(
                    row, 1, QTableWidgetItem(value[:100] if value else "(추출 실패)")
                )
                ok = _test_value_success(value)
                status_item = QTableWidgetItem("✓ 성공" if ok else "✗ 실패")
                status_item.setForeground(
                    Qt.GlobalColor.darkGreen if ok else Qt.GlobalColor.red
                )
                self.test_results_table.setItem(row, 2, status_item)

            success_count = sum(1 for v in results.values() if _test_value_success(v))
            self.log_text.appendPlainText(
                f"테스트 완료: {success_count}/{len(results)} 성공"
            )

    def _on_test_error(self, msg: str) -> None:
        self.status_label.setText(f"테스트 오류: {msg}")
        self.log_text.appendPlainText(f"테스트 오류: {msg}")

    def _test_sample_products(self, count: int = 3) -> None:
        """Test extraction on multiple sample product pages."""
        if not self._probe_result or not self._probe_result.sample_links:
            QMessageBox.warning(self, "테스트 불가", "샘플 상품 링크가 없습니다.")
            return

        yaml_text = self.yaml_edit.toPlainText().strip()
        if not yaml_text:
            return

        links = self._probe_result.sample_links[:count]
        normalized = []
        from urllib.parse import urljoin

        for link in links:
            if not link.startswith("http"):
                link = urljoin(self._probe_result.main_url, link)
            normalized.append(link)

        if not normalized:
            QMessageBox.warning(self, "테스트 불가", "샘플 상품 링크가 없습니다.")
            return

        login_url, username, password = self._get_test_credentials()

        self.log_text.appendPlainText(f"샘플 {len(normalized)}개 상품 일괄 테스트 시작...")
        self.status_label.setText(f"샘플 {len(normalized)}개 테스트 중...")
        self.test_results_table.setRowCount(0)

        tested_yaml_hash = self._yaml_hash(yaml_text)
        worker = TestWorker(AdapterTestRequest(yaml_text, normalized, tested_yaml_hash, login_url, username, password))
        worker.finished.connect(lambda results, h=tested_yaml_hash: self._on_test_finished(results, tested_yaml_hash=h))
        worker.error.connect(self._on_test_error)
        worker.progress.connect(lambda msg: self.log_text.appendPlainText(msg))
        worker.start()
        self._test_worker = worker
