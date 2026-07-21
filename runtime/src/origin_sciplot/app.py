"""PySide6 application entry."""

from __future__ import annotations

import sys

from .project_paths import resources_dir


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QIcon
    except ImportError as exc:  # pragma: no cover - user-facing startup guard
        print("PySide6 is not installed. Run: python -m pip install -r requirements.txt")
        raise SystemExit(1) from exc

    from .main_window import MainWindow

    app = QApplication(sys.argv)
    icon = resources_dir() / "app_icon.png"
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    qss = resources_dir() / "qss" / "main.qss"
    if qss.is_file():
        app.setStyleSheet(qss.read_text(encoding="utf-8"))
    window = MainWindow()
    window.show()
    return app.exec()
