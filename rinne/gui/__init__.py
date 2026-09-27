"""PySide6 desktop interface."""

from __future__ import annotations

import sys


def _windows_setup() -> None:
    """Group the taskbar button under Rinne (not python.exe) so it shows Rinne's icon."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Zodchi.Rinne")
    except (AttributeError, OSError):
        pass


def main() -> int:
    if "--selftest" in sys.argv:
        from ..selftest import run
        i = sys.argv.index("--selftest")
        return run(sys.argv[i + 1] if i + 1 < len(sys.argv) else None)
    if sys.platform == "win32":
        _windows_setup()

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
