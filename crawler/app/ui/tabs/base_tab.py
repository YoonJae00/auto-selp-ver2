from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class BaseTab(QWidget):
    """Base tab with header, scrollable body, and empty-state helper."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)

        header_frame = QFrame(self)
        header_frame.setObjectName("tabHeader")
        header_frame.setStyleSheet("""
            QFrame#tabHeader {
                background-color: #ffffff;
                border-bottom: 1px solid #e5e7eb;
            }
        """)
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(28, 20, 28, 16)
        header_layout.setSpacing(4)

        self._title = QLabel(self.default_title(), header_frame)
        self._title.setProperty("heading", True)
        header_layout.addWidget(self._title)

        self._subtitle = QLabel(self.default_subtitle(), header_frame)
        self._subtitle.setProperty("subheading", True)
        self._subtitle.setWordWrap(True)
        header_layout.addWidget(self._subtitle)

        self._outer.addWidget(header_frame)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._body = QWidget(scroll)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(28, 16, 28, 20)
        self._body_layout.setSpacing(14)
        scroll.setWidget(self._body)

        self._outer.addWidget(scroll, stretch=1)

    def default_title(self) -> str:
        return "탭"

    def default_subtitle(self) -> str:
        return ""

    def body_layout(self) -> QVBoxLayout:
        return self._body_layout

    def add_stretch(self) -> None:
        self._body_layout.addStretch()

    def create_empty_label(self, message: str) -> QLabel:
        label = QLabel(message)
        label.setProperty("empty", True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label
