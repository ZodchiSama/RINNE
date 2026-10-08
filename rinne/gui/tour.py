"""The guided tour: dims the window, spotlights one part at a time, with pop-up steps."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QPushButton, QWidget

from ..i18n import _
from . import theme
from .common import hbox, label, vbox


@dataclass
class Step:
    title: str
    text: str
    target: Callable[[], QWidget | None]  # widget to spotlight (None = centred)
    before: Callable[[], None] | None = None  # e.g. switch to the right page first


class TourOverlay(QWidget):
    finished = Signal()

    def __init__(self, host: QWidget, steps: list[Step]):
        super().__init__(host)
        self.host, self.steps, self.index = host, steps, 0
        self.hole = QRect()
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.StrongFocus)
        self.bubble = QFrame(self)
        self.bubble.setObjectName("tourBubble")
        self.bubble.setFixedWidth(min(theme.px(340), max(theme.px(240), host.width() - theme.px(24))))
        lay = vbox(self.bubble, 8, 18)
        self.counter = label("", "tourCounter")
        self.title = label("", "h2", wrap=True)
        self.text = label("", "body", wrap=True)
        lay.addWidget(self.counter)
        lay.addWidget(self.title)
        lay.addWidget(self.text)
        lay.addSpacing(theme.px(4))
        row = hbox(spacing=8)
        self.skip = QPushButton(_("Skip tour"))
        self.skip.setObjectName("link")
        self.back = QPushButton(_("Back"))
        self.back.setObjectName("ghost")
        self.next = QPushButton(_("Next"))
        self.next.setObjectName("primary")
        row.addWidget(self.skip)
        row.addStretch()
        row.addWidget(self.back)
        row.addWidget(self.next)
        lay.addLayout(row)
        self.skip.clicked.connect(self.close_tour)
        self.back.clicked.connect(lambda: self.show_step(self.index - 1))
        self.next.clicked.connect(self._next)
        host.installEventFilter(self)

    def start(self) -> None:
        self.setGeometry(self.host.rect())
        self.show()
        self.raise_()
        self.setFocus()
        self.show_step(0)

    def _next(self) -> None:
        if self.index >= len(self.steps) - 1:
            self.close_tour()
        else:
            self.show_step(self.index + 1)

    def close_tour(self) -> None:
        self.host.removeEventFilter(self)
        self.hide()
        self.finished.emit()
        self.deleteLater()

    def show_step(self, i: int) -> None:
        self.index = max(0, min(len(self.steps) - 1, i))
        step = self.steps[self.index]
        if step.before:
            step.before()
        self.counter.setText(_("STEP {value} OF {n}").format(value=self.index + 1, n=len(self.steps)))
        self.title.setText(step.title)
        self.text.setText(step.text)
        self.back.setVisible(self.index > 0)
        self.next.setText(_("Finish") if self.index == len(self.steps) - 1 else _("Next"))
        self._place()
        # A page switch rebuilds widgets; place again once Qt has laid them out.
        QTimer.singleShot(60, self._place)

    def _place(self) -> None:
        self.setGeometry(self.host.rect())
        target = self.steps[self.index].target()
        if target is not None and target.isVisible():
            top_left = target.mapTo(self.host, QPoint(0, 0))
            pad = theme.px(6)
            self.hole = QRect(top_left, target.size()).adjusted(-pad, -pad, pad, pad)
        else:
            self.hole = QRect()
        bw = self.bubble.width()
        # Word-wrapped text: ask for the height at this width (sizeHint assumes one line).
        bh = max(self.bubble.sizeHint().height(), self.bubble.layout().totalHeightForWidth(bw))
        gap, margin = theme.px(16), theme.px(12)
        W, H = self.width(), self.height()
        if self.hole.isNull():
            x, y = (W - bw) // 2, (H - bh) // 2
        elif self.hole.right() + gap + bw < W - margin:  # to the right
            x, y = self.hole.right() + gap, self.hole.center().y() - bh // 2
        elif self.hole.bottom() + gap + bh < H - margin:  # below
            x, y = self.hole.center().x() - bw // 2, self.hole.bottom() + gap
        else:  # above
            x, y = self.hole.center().x() - bw // 2, self.hole.top() - gap - bh
        x = max(margin, min(W - bw - margin, x))
        y = max(margin, min(H - bh - margin, y))
        self.bubble.setGeometry(x, y, bw, bh)
        self.bubble.raise_()
        self.update()

    def eventFilter(self, obj, event) -> bool:
        if obj is self.host and event.type() == event.Type.Resize:
            self._place()
        return False

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key_Escape:
            self.close_tour()
        elif key in (Qt.Key_Right, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self._next()
        elif key == Qt.Key_Left:
            self.show_step(self.index - 1)

    def mousePressEvent(self, event) -> None:
        event.accept()  # the dimmed area isn't clickable during the tour

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        dim = QPainterPath()
        dim.addRect(QRectF(self.rect()))
        if not self.hole.isNull():
            hole = QPainterPath()
            hole.addRoundedRect(QRectF(self.hole), theme.px(12), theme.px(12))
            dim = dim.subtracted(hole)
        p.fillPath(dim, QColor(0, 0, 0, 165))
        if not self.hole.isNull():
            p.setPen(QPen(theme.qcolor(theme.ACCENT), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(self.hole), theme.px(12), theme.px(12))
