"""`rinne --selftest <report.txt>`: checks a built app (e.g. the Windows .exe) actually works.

Used by CI because the Windows build can't be run by hand. Windowed builds have no console,
so results go to a file; the exit code is 0 when every check passes.
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path


def run(report: str | None) -> int:
    lines: list[str] = []
    ok = True

    def check(name: str, fn) -> None:
        nonlocal ok
        try:
            detail = fn()
            lines.append(f"PASS  {name}{f' — {detail}' if detail else ''}")
        except Exception as e:  # report every failure, don't stop at the first
            ok = False
            lines.append(f"FAIL  {name} — {type(e).__name__}: {e}")
            lines.append(traceback.format_exc())

    tmp = tempfile.mkdtemp(prefix="rinne-selftest-")
    os.environ["XDG_DATA_HOME"] = str(Path(tmp) / "data")  # never touch the real library
    os.environ["XDG_CACHE_HOME"] = str(Path(tmp) / "cache")

    from PySide6.QtNetwork import QSslSocket
    from PySide6.QtWidgets import QApplication

    from . import __version__
    app = QApplication.instance() or QApplication(sys.argv[:1])
    lines.append(f"Rinne {__version__} on {sys.platform}, Python {sys.version.split()[0]}")

    def assets():
        from .gui.common import asset
        missing = [n for n in ("icon-256.png", "logo-round.png", "icon-1024.png") if not Path(asset(n)).exists()]
        if missing:
            raise FileNotFoundError(", ".join(missing))
        return "icons and logo found"

    def tls():
        if not QSslSocket.supportsSsl():
            raise RuntimeError(f"no TLS backend (available: {QSslSocket.availableBackends()})")
        return f"Qt TLS backend: {QSslSocket.activeBackend()}"

    def https():
        from .anilist import lookup
        a = lookup(1)  # Cowboy Bebop
        return f"AniList reachable ({a.title})" if a else "AniList reachable"

    def window():
        from .gui.window import MainWindow
        w = MainWindow()
        w.update_presence = lambda force=False: None
        w.show()
        for _ in range(20):
            app.processEvents()
        page = type(w.shell.currentWidget()).__name__
        w._quitting = True
        w.close()
        return f"main window opened (showing {page})"

    check("bundled assets", assets)
    check("TLS support", tls)
    check("HTTPS to AniList", https)
    check("main window", window)
    lines.append("RESULT: " + ("OK" if ok else "FAILED"))
    text = "\n".join(lines) + "\n"
    if report:
        Path(report).write_text(text, encoding="utf-8")
    elif sys.stdout is not None:
        sys.stdout.write(text)
    return 0 if ok else 1
