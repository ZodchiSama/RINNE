"""Small layout helpers and reusable widgets."""

from __future__ import annotations

from PySide6.QtCore import QObject, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QAbstractButton, QBoxLayout, QFrame, QHBoxLayout, QLabel, QLayout, QProgressBar, QSizePolicy,
    QVBoxLayout, QWidget,
)

from ..models import CURRENTLY_AIRING, WEEKDAYS, Anime
from . import theme


def button_row(*widgets, spacing: float = 8, stretch_before: bool = False) -> QWidget:
    """A row of buttons. On phones it wraps onto more lines instead of forcing the page wider."""
    host = QWidget()
    if theme.COMPACT:
        flow = FlowLayout(host, spacing)
        for w in widgets:
            flow.addWidget(w)
    else:
        row = hbox(host, spacing)
        if stretch_before:
            row.addStretch()
        for w in widgets:
            row.addWidget(w)
        if not stretch_before:
            row.addStretch()
    return host


def watch_button(anime) -> QWidget | None:
    """'▶ Watch on <site>' for a show's official streams (a menu when there are several)."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QMenu, QPushButton
    links = getattr(anime, "streaming", None) or []
    if not links:
        return None
    b = QPushButton(f"▶  Watch on {links[0]['site']}" if len(links) == 1 else "▶  Watch ▾")
    b.setObjectName("watch")
    b.setCursor(Qt.PointingHandCursor)
    if len(links) == 1:
        b.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(links[0]["url"])))
    else:
        menu = QMenu(b)
        for link in links:
            menu.addAction(link["site"], lambda u=link["url"]: QDesktopServices.openUrl(QUrl(u)))
        b.setMenu(menu)
    b.setToolTip("Open the official stream in your browser")
    return b


def page_margin() -> float:
    return 14 if theme.COMPACT else 28


def set_margins(layout, n: float) -> None:
    m = theme.px(n)
    layout.setContentsMargins(m, m, m, m)


def label(text: str = "", name: str = "", wrap: bool = False, rich: bool = False) -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    # Phones: any label may wrap, so a long one can never push a page wider than the screen.
    lbl.setWordWrap(wrap or theme.COMPACT)
    lbl.setTextFormat(Qt.RichText if rich else Qt.PlainText)
    return lbl


def vbox(parent: QWidget | None = None, spacing: float = 8, margins: float = 0) -> QVBoxLayout:
    lay = QVBoxLayout(parent) if parent is not None else QVBoxLayout()
    lay.setSpacing(theme.px(spacing))
    m = theme.px(margins) if margins else 0
    lay.setContentsMargins(m, m, m, m)
    return lay


def hbox(parent: QWidget | None = None, spacing: float = 8, margins: float = 0) -> QHBoxLayout:
    lay = QHBoxLayout(parent) if parent is not None else QHBoxLayout()
    lay.setSpacing(theme.px(spacing))
    m = theme.px(margins) if margins else 0
    lay.setContentsMargins(m, m, m, m)
    return lay


def card(name: str = "card", margins: float = 14, spacing: float = 8,
         horizontal: bool = False) -> tuple[QFrame, QBoxLayout]:
    frame = QFrame()
    frame.setObjectName(name)
    if theme.COMPACT:  # tighter padding on phones: every pixel of width counts
        margins = min(margins, 12)
    lay = (hbox if horizontal else vbox)(frame, spacing, margins)
    return frame, lay


def clear(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if w := item.widget():
            w.hide()
            w.deleteLater()
        elif sub := item.layout():
            clear(sub)


def badge(text: str, kind: str = "badge") -> QLabel:
    b = label(text, kind)
    b.setSizePolicy(b.sizePolicy().horizontalPolicy(), b.sizePolicy().verticalPolicy())
    return b


def progress(anime: Anime) -> QProgressBar:
    bar = QProgressBar()
    bar.setTextVisible(False)
    total = anime.episodes_total or max(anime.episodes_watched, 1)
    bar.setRange(0, total)
    bar.setValue(min(anime.episodes_watched, total))
    return bar


def progress_text(anime: Anime) -> str:
    return f"Ep {anime.episodes_watched} / {anime.episodes_total or '?'}"


def airing_text(anime: Anime) -> str:
    if anime.airing_status != CURRENTLY_AIRING:
        return ""
    if anime.broadcast_day is not None:
        return f"Airs {WEEKDAYS[anime.broadcast_day][:3]}"
    return "Airing"


def fmt_minutes(m: int) -> str:
    h, mm = divmod(m, 60)
    return f"{h}h {mm:02d}m" if h else f"{mm}m"


class ElidedLabel(QLabel):
    """Single-line label that elides with … instead of clipping; full text in the tooltip."""

    def __init__(self, text: str, name: str = ""):
        super().__init__(text)
        if name:
            self.setObjectName(name)
        self.setToolTip(text)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def minimumSizeHint(self):
        return QSize(theme.px(30), self.fontMetrics().height())

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setPen(self.palette().color(self.foregroundRole()))
        text = self.fontMetrics().elidedText(self.text(), Qt.ElideRight, self.width())
        p.drawText(self.rect(), Qt.AlignLeft | Qt.AlignVCenter, text)


class FlowLayout(QLayout):
    """Lays children out left to right, wrapping onto new rows.

    Heights come from each item's height-for-width, so word-wrapped text inside fixed-width
    cards is never clipped. With `uniform_rows`, every item in a row gets the row's height.
    """

    def __init__(self, parent: QWidget | None = None, spacing: float = 10, uniform_rows: bool = False):
        super().__init__(parent)
        self._items = []
        self._gap = theme.px(spacing)
        self._uniform = uniform_rows
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, apply=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    @staticmethod
    def _item_size(item, max_width: int) -> QSize:
        hint = item.sizeHint()
        w = min(hint.width(), max_width) if max_width > 0 else hint.width()
        h = item.heightForWidth(w) if item.hasHeightForWidth() else hint.height()
        return QSize(w, max(h, item.minimumSize().height()))

    def _do_layout(self, rect, apply: bool) -> int:
        rows: list[list[tuple]] = []
        row: list[tuple] = []
        x = rect.x()
        for item in self._items:
            size = self._item_size(item, rect.width())
            if row and x + size.width() > rect.right() + 1:
                rows.append(row)
                row, x = [], rect.x()
            row.append((item, size))
            x += size.width() + self._gap
        if row:
            rows.append(row)
        y = rect.y()
        for row in rows:
            line_h = max(size.height() for _, size in row)
            x = rect.x()
            for item, size in row:
                if apply:
                    h = line_h if self._uniform else size.height()
                    item.setGeometry(QRect(QPoint(x, y), QSize(size.width(), h)))
                x += size.width() + self._gap
            y += line_h + self._gap
        return max(0, y - self._gap - rect.y())


class Switch(QAbstractButton):
    """A pill-shaped on/off toggle."""

    def __init__(self, checked: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(theme.px(44), theme.px(24))

    def sizeHint(self):
        return QSize(theme.px(44), theme.px(24))

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        on = self.isChecked()
        track = theme.qcolor(theme.ACCENT if on else theme.SURFACE_3)
        if not self.isEnabled():
            track.setAlpha(90)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - theme.px(6)
        x = r.right() - d - theme.px(3) if on else r.left() + theme.px(3)
        p.setBrush(theme.qcolor("#ffffff"))
        p.drawEllipse(x, r.top() + theme.px(3), d, d)


class Clickable(QObject):
    """Emits `clicked` on left click of the watched widget."""

    clicked = Signal()

    def __init__(self, widget: QWidget):
        super().__init__(widget)
        widget.installEventFilter(self)
        widget.setCursor(Qt.PointingHandCursor)

    def eventFilter(self, obj, event) -> bool:
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            self.clicked.emit()
        return False
