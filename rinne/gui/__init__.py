"""PySide6 desktop interface."""

from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from .. import APP_NAME, DISPLAY_NAME
    from .desktop import app_icon
    from .window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(DISPLAY_NAME)
    app.setDesktopFileName(APP_NAME)
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)  # the tray can keep Rinne running
    win = MainWindow()
    if not win.should_start_hidden():
        win.show()
    else:
        win.update_tray()
    app.lastWindowClosed.connect(lambda: None if win.close_keeps_running() else app.quit())
    return app.exec()
