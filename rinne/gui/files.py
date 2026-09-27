"""Reading and writing files picked in a file dialog.

On Android the picker returns content:// URIs, which Python's open() can't use; QFile can.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile, QIODevice


def read_bytes(path: str) -> bytes:
    if path.startswith("content:"):
        f = QFile(path)
        if not f.open(QIODevice.ReadOnly):
            raise OSError(f"Can't open {path}: {f.errorString()}")
        try:
            return bytes(f.readAll().data())
        finally:
            f.close()
    return Path(path).read_bytes()


def write_bytes(path: str, data: bytes) -> None:
    if path.startswith("content:"):
        f = QFile(path)
        if not f.open(QIODevice.WriteOnly | QIODevice.Truncate):
            raise OSError(f"Can't write {path}: {f.errorString()}")
        try:
            f.write(data)
        finally:
            f.close()
        return
    Path(path).write_bytes(data)
