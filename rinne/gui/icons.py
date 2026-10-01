"""A small line-icon set drawn with QPainter, so icons follow the active theme's colours."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from . import theme


def _draw(name: str, p: QPainter, s: float) -> None:
    """Draw icon `name` in a 24×24 design box scaled by s."""
    def pt(x, y):
        return QPointF(x * s, y * s)

    def rect(x, y, w, h):
        return QRectF(x * s, y * s, w * s, h * s)

    if name == "week":  # calendar
        p.drawRoundedRect(rect(3.5, 5, 17, 15), 3 * s, 3 * s)
        p.drawLine(pt(3.5, 10), pt(20.5, 10))
        p.drawLine(pt(8, 3), pt(8, 7))
        p.drawLine(pt(16, 3), pt(16, 7))
        for x, y in ((8, 14), (12, 14), (16, 14), (8, 17), (12, 17)):
            p.drawPoint(pt(x, y))
    elif name == "next":  # cycle with a play head
        path = QPainterPath()
        path.arcMoveTo(rect(4, 4, 16, 16), 60)
        path.arcTo(rect(4, 4, 16, 16), 60, 280)
        p.drawPath(path)
        p.drawLine(pt(16, 5.1), pt(16.5, 1.8))
        p.drawLine(pt(16, 5.1), pt(19.2, 5.8))
        tri = QPainterPath(pt(10.5, 9))
        tri.lineTo(pt(15, 12))
        tri.lineTo(pt(10.5, 15))
        tri.closeSubpath()
        p.drawPath(tri)
    elif name == "library":  # grid of posters
        for x, y in ((4, 4), (13, 4), (4, 13), (13, 13)):
            p.drawRoundedRect(rect(x, y, 7, 7), 1.6 * s, 1.6 * s)
    elif name == "import":  # tray with a down arrow
        p.drawLine(pt(12, 3.5), pt(12, 14))
        p.drawLine(pt(7.5, 9.5), pt(12, 14))
        p.drawLine(pt(16.5, 9.5), pt(12, 14))
        path = QPainterPath(pt(4, 14))
        path.lineTo(pt(4, 19))
        path.quadTo(pt(4, 20.5), pt(5.5, 20.5))
        path.lineTo(pt(18.5, 20.5))
        path.quadTo(pt(20, 20.5), pt(20, 19))
        path.lineTo(pt(20, 14))
        p.drawPath(path)
    elif name == "settings":  # gear
        p.drawEllipse(rect(9, 9, 6, 6))
        import math
        path = QPainterPath()
        teeth = 8
        for i in range(teeth * 2):
            a = math.pi * i / teeth
            r = 8.5 if i % 2 == 0 else 6.6
            x, y = 12 + r * math.cos(a), 12 + r * math.sin(a)
            (path.moveTo if i == 0 else path.lineTo)(pt(x, y))
        path.closeSubpath()
        p.drawPath(path)
    elif name == "stats":  # bar chart
        p.drawLine(pt(4, 20), pt(20, 20))
        for x, top in ((6.5, 13), (11, 7), (15.5, 10)):
            p.drawRoundedRect(rect(x, top, 3, 20 - top), 1 * s, 1 * s)
    elif name == "chevron":
        p.drawLine(pt(9, 6), pt(15, 12))
        p.drawLine(pt(15, 12), pt(9, 18))
    elif name == "heart":
        path = QPainterPath(pt(12, 20))
        path.cubicTo(pt(2, 13), pt(4, 4), pt(12, 8))
        path.cubicTo(pt(20, 4), pt(22, 13), pt(12, 20))
        p.drawPath(path)
    elif name == "chat":
        p.drawRoundedRect(rect(3.5, 4.5, 17, 12), 3 * s, 3 * s)
        path = QPainterPath(pt(8, 16.5))
        path.lineTo(pt(7, 20.5))
        path.lineTo(pt(12, 16.5))
        p.drawPath(path)
    elif name == "info":
        p.drawEllipse(rect(3.5, 3.5, 17, 17))
        p.drawLine(pt(12, 11), pt(12, 16.5))
        p.drawPoint(pt(12, 7.8))
    elif name == "sparkle":
        path = QPainterPath(pt(12, 3))
        path.quadTo(pt(13, 11), pt(21, 12))
        path.quadTo(pt(13, 13), pt(12, 21))
        path.quadTo(pt(11, 13), pt(3, 12))
        path.quadTo(pt(11, 11), pt(12, 3))
        p.drawPath(path)


def icon(name: str, color: str | None = None, size: int = 20) -> QIcon:
    """A theme-coloured icon; the checked/active state uses the soft accent text colour."""
    ic = QIcon()
    for state_color, mode, state in (
        (color or theme.MUTED, QIcon.Normal, QIcon.Off),
        (theme.SOFT_TEXT, QIcon.Normal, QIcon.On),
        (theme.TEXT, QIcon.Active, QIcon.Off),
    ):
        ic.addPixmap(pixmap(name, state_color, size), mode, state)
    return ic


def pixmap(name: str, color: str, size: int = 20, dpr: float = 2.0) -> QPixmap:
    px = theme.px(size)
    pm = QPixmap(round(px * dpr), round(px * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), max(1.4, px / 12))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    _draw(name, p, px / 24)
    p.end()
    return pm
