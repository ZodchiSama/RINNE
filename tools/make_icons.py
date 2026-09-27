"""Build Rinne's icon assets from the source artwork in assets/source/.

    .venv/bin/python tools/make_icons.py

Outputs (in rinne/assets/):
  icon.png          512 px app icon, white corners made transparent
  icon-<N>.png      hicolor sizes for the desktop entry (16 … 512)
  logo-round.png    512 px round badge cut from the wordmark, for use inside the app
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "source"
OUT = ROOT / "rinne" / "assets"
SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
NAVY = (0, 10, 43)  # the icon's background colour


def transparent_corners(img: QImage) -> QImage:
    """Turn the white outside the squircle transparent, un-blending the anti-aliased edge
    so no light fringe is left. Only navy↔white blends are touched (not the purple wheel)."""
    img = img.convertToFormat(QImage.Format_ARGB32)
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            r, g, b = c.red(), c.green(), c.blue()
            on_navy_white_line = g >= r - 8 and b >= g - 8 and (b - r) <= 55
            if r > 30 and on_navy_white_line:
                white = min(1.0, r / 255)  # how much of the pixel is white background
                img.setPixelColor(x, y, QColor(*NAVY, round(255 * (1 - white))))
    return img


def round_badge(img: QImage, cx: float, cy: float, radius: float, size: int) -> QImage:
    out = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    path = QPainterPath()
    path.addEllipse(QRectF(0, 0, size, size))
    p.setClipPath(path)
    p.drawImage(QRectF(0, 0, size, size), img, QRectF(cx - radius, cy - radius, 2 * radius, 2 * radius))
    p.end()
    return out


def main() -> int:
    QGuiApplication(sys.argv)
    OUT.mkdir(parents=True, exist_ok=True)
    icon = transparent_corners(QImage(str(SRC / "icon-square.png")))
    for n in SIZES:
        icon.scaled(n, n, Qt.KeepAspectRatio, Qt.SmoothTransformation).save(str(OUT / f"icon-{n}.png"))
    icon.scaled(512, 512, Qt.KeepAspectRatio, Qt.SmoothTransformation).save(str(OUT / "icon.png"))
    # Discord recommends 1024×1024 art assets.
    icon.scaled(1024, 1024, Qt.KeepAspectRatio, Qt.SmoothTransformation).save(str(OUT / "icon-1024.png"))

    logo = QImage(str(SRC / "logo-wordmark.png"))
    # The outer arrow ring is centred in the artwork; keep a margin around its arrowheads.
    s = logo.width()
    round_badge(logo, s / 2, s / 2, s * 0.40, 512).save(str(OUT / "logo-round.png"))
    print("wrote", ", ".join(sorted(p.name for p in OUT.glob("*.png"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
