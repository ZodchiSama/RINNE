"""Logging to a rotating file in the data folder, so problems can be reported."""

from __future__ import annotations

import logging
import platform
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import __version__
from .storage import data_dir

log = logging.getLogger("rinne")
_path: Path | None = None


def log_path() -> Path:
    return data_dir() / "rinne.log"


def setup() -> Path:
    """Log to <data>/rinne.log (1 MB × 3 files) and record uncaught exceptions."""
    global _path
    if _path is not None:
        return _path
    _path = log_path()
    handler = RotatingFileHandler(_path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    log.setLevel(logging.INFO)
    log.addHandler(handler)
    log.info("Rinne %s starting — Python %s on %s", __version__, platform.python_version(),
             platform.platform())

    previous = sys.excepthook

    def excepthook(kind, value, tb):
        log.critical("Uncaught exception", exc_info=(kind, value, tb))
        previous(kind, value, tb)

    sys.excepthook = excepthook
    return _path


def tail(lines: int = 80) -> str:
    """The last lines of the log (for bug reports)."""
    path = log_path()
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return ""
