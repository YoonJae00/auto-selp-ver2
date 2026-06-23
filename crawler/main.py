from __future__ import annotations

import os
import sys


def _ensure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def _suppress_macos_noise() -> None:
    if sys.platform != "darwin":
        return
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts.warning=false")
    os.environ.setdefault("QT_MAC_DISABLE_NSODIUM", "1")


def main() -> None:
    _ensure_utf8()
    _suppress_macos_noise()

    from PySide6.QtWidgets import QApplication

    from app.db.session import init_db
    from app.ui.main_window import MainWindow

    init_db()
    app = QApplication(sys.argv)
    app.setApplicationName("Auto-Selp Crawler")
    app.setApplicationDisplayName("Auto-Selp Crawler")
    app.setOrganizationName("Auto-Selp")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
