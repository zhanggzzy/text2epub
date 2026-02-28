from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.controller import AppController
from app.ui_mainwindow import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    AppController(window)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

