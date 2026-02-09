from __future__ import annotations

import sys

from PySide6 import QtWidgets

from app.data import db
from app.theme import apply_theme
from app.ui.main_window import MainWindow
from app.utils.logging import setup_logging


def main() -> int:
    setup_logging()
    app = QtWidgets.QApplication(sys.argv)
    app.setOrganizationName("SeedScope")
    app.setApplicationName("SeedScope")
    db.init_db()
    theme_mode = db.get_setting("theme_mode", "dark") or "dark"
    apply_theme(app, theme_mode)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
