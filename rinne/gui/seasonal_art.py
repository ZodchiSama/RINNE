"""Seasonal decorations painted on the window background (behind the pages).

Halloween: a harvest moon in the top-right corner with a cobweb across it, a spider hanging in
front of the moon, bats, and a warm glow rising from the bottom of the window.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient

CORNER_W, CORNER_H = 640, 440
_cache: dict[tuple, QPixmap] = {}

BONE = (239, 230, 218)
SILHOUETTE = QColor(12, 7, 16)


def _bat(p: QPainter, cx: float, cy: float, span: float, color: QColor, tilt: float = 0) -> None:
    """A bat with scalloped wings, `span` wide."""
    s = span / 2
    path = QPainterPath()
    path.moveTo(0, -0.10 * s)
    # Right wing: up to the tip, then three scallops back to the body.
    path.cubicTo(0.25 * s, -0.45 * s, 0.70 * s, -0.55 * s, 1.0 * s, -0.20 * s)
    path.quadTo(0.86 * s, 0.00 * s, 0.78 * s, 0.18 * s)
    path.quadTo(0.62 * s, 0.02 * s, 0.50 * s, 0.20 * s)
    path.quadTo(0.36 * s, 0.04 * s, 0.22 * s, 0.24 * s)
    path.quadTo(0.10 * s, 0.10 * s, 0.0, 0.30 * s)
    # Left wing, mirrored.
    path.quadTo(-0.10 * s, 0.10 * s, -0.22 * s, 0.24 * s)
    path.quadTo(-0.36 * s, 0.04 * s, -0.50 * s, 0.20 * s)
    path.quadTo(-0.62 * s, 0.02 * s, -0.78 * s, 0.18 * s)
    path.quadTo(-0.86 * s, 0.00 * s, -1.0 * s, -0.20 * s)
    path.cubicTo(-0.70 * s, -0.55 * s, -0.25 * s, -0.45 * s, 0, -0.10 * s)
    # Head and ears.
    head = QPainterPath()
    head.moveTo(-0.09 * s, -0.08 * s)
    head.lineTo(-0.10 * s, -0.30 * s)
    head.lineTo(-0.03 * s, -0.20 * s)
    head.lineTo(0.03 * s, -0.20 * s)
    head.lineTo(0.10 * s, -0.30 * s)
    head.lineTo(0.09 * s, -0.08 * s)
    head.closeSubpath()
    p.save()
    p.translate(cx, cy)
    p.rotate(tilt)
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawPath(path.united(head))
    p.restore()


def _spider(p: QPainter, x: float, top: float, y: float, size: float) -> None:
    p.setPen(QPen(QColor(*BONE, 120), 1.2))
    p.drawLine(QPointF(x, top), QPointF(x, y - size * 0.9))
    p.setPen(QPen(SILHOUETTE, max(1.6, size * 0.13), Qt.SolidLine, Qt.RoundCap))
    for side in (-1, 1):
        for k, (dx, dy, ex, ey) in enumerate(((1.1, -0.7, 1.6, -1.3), (1.3, -0.2, 1.9, -0.5),
                                               (1.3, 0.3, 1.9, 0.9), (1.0, 0.7, 1.4, 1.5))):
            knee = QPointF(x + side * dx * size, y + dy * size)
            p.drawLine(QPointF(x, y), knee)
            p.drawLine(knee, QPointF(x + side * ex * size, y + ey * size))
    p.setPen(Qt.NoPen)
    p.setBrush(SILHOUETTE)
    p.drawEllipse(QPointF(x, y + size * 0.25), size * 0.62, size * 0.75)  # abdomen
    p.drawEllipse(QPointF(x, y - size * 0.55), size * 0.38, size * 0.36)  # head
    p.setBrush(QColor(255, 120, 40, 220))  # eyes catching the moonlight
    for side in (-1, 1):
        p.drawEllipse(QPointF(x + side * size * 0.14, y - size * 0.58), size * 0.08, size * 0.08)


def _corner(dpr: float) -> QPixmap:
    key = ("corner", dpr)
    if key in _cache:
        return _cache[key]
    w, h = CORNER_W, CORNER_H
    pix = QPixmap(round(w * dpr), round(h * dpr))
    pix.setDevicePixelRatio(dpr)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    # Harvest moon with a soft halo.
    # High in the corner, partly above the window, so page descriptions never run across it.
    moon = QPointF(w - 120, 14)
    halo = QRadialGradient(moon, 210)
    halo.setColorAt(0.0, QColor(255, 150, 60, 70))
    halo.setColorAt(0.45, QColor(255, 120, 40, 22))
    halo.setColorAt(1.0, QColor(255, 120, 40, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(halo)
    p.drawEllipse(moon, 210, 210)
    face = QRadialGradient(QPointF(moon.x() - 16, moon.y() - 18), 78)
    face.setColorAt(0.0, QColor(255, 226, 170, 235))
    face.setColorAt(0.7, QColor(255, 176, 92, 225))
    face.setColorAt(1.0, QColor(240, 128, 52, 215))
    p.setBrush(face)
    p.drawEllipse(moon, 60, 60)
    p.setBrush(QColor(200, 100, 40, 55))  # craters
    for dx, dy, r in ((-20, -12, 11), (18, 14, 8), (-4, 26, 6), (24, -22, 5)):
        p.drawEllipse(QPointF(moon.x() + dx, moon.y() + dy), r, r)

    # Cobweb anchored in the corner, drawn over the moon.
    corner = QPointF(w, 0)
    reach = 400
    spokes = [math.radians(a) for a in (91, 104, 118, 132, 146, 160, 174, 179)]
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(*BONE, 105), 1.4))
    for a in spokes:
        p.drawLine(corner, QPointF(w + math.cos(a) * reach * 1.2, math.sin(a) * reach * 1.2))
    p.setPen(QPen(QColor(*BONE, 80), 1.15))
    for ring in (38, 78, 122, 170, 222, 278, 338):
        web = QPainterPath()
        for i, a in enumerate(spokes):
            pt = QPointF(w + math.cos(a) * ring, math.sin(a) * ring)
            if i == 0:
                web.moveTo(pt)
                continue
            mid = (a + spokes[i - 1]) / 2
            sag = ring * 0.84
            web.quadTo(QPointF(w + math.cos(mid) * sag, math.sin(mid) * sag), pt)
        p.drawPath(web)

    # A spider dropping in front of the moon, and bats.
    _spider(p, moon.x() - 30, 0, moon.y() + 34, 13)
    _bat(p, moon.x() + 26, moon.y() + 4, 38, SILHOUETTE, -8)  # across the moon
    for cx, cy, span, tilt in ((w - 300, 34, 36, 10), (w - 410, 14, 26, -12),
                               (w - 230, 64, 26, 6), (w - 520, 40, 20, 14)):
        _bat(p, cx, cy, span, QColor(70, 40, 86, 210), tilt)
    p.end()
    _cache[key] = pix
    return pix


def paint_halloween(p: QPainter, rect: QRectF, dpr: float) -> None:
    """Decorate the window background: call after it's filled (and after any slideshow)."""
    glow = QLinearGradient(0, rect.height() * 0.45, 0, rect.height())
    glow.setColorAt(0.0, QColor(255, 110, 30, 0))
    glow.setColorAt(1.0, QColor(255, 110, 30, 34))
    p.fillRect(rect, glow)
    corner = _corner(dpr)
    p.drawPixmap(QPointF(rect.width() - CORNER_W, 0), corner)
