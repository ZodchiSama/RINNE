"""The Stats page: your watching, by the numbers."""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QGridLayout, QToolTip, QWidget

from .. import stats as stats_mod
from ..i18n import _, _n, strftime
from . import theme
from .common import card, clear, fmt_minutes, hbox, label, page_margin, set_margins, vbox
from .images import Cover
from .common import scroll_page

if TYPE_CHECKING:
    from .window import MainWindow


def nice_max(value: int) -> int:
    """Round an axis maximum up to 1, 2 or 5 × 10^k (at least 4)."""
    if value <= 4:
        return 4
    mag = 10 ** int(math.floor(math.log10(value)))
    for step in (1, 2, 5, 10):
        if value <= step * mag:
            return step * mag
    return 10 * mag


class BarChart(QWidget):
    """A single-series bar chart: one hue, rounded data-ends on the baseline, quiet axes,
    and the exact value in a tooltip on hover."""

    def __init__(self, data: list[tuple[str, int, str]], parent=None):
        super().__init__(parent)
        self.data = data  # (axis label, value, tooltip)
        self.hover = -1
        self.setMouseTracking(True)
        self.setMinimumHeight(theme.px(170))

    def _geometry(self):
        fm = QFontMetrics(self.font())
        left, bottom, top = theme.px(30), fm.height() + theme.px(8), theme.px(8)
        plot = QRectF(left, top, self.width() - left - theme.px(4), self.height() - top - bottom)
        slot = plot.width() / max(1, len(self.data))
        return plot, slot

    def paintEvent(self, event) -> None:
        if not self.data:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        f = self.font()
        f.setPixelSize(theme.px(11))
        p.setFont(f)
        fm = QFontMetrics(f)
        plot, slot = self._geometry()
        top_value = nice_max(max(v for _, v, _ in self.data))

        # Recessive grid: baseline, middle and top, labelled on the left.
        for frac in (0, 0.5, 1):
            y = plot.bottom() - frac * plot.height()
            p.setPen(QPen(theme.qcolor(theme.BORDER), 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(theme.qcolor(theme.FAINT))
            p.drawText(QRectF(0, y - fm.height() / 2, plot.left() - theme.px(6), fm.height()),
                       Qt.AlignRight | Qt.AlignVCenter, str(round(top_value * frac)))

        # Bars: thin, with a gap between them; 4px rounded tops anchored to the baseline.
        bar_w = max(theme.px(3), min(slot - theme.px(2), slot * 0.62))
        radius = min(theme.px(4), bar_w / 2)
        for i, (_label, value, _tip) in enumerate(self.data):
            if value <= 0:
                continue
            h = max(radius, value / top_value * plot.height())
            x = plot.left() + i * slot + (slot - bar_w) / 2
            r = QRectF(x, plot.bottom() - h, bar_w, h)
            path = QPainterPath()
            path.moveTo(r.left(), r.bottom())
            path.lineTo(r.left(), r.top() + radius)
            path.quadTo(r.left(), r.top(), r.left() + radius, r.top())
            path.lineTo(r.right() - radius, r.top())
            path.quadTo(r.right(), r.top(), r.right(), r.top() + radius)
            path.lineTo(r.right(), r.bottom())
            path.closeSubpath()
            p.fillPath(path, theme.qcolor(theme.ACCENT_HOVER if i == self.hover else theme.ACCENT))

        # Axis labels: only as many as fit without colliding.
        p.setPen(theme.qcolor(theme.MUTED))
        widest = max(fm.horizontalAdvance(lbl) for lbl, _, _ in self.data) + theme.px(10)
        every = max(1, math.ceil(widest / slot))
        for i, (lbl, _value, _tip) in enumerate(self.data):
            if (len(self.data) - 1 - i) % every:
                continue
            cx = plot.left() + (i + 0.5) * slot
            p.drawText(QRectF(cx - widest / 2, plot.bottom() + theme.px(4), widest, fm.height()),
                       Qt.AlignCenter, lbl)

    def mouseMoveEvent(self, event) -> None:
        plot, slot = self._geometry()
        x = event.position().x()
        i = int((x - plot.left()) // slot) if plot.left() <= x <= plot.right() else -1
        if i != self.hover:
            self.hover = i if 0 <= i < len(self.data) else -1
            self.update()
        if self.hover >= 0:
            QToolTip.showText(event.globalPosition().toPoint(), self.data[self.hover][2], self)
        else:
            QToolTip.hideText()

    def leaveEvent(self, event) -> None:
        self.hover = -1
        self.update()


class GoalGrid(QWidget):
    """Daily goals for the last weeks: one row per week (Sunday → Saturday), one cell per day.
    Complete days get a ✓, failed ones an ✕, so the grid doesn't rely on colour alone."""

    LABELS = {"done": "Complete", "failed": "Failed", "open": "Not finished yet",
              "none": "Nothing planned", "future": "Coming up"}

    def __init__(self, weeks: list[tuple[date, list[str]]], parent=None):
        super().__init__(parent)
        self.weeks = weeks
        self.setMouseTracking(True)
        self.hover: tuple[int, int] | None = None
        self.setMinimumHeight(self._row_h() * (len(weeks) + 1))

    def _row_h(self) -> int:
        return theme.px(30)

    def _cells(self):
        left = theme.px(64)
        size = min(theme.px(26), max(theme.px(14), (self.width() - left) // 7 - theme.px(6)))
        gap = theme.px(6)
        return left, size, gap

    def _cell_rect(self, w: int, d: int) -> QRectF:
        left, size, gap = self._cells()
        top = self._row_h() * (w + 1) + (self._row_h() - size) / 2
        return QRectF(left + d * (size + gap), top, size, size)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        f = QFont(self.font())
        f.setPixelSize(theme.px(11))
        p.setFont(f)
        p.setPen(QColor(theme.MUTED))
        for d, name in enumerate(["S", "M", "T", "W", "T", "F", "S"]):
            r = self._cell_rect(-1, d)
            p.drawText(r, Qt.AlignCenter, name)
        fill = {"done": theme.SUCCESS, "failed": theme.DANGER, "open": theme.AMBER_BG,
                "none": theme.SURFACE_2, "future": None}
        for w, (start, states) in enumerate(self.weeks):
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(0, self._row_h() * (w + 1), theme.px(58), self._row_h()),
                       Qt.AlignVCenter | Qt.AlignLeft, f"{start:%d %b}")
            for d, st in enumerate(states):
                r = self._cell_rect(w, d)
                if fill[st]:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(fill[st]))
                else:
                    p.setPen(QPen(QColor(theme.BORDER), 1, Qt.DashLine))
                    p.setBrush(Qt.NoBrush)
                if st == "open":
                    p.setPen(QPen(QColor(theme.WARN), 1.2))
                if self.hover == (w, d):
                    p.setPen(QPen(QColor(theme.TEXT), 2))
                p.drawRoundedRect(r, theme.px(6), theme.px(6))
                mark = {"done": "✓", "failed": "✕", "open": "!"}.get(st)
                if mark:
                    p.setPen(QColor(theme.SURFACE if st in ("done", "failed") else theme.WARN))
                    p.drawText(r, Qt.AlignCenter, mark)
        p.end()

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()
        hit = None
        for w in range(len(self.weeks)):
            for d in range(7):
                if self._cell_rect(w, d).contains(pos):
                    hit = (w, d)
        if hit != self.hover:
            self.hover = hit
            self.update()
        if hit:
            start, states = self.weeks[hit[0]]
            on = start + timedelta(days=hit[1])
            QToolTip.showText(event.globalPosition().toPoint(), f"{on:%a %d %b}: {self.LABELS[states[hit[1]]]}", self)
        else:
            QToolTip.hideText()

    def leaveEvent(self, event) -> None:
        self.hover = None
        self.update()


class HBarList(QWidget):
    """Ranked horizontal bars (label · bar · value), one hue."""

    def __init__(self, rows: list[tuple[str, int]], unit: str, parent=None):
        super().__init__(parent)
        lay = QGridLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setHorizontalSpacing(theme.px(10))
        lay.setVerticalSpacing(theme.px(8))
        lay.setColumnStretch(1, 1)
        top = max((v for _, v in rows), default=1) or 1
        for r, (name, value) in enumerate(rows):
            lay.addWidget(label(name, "small"), r, 0)
            bar = _Bar(value / top)
            bar.setToolTip(f"{name}: {value} {unit}")
            lay.addWidget(bar, r, 1)
            lay.addWidget(label(str(value), "faint"), r, 2, alignment=Qt.AlignRight)


class _Bar(QWidget):
    def __init__(self, fraction: float):
        super().__init__()
        self.fraction = fraction
        self.setFixedHeight(theme.px(10))
        self.setMinimumWidth(theme.px(60))

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = max(theme.px(4), self.width() * self.fraction)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, self.height()), theme.px(4), theme.px(4))
        p.fillPath(path, theme.qcolor(theme.ACCENT))


class StatsPage(QWidget):
    def __init__(self, win: MainWindow):
        super().__init__()
        self.win = win
        outer = vbox(self)
        self.area, inner = scroll_page()
        outer.addWidget(self.area)
        self.body = vbox(inner, 16, 28)

    def _tile(self, value: str, caption: str, sub: str = "") -> QFrame:
        frame, lay = card("stat", 14, 2)
        lay.addWidget(label(value, "statValue"))
        lay.addWidget(label(caption, "statLabel"))
        if sub:
            lay.addWidget(label(sub, "faint"))
        return frame

    def refresh(self) -> None:
        scroll = self.area.verticalScrollBar().value()
        clear(self.body)
        set_margins(self.body, page_margin())
        st = self.win.state
        s = stats_mod.compute(st)
        titles = vbox(spacing=2)
        titles.addWidget(label(_("Stats"), "h1"))
        titles.addWidget(label(_("Your watching, by the numbers."), "muted"))
        self.body.addLayout(titles)

        days = s.total_minutes / 60 / 24
        tiles = [
            self._tile(str(s.week_episodes), _("Episodes in the last 7 days"), fmt_minutes(s.week_minutes)),
            self._tile(_n("{n} day", "{n} days", s.streak), _("Current streak"),
                       _n("Best: {n} day", "Best: {n} days", s.best_streak)),
            self._tile(f"{s.total_episodes:,}", _("Episodes watched, all time")),
            self._tile(f"{days:,.1f} days" if days >= 1 else fmt_minutes(s.total_minutes),
                       _("Time watched, all time"), _("{value:,} hours").format(value=s.total_minutes // 60)),
        ]
        grid = QGridLayout()
        grid.setSpacing(theme.px(10 if theme.COMPACT else 12))
        for n, tile in enumerate(tiles):
            grid.addWidget(tile, *((n // 2, n % 2) if theme.COMPACT else (0, n)))
        self.body.addLayout(grid)

        frame, lay = card(margins=18, spacing=10)
        lay.addWidget(label(_("Daily goals"), "h2"))
        lay.addWidget(label(_("A day is complete when you tick everything planned for it. Days still unfinished "
                            "when the week restarts (00:00 Sunday) count as failed."), "faint", wrap=True))
        goals = (vbox if theme.COMPACT else hbox)(spacing=18)
        nums = vbox(spacing=8)
        rate = s.goal_rate
        for value, caption in [(s.days_done, "Days complete"), (s.days_failed, "Days failed"),
                               (f"{rate:.0%}" if rate is not None else "—", "Success rate"),
                               (f"{s.goal_streak}", f"Complete in a row (best {s.best_goal_streak})")]:
            line = hbox(spacing=8)
            line.addWidget(label(str(value), "h2"))
            line.addWidget(label(caption, "small"), 1)
            nums.addLayout(line)
        nums.addStretch()
        goals.addLayout(nums)
        grid_col = vbox(spacing=6)
        grid_col.addWidget(GoalGrid(s.goal_weeks))
        grid_col.addWidget(label(_("✓ complete · ✕ failed · ! not finished yet · dashed: coming up"), "faint", wrap=True))
        goals.addLayout(grid_col, 1)
        lay.addLayout(goals)
        self.body.addWidget(frame)

        if not st.history:
            frame, lay = card(margins=18)
            lay.addWidget(label(_("Your history starts now"), "cardTitle"))
            lay.addWidget(label(_("Tick episodes in Your Week and the charts below fill in day by day. "
                                "All-time totals already include everything on your list."), "muted", wrap=True))
            self.body.addWidget(frame)

        frame, lay = card(margins=18, spacing=10)
        lay.addWidget(label(_("Episodes per week"), "h2"))
        lay.addWidget(BarChart([(strftime(d, "%d %b"), n,
                                 _n("Week of {date}: {n} episode", "Week of {date}: {n} episodes", n,
                                    date=strftime(d, "%d %b")))
                                for d, n in s.weekly]))
        self.body.addWidget(frame)

        frame, lay = card(margins=18, spacing=10)
        lay.addWidget(label(_("Last 30 days"), "h2"))
        lay.addWidget(BarChart([(f"{d.day}", n, _n("{date}: {n} episode", "{date}: {n} episodes", n,
                                                    date=strftime(d, "%a %d %b")))
                                for d, n in s.daily]))
        self.body.addWidget(frame)

        row = (vbox if theme.COMPACT else hbox)(spacing=12)
        gframe, gl = card(margins=18, spacing=10)
        gl.addWidget(label(_("Top genres"), "h2"))
        gl.addWidget(label(_("By episodes watched across your list."), "faint"))
        if s.genres:
            gl.addWidget(HBarList(s.genres, "episodes"))
        else:
            gl.addWidget(label(_("Genres appear once show details have loaded."), "muted"))
        gl.addStretch()
        row.addWidget(gframe, 1)
        lframe, ll = card(margins=18, spacing=10)
        ll.addWidget(label(_("Your list"), "h2"))
        rate = s.completion_rate
        for value, caption in [(s.watching, "Watching"), (s.completed, "Completed"), (s.dropped, "Dropped"),
                               (f"{rate:.0%}" if rate is not None else "—", "Completion rate (completed vs dropped)")]:
            line = hbox(spacing=8)
            line.addWidget(label(str(value), "h2"))
            line.addWidget(label(caption, "small"), 1)
            ll.addLayout(line)
        ll.addStretch()
        row.addWidget(lframe, 1)
        self.body.addLayout(row)

        if s.recent:
            frame, lay = card(margins=18, spacing=8)
            lay.addWidget(label(_("Recently watched"), "h2"))
            for h in s.recent:
                a = st.library.get(h["m"])
                if a is None:
                    continue
                line = hbox(spacing=10)
                line.addWidget(Cover(a.image_url, a.name, 28, 40, 4))
                line.addWidget(label(_("{name} — episode {e}").format(name=a.name, e=h['e']), "", wrap=True), 1)
                try:
                    when = date.fromisoformat(h["d"])
                    line.addWidget(label(f"{when:%a %d %b}", "faint"))
                except ValueError:
                    pass
                lay.addLayout(line)
            self.body.addWidget(frame)
        self.body.addStretch()
        self.area.verticalScrollBar().setValue(scroll)
