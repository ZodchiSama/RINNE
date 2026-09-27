"""The three main pages: This Week, Up Next, Library."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from PySide6.QtCore import QModelIndex, QRect, QRectF, QSize, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QFrame, QGraphicsOpacityEffect, QGridLayout, QLabel,
    QLineEdit, QMenu,
    QListView, QPushButton, QScrollArea, QStyle, QStyledItemDelegate,
    QStyleOptionViewItem, QToolButton, QWidget,
)

from .. import scheduler
from ..models import EPISODES, LIST_STATUSES, PLAN_TO_WATCH, STATUS_LABELS, WEEKDAYS, Anime
from ..recommender import SERIES, rank
from . import theme
from .common import (
    Clickable, ElidedLabel, FlowLayout, airing_text, page_margin, set_margins, touch_scroll, badge, card, clear, fmt_minutes, hbox, label, progress, progress_text,
    vbox,
)
from .images import Cover, cache

if TYPE_CHECKING:
    from .window import MainWindow


def scroll_page(horizontal: bool = False) -> tuple[QScrollArea, QWidget]:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    if not horizontal:
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    inner = QWidget()
    inner.setObjectName("page")
    area.setWidget(inner)
    touch_scroll(area)
    return area, inner


# =========================================================================== This Week


def two_line_label(text: str, width: int, name: str = "cardTitle") -> QLabel:
    """A label showing at most two lines, ending in … if the title is longer."""
    lbl = label("", name)
    fm = QFontMetrics(lbl.font())
    lbl.setText(_elide_lines(text, fm, width, 2))
    lbl.setToolTip(text)
    lbl.setFixedHeight(fm.lineSpacing() * min(2, lbl.text().count("\n") + 1) + 2)
    return lbl


class EpisodeCard(QFrame):
    toggled = Signal(int)
    opened = Signal()

    def __init__(self, idx: int, anime: Anime | None, item, missed: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("episode")
        if not theme.COMPACT:
            self.setFixedWidth(theme.px(262))
        title = anime.name if anime else f"#{item.mal_id}"
        finale = bool(anime and anime.episodes_total and item.episode == anime.episodes_total)
        self.setProperty("missed", missed and not item.done)
        self.setProperty("finale", finale and not item.done)
        lay = hbox(self, 12, 10)
        lay.addWidget(Cover(anime.image_url if anime else "", title, 46, 66, 7))

        text = vbox(spacing=4)
        if theme.COMPACT:
            text.addWidget(ElidedLabel(title, "cardTitle"))
        else:
            text.addWidget(two_line_label(title, theme.px(262 - 46 - 24 - 20 - 36)))
        meta = hbox(spacing=6)
        meta.addWidget(label(f"Episode {item.episode}", "small"))
        if finale:
            meta.addWidget(badge("Finale"))
        elif item.episode == 1:
            meta.addWidget(badge("New", "badgeGreen"))
        meta.addStretch()
        text.addLayout(meta)
        text.addStretch()
        lay.addLayout(text, 1)

        check = QToolButton()
        check.setObjectName("check")
        check.setCheckable(True)
        check.setChecked(item.done)
        check.setText("✓" if item.done else "")
        check.setCursor(Qt.PointingHandCursor)
        check.setToolTip("Mark as unwatched" if item.done else "Mark as watched")
        check.clicked.connect(lambda: self.toggled.emit(idx))
        lay.addWidget(check, alignment=Qt.AlignVCenter)

        tips = [title]
        if item.note:
            tips.append(item.note)
        if missed and not item.done:
            tips.append("Missed — tick it if you watched it, or it'll be rescheduled on replan")
        if anime and anime.genres:
            tips.append(", ".join(anime.genres[:5]))
        self.setToolTip("\n".join(tips))
        if item.done:
            fx = QGraphicsOpacityEffect(self)
            fx.setOpacity(0.45)
            self.setGraphicsEffect(fx)
        self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.opened.emit()
        super().mouseReleaseEvent(event)


class DayRow(QFrame):
    """One day of the agenda: date and daily amount on the left, episode cards flowing right."""

    amount_changed = Signal(int, int)  # day, delta

    def __init__(self, day: int, on: date, today: date, amount: int, by_episodes: bool,
                 minutes: int, count: int, parent=None):
        super().__init__(parent)
        self.setObjectName("day")
        self.setProperty("today", on == today)
        self.setProperty("past", on < today)

        step = 1 if by_episodes else 15
        minus = QToolButton(text="−")
        plus = QToolButton(text="+")
        for b, d, tip in ((minus, -step, "Watch less this day"), (plus, step, "Watch more this day")):
            b.setObjectName("stepper")
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, d=d: self.amount_changed.emit(day, d))
        unit = ("episode" if amount == 1 else "episodes") if by_episodes else "min"
        value = label("Day off" if amount == 0 else f"{amount} {unit}", "small")
        value.setAlignment(Qt.AlignCenter)
        summary = f"{count} ep · {fmt_minutes(minutes)}" if count else ""

        if theme.COMPACT:
            # Phone: day header on top, then one card per line.
            col = vbox(self, 10, 12)
            head = hbox(spacing=8)
            head.addWidget(label(WEEKDAYS[on.weekday()], "h2"))
            if on == today:
                head.addWidget(badge("Today"))
            head.addStretch()
            head.addWidget(minus)
            value.setMinimumWidth(theme.px(78))
            head.addWidget(value)
            head.addWidget(plus)
            col.addLayout(head)
            col.addWidget(label(f"{on.day} {on:%B}" + (f"  ·  {summary}" if summary else ""), "faint"))
            self.cards = QWidget()
            self.flow = vbox(self.cards, 8)
            col.addWidget(self.cards)
            return

        row = hbox(self, 18, 14)
        side = vbox(spacing=6)
        head = hbox(spacing=8)
        head.addWidget(label(WEEKDAYS[on.weekday()], "h2"))
        if on == today:
            head.addWidget(badge("Today"))
        head.addStretch()
        side.addLayout(head)
        side.addWidget(label(f"{on.day} {on:%B}", "faint"))
        amt = hbox(spacing=6)
        amt.addWidget(minus)
        amt.addWidget(value, 1)
        amt.addWidget(plus)
        side.addLayout(amt)
        side.addWidget(label(summary, "faint"))
        side.addStretch()
        side_w = QWidget()
        side_w.setLayout(side)
        side_w.setFixedWidth(theme.px(176))
        row.addWidget(side_w)

        self.cards = QWidget()
        self.flow = FlowLayout(self.cards, 10)
        row.addWidget(self.cards, 1)

    def add(self, w: QWidget) -> None:
        self.flow.addWidget(w)

    def finish(self, empty_text: str) -> None:
        if self.flow.count() == 0:
            self.flow.addWidget(label(empty_text, "muted"))


class WatchingCard(QFrame):
    opened = Signal()

    def __init__(self, anime: Anime, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setProperty("clickable", True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedWidth(theme.px(156))
        lay = vbox(self, 8, 10)
        lay.addWidget(Cover(anime.image_url, anime.name, 134, 190, 10), alignment=Qt.AlignHCenter)
        lay.addWidget(two_line_label(anime.name, theme.px(134)))
        lay.addWidget(progress(anime))
        meta = hbox(spacing=6)
        meta.addWidget(label(progress_text(anime), "small"))
        meta.addStretch()
        if air := airing_text(anime):
            meta.addWidget(badge(air, "badgeAmber"))
        lay.addLayout(meta)
        lay.addStretch()
        self.setToolTip(", ".join(anime.genres[:6]))

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.opened.emit()
        super().mouseReleaseEvent(event)


def stat(value: str, caption: str) -> QFrame:
    frame, lay = card("stat", 14, 2)
    lay.addWidget(label(value, "statValue"))
    lay.addWidget(label(caption, "statLabel"))
    return frame


class WeekPage(QWidget):
    def __init__(self, win: MainWindow):
        super().__init__()
        self.win = win
        outer = vbox(self)
        self.area, inner = scroll_page()
        outer.addWidget(self.area)
        self.body = vbox(inner, 18, 28)

    def refresh(self) -> None:
        state, today = self.win.state, date.today()
        scroll = self.area.verticalScrollBar().value()
        clear(self.body)
        set_margins(self.body, page_margin())
        s = state.settings
        week = state.week
        start = date.fromisoformat(week.week_start) if week else today
        end = start + timedelta(days=6)

        # Header.
        head = hbox()
        titles = vbox(spacing=2)
        titles.addWidget(label("Your Week", "h1"))
        titles.addWidget(label(f"{start:%d %b} – {end:%d %b %Y}", "muted"))
        head.addLayout(titles)
        head.addStretch()
        if theme.COMPACT:  # buttons go on their own row below the title
            self.body.addLayout(head)
            head = hbox(spacing=8)
        settings_btn = QPushButton("Customize days")
        settings_btn.setObjectName("ghost")
        settings_btn.clicked.connect(lambda: self.win.open_settings("schedule"))
        replan = QPushButton("Replan from today")
        replan.setObjectName("primary")
        replan.setToolTip("Start a fresh 7-day plan today, ignoring past days (Ctrl R)")
        replan.clicked.connect(self.win.replan_fresh)
        self.replan_btn = replan
        head.addWidget(settings_btn)
        head.addWidget(replan)
        self.body.addLayout(head)

        items = week.items if week else []
        rotation = scheduler.current_rotation(state.library)

        # Stats.
        def mins(its):
            return sum(state.library[i.mal_id].minutes_per_episode for i in its if i.mal_id in state.library)
        todays = [i for i in items if i.day == (today - start).days] if start <= today <= end else []
        tiles = [stat(f"{sum(i.done for i in todays)} / {len(todays)}", "Watched today"),
                 stat(f"{sum(i.done for i in items)} / {len(items)}", "Episodes this plan"),
                 stat(fmt_minutes(mins(items)), "Planned watch time"),
                 stat(str(len(rotation)), "Shows watching")]
        stats = QGridLayout()
        stats.setSpacing(theme.px(10 if theme.COMPACT else 12))
        for n, tile in enumerate(tiles):
            if theme.COMPACT:
                stats.addWidget(tile, n // 2, n % 2)  # 2 × 2 on phones
            else:
                stats.addWidget(tile, 0, n)
        self.body.addLayout(stats)

        # Now watching.
        self.body.addWidget(label("Now watching", "h2"))
        if rotation:
            strip_area = QScrollArea()
            strip_area.setWidgetResizable(True)
            strip_area.setFrameShape(QFrame.NoFrame)
            strip_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            strip = QWidget()
            strip.setObjectName("page")
            row = hbox(strip, 12)
            for a in rotation:
                wc = WatchingCard(a)
                wc.opened.connect(lambda a=a: self.win.open_profile(a))
                row.addWidget(wc)
            row.addStretch()
            strip_area.setWidget(strip)
            strip_area.setFixedHeight(strip.sizeHint().height() + theme.px(14))
            self.body.addWidget(strip_area)
        else:
            frame, lay = card(margins=22)
            lay.addWidget(label("Your Watching list is empty", "cardTitle"))
            lay.addWidget(label("Only shows on your Watching list are scheduled. Import your MAL list, "
                                "or open Library, right-click a show and set it to Watching.",
                                "muted", wrap=True))
            self.body.addWidget(frame)

        # Days.
        sched_head = hbox()
        sched_head.addWidget(label("Schedule", "h2"))
        sched_head.addStretch()
        unit = "episodes" if s.plan_by == EPISODES else "minutes"
        sched_head.addWidget(label(f"Planning by {unit} per day · use − / + on a day to adjust", "faint"))
        self.body.addLayout(sched_head)
        self.first_day = None
        for day in range(scheduler.PLAN_DAYS):
            on = start + timedelta(days=day)
            day_items = [(n, i) for n, i in enumerate(items) if i.day == day]
            if on < today and not day_items:
                continue  # nothing happened that day; keep today near the top
            row = DayRow(on.weekday(), on, today, s.day_amount(on.weekday()), s.plan_by == EPISODES,
                         mins(i for _, i in day_items), len(day_items))
            row.amount_changed.connect(self.win.change_day_amount)
            for n, it in day_items:
                anime = state.library.get(it.mal_id)
                ep = EpisodeCard(n, anime, it, on < today)
                ep.toggled.connect(self.win.toggle_item)
                if anime:
                    ep.opened.connect(lambda a=anime: self.win.open_profile(a))
                row.add(ep)
            if on < today:
                empty = "—"
            elif s.day_amount(day) == 0:
                empty = "Day off — enjoy!"
            elif not rotation:
                empty = "Nothing to watch — add a show to your Watching list"
            else:
                empty = "All caught up — nothing new has aired yet"
            row.finish(empty)
            self.body.addWidget(row)
            if self.first_day is None:
                self.first_day = row
        self.body.addStretch()
        self.area.verticalScrollBar().setValue(scroll)


# =========================================================================== Up Next


class UpNextPage(QWidget):
    def __init__(self, win: MainWindow):
        super().__init__()
        self.win = win
        outer = vbox(self)
        self.area, inner = scroll_page()
        outer.addWidget(self.area)
        self.body = vbox(inner, 16, 28)

    def refresh(self) -> None:
        state = self.win.state
        scroll = self.area.verticalScrollBar().value()
        clear(self.body)
        set_margins(self.body, page_margin())
        titles = vbox(spacing=2)
        titles.addWidget(label("Up Next", "h1"))
        titles.addWidget(label("What takes over when each show finishes. The next season always "
                               "comes first — even if it isn't on your MAL list yet.", "muted", wrap=True))
        self.body.addLayout(titles)

        rotation = scheduler.current_rotation(state.library)
        self.body.addWidget(label("When a show finishes", "h2"))
        if not rotation:
            self.body.addWidget(label("Nothing on your Watching list yet.", "muted"))
        for a in sorted(rotation, key=lambda a: (a.episodes_total - a.episodes_watched)
                        if a.episodes_total else 10**6):
            self.body.addWidget(self._succession(a, scheduler.preview_next(state, a)))

        self.body.addSpacing(theme.px(8))
        self.body.addWidget(label("Plan to Watch picks", "h2"))
        self.body.addWidget(label("Used when a series has no next season. Ranked by your taste, MAL "
                                  "score, priority and variety.", "muted", wrap=True))
        excluded = scheduler.excluded_airing(state.library, state.settings.allow_airing)
        picks = rank(state.library, None, rotation, exclude=excluded)[:12]
        if not picks:
            self.body.addWidget(label("Your Plan to Watch list is empty.", "muted"))
        for n, sug in enumerate(picks, 1):
            self.body.addWidget(self._pick_row(n, sug))
        self.body.addStretch()
        self.area.verticalScrollBar().setValue(scroll)

    def _succession(self, current: Anime, sug) -> QFrame:
        compact = theme.COMPACT
        frame, outer = card(margins=14, spacing=10 if compact else 16, horizontal=not compact)
        lay = hbox(spacing=12) if compact else outer
        if compact:
            outer.addLayout(lay)
        frame.setProperty("clickable", True)
        Clickable(frame).clicked.connect(lambda: self.win.open_profile(current))
        frame.setToolTip(f"Open {current.name}")
        lay.addWidget(Cover(current.image_url, current.name, 70, 100, 8))
        left = vbox(spacing=4)
        left.addWidget(label("WHEN THIS FINISHES", "faint"))
        t = label(current.name, "cardTitle", wrap=True)
        left.addWidget(t)
        if current.episodes_total:
            n = current.episodes_total - current.episodes_watched
            left.addWidget(label(f"{n} episode{'s' if n != 1 else ''} left", "small"))
        else:
            left.addWidget(label(progress_text(current), "small"))
        left.addWidget(progress(current))
        left.addStretch()
        lw = QWidget()
        lw.setLayout(left)
        if compact:
            lay.addWidget(lw, 1)
            outer.addWidget(label("↓", "arrow"), alignment=Qt.AlignHCenter)
            lay = hbox(spacing=12)
            outer.addLayout(lay)
        else:
            lw.setFixedWidth(theme.px(230))
            lay.addWidget(lw)
            lay.addWidget(label("→", "arrow"), alignment=Qt.AlignVCenter)

        if sug is None:
            lay.addWidget(label("Nothing to follow it — no next season and your Plan to Watch "
                                "list is empty.", "muted", wrap=True), 1)
            return frame
        nxt = sug.anime
        lay.addWidget(Cover(nxt.image_url, nxt.name, 70, 100, 8))
        right = vbox(spacing=4)
        if sug.kind == SERIES:
            kind = ("Next season · will be added from MAL", "badgeAmber") \
                if nxt.mal_id not in self.win.state.library else ("Next season", "badgeGreen")
        else:
            kind = ("From Plan to Watch", "badge")
        right.addWidget(badge(*kind), alignment=Qt.AlignLeft)
        right.addWidget(label(nxt.name, "bigTitle", wrap=True))
        for _, text in sug.reasons[:3]:
            right.addWidget(label(text, "small", wrap=True))
        right.addStretch()
        lay.addLayout(right, 1)
        return frame

    def _pick_row(self, n: int, sug) -> QFrame:
        a = sug.anime
        frame, lay = card(margins=10, spacing=14, horizontal=True)
        frame.setProperty("clickable", True)
        Clickable(frame).clicked.connect(lambda: self.win.open_profile(a))
        num = label(str(n), "h2")
        num.setFixedWidth(theme.px(26))
        num.setAlignment(Qt.AlignCenter)
        lay.addWidget(num)
        lay.addWidget(Cover(a.image_url, a.name, 48, 68, 6))
        mid = vbox(spacing=4)
        top = hbox(spacing=8)
        # A plain label can't shrink below its text width, which would push the page wider
        # than a phone screen; the elided one shrinks with "…".
        top.addWidget(ElidedLabel(a.name, "cardTitle") if theme.COMPACT else label(a.name, "cardTitle"),
                      1 if theme.COMPACT else 0)
        if a.mean_score:
            top.addWidget(badge(f"★ {a.mean_score:.2f}", "badgeAmber"))
        top.addWidget(label(f"{a.episodes_total or '?'} eps", "faint"))
        top.addStretch()
        mid.addLayout(top)
        good = [t for p, t in sug.reasons if p > 0][:3]
        bad = [t for p, t in sug.reasons if p < 0][:2]
        text = "  ·  ".join(good)
        if bad:
            text += ("  ·  " if text else "") + "  ·  ".join(f"<span style='color:{theme.DANGER}'>{t}</span>" for t in bad)
        mid.addWidget(label(text, "small", wrap=True, rich=True))
        lay.addLayout(mid, 1)
        start = QPushButton("Start watching")
        start.setObjectName("primary")
        start.clicked.connect(lambda: self.win.start_show(a))
        never = QPushButton("Never suggest")
        never.setObjectName("ghost")
        never.clicked.connect(lambda: self.win.toggle_excluded(a))
        if theme.COMPACT:  # buttons under the text on phones
            btns = hbox(spacing=8)
            btns.addStretch()
            btns.addWidget(never)
            btns.addWidget(start)
            mid.addLayout(btns)
        else:
            lay.addWidget(never)
            lay.addWidget(start)
        return frame


# =========================================================================== Library


ID_ROLE = Qt.UserRole + 1
STATUS_ROLE = Qt.UserRole + 2
SORT_ROLE = Qt.UserRole + 3
SEARCH_ROLE = Qt.UserRole + 4


class PosterDelegate(QStyledItemDelegate):
    def __init__(self, win: MainWindow, parent=None):
        super().__init__(parent)
        self.win = win

    cell: QSize | None = None  # set by LibraryPage (phones use a width-filling grid)

    def sizeHint(self, option, index) -> QSize:
        return self.cell or QSize(theme.px(172), theme.px(300))

    def paint(self, p: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        anime = self.win.state.library.get(index.data(ID_ROLE))
        if anime is None:
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = option.rect.adjusted(theme.px(6), theme.px(6), -theme.px(6), -theme.px(6))
        hovered = option.state & QStyle.State_MouseOver
        selected = option.state & QStyle.State_Selected
        path = QPainterPath()
        path.addRoundedRect(QRectF(r), theme.px(12), theme.px(12))
        p.fillPath(path, QColor(theme.SURFACE_2 if hovered or selected else theme.SURFACE))
        if selected:
            p.setPen(QPen(QColor(theme.ACCENT), 2))
            p.drawPath(path)

        pad = theme.px(8)
        cw = r.width() - 2 * pad
        ch = round(cw * 1.42)
        dpr = p.device().devicePixelRatioF() if p.device() else 1.0
        pix = cache().cover(anime.image_url, anime.name, cw, ch, theme.px(9), dpr)
        p.drawPixmap(r.left() + pad, r.top() + pad, pix)
        if anime.excluded:
            p.fillRect(QRect(r.left() + pad, r.top() + pad, cw, ch), QColor(0, 0, 0, 140))

        # Status pill on the cover.
        color = QColor(theme.STATUS_COLORS.get(anime.status, theme.MUTED))
        f = QFont(option.font)
        f.setPixelSize(theme.px(11))
        f.setBold(True)
        p.setFont(f)
        text = STATUS_LABELS.get(anime.status, anime.status)
        fm = QFontMetrics(f)
        pill = QRect(r.left() + pad + theme.px(6), r.top() + pad + theme.px(6),
                     fm.horizontalAdvance(text) + theme.px(14), fm.height() + theme.px(6))
        pp = QPainterPath()
        pp.addRoundedRect(QRectF(pill), pill.height() / 2, pill.height() / 2)
        p.fillPath(pp, theme.qcolor(theme.BG, 225))
        p.setPen(color)
        p.drawText(pill, Qt.AlignCenter, text)

        # Title and meta.
        y = r.top() + pad + ch + theme.px(8)
        f = QFont(option.font)
        f.setPixelSize(theme.px(13))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(theme.TEXT))
        fm = QFontMetrics(f)
        title_rect = QRect(r.left() + pad, y, cw, fm.lineSpacing() * 2)
        elided = _elide_lines(anime.name, fm, cw, 2)
        p.drawText(title_rect, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, elided)
        y += fm.lineSpacing() * 2 + theme.px(4)

        f.setBold(False)
        f.setPixelSize(theme.px(12))
        p.setFont(f)
        p.setPen(QColor(theme.MUTED))
        meta = progress_text(anime)
        if anime.mean_score:
            meta += f"   ★ {anime.mean_score:.2f}"
        p.drawText(QRect(r.left() + pad, y, cw, QFontMetrics(f).height()), Qt.AlignLeft, meta)
        p.restore()


def _elide_lines(text: str, fm: QFontMetrics, width: int, lines: int) -> str:
    words, out, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if fm.horizontalAdvance(trial) <= width or not cur:
            cur = trial
        else:
            out.append(cur)
            cur = w
            if len(out) == lines - 1:
                break
    rest = " ".join(words[len(" ".join(out + [cur]).split()):])
    last = f"{cur} {rest}".strip() if rest else cur
    out.append(last)
    return "\n".join(fm.elidedText(line, Qt.ElideRight, width) for line in out[:lines])


class LibraryFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.text, self.status = "", ""
        self.setSortRole(SORT_ROLE)

    def set_text(self, t: str) -> None:
        self.text = t.lower()
        self.invalidateFilter()

    def set_status(self, s: str) -> None:
        self.status = s
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent) -> bool:
        idx = self.sourceModel().index(row, 0, parent)
        if self.status and idx.data(STATUS_ROLE) != self.status:
            return False
        return self.text in (idx.data(SEARCH_ROLE) or "")


SORTS = [("Title", "title"), ("MAL score", "score"), ("Progress", "progress"), ("Recently started", "started")]


class LibraryPage(QWidget):
    def __init__(self, win: MainWindow):
        super().__init__()
        self.win = win
        self.root = root = vbox(self, 14, 28)
        self.header = QWidget()
        self.head_grid = QGridLayout(self.header)
        self.head_grid.setContentsMargins(0, 0, 0, 0)
        self.head_grid.setHorizontalSpacing(theme.px(8))
        self.head_grid.setVerticalSpacing(theme.px(10))
        self.titles = QWidget()
        titles = vbox(self.titles, 2)
        titles.addWidget(label("Library", "h1"))
        self.count = label("", "muted")
        titles.addWidget(self.count)
        self.search = QLineEdit(placeholderText="Search your list…")
        self.sort = QComboBox()
        for text, key in SORTS:
            self.sort.addItem(f"Sort: {text}", key)
        self.import_btn = QPushButton("Import")
        self.import_btn.setObjectName("ghost")
        imenu = QMenu(self.import_btn)
        imenu.addAction("From MAL export file…", win.import_file)
        imenu.addAction("From MAL username…", win.import_username)
        imenu.addSeparator()
        imenu.addAction("Refresh all show details", lambda: win.run_enrich(force=True))
        self.import_btn.setMenu(imenu)
        self._head_compact: bool | None = None
        root.addWidget(self.header)

        chip_area = QScrollArea()  # scrolls sideways when the chips don't fit (phones)
        chip_area.setWidgetResizable(True)
        chip_area.setFrameShape(QFrame.NoFrame)
        chip_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        chip_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        chip_host = QWidget()
        chip_host.setObjectName("page")
        chips = hbox(chip_host, 8)
        touch_scroll(chip_area)
        self.group = QButtonGroup(self)
        for n, (text, key) in enumerate([("All", "")] + [(STATUS_LABELS[s], s) for s in LIST_STATUSES]):
            b = QPushButton(text)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty("status", key)
            self.group.addButton(b, n)
            chips.addWidget(b)
            if key == "":
                b.setChecked(True)
        chips.addStretch()
        chip_area.setWidget(chip_host)
        chip_area.setFixedHeight(chip_host.sizeHint().height() + theme.px(2))
        root.addWidget(chip_area)

        self.model = QStandardItemModel()
        self.proxy = LibraryFilter(self)
        self.proxy.setSourceModel(self.model)
        self.view = QListView()
        self.view.setModel(self.proxy)
        self.view.setViewMode(QListView.IconMode)
        self.view.setResizeMode(QListView.Adjust)
        self.view.setMovement(QListView.Static)
        self.view.setUniformItemSizes(True)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.setMouseTracking(True)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.view.setItemDelegate(PosterDelegate(win, self.view))
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._menu)
        self.view.clicked.connect(lambda idx: self._open(idx))
        touch_scroll(self.view)
        self.view.viewport().installEventFilter(self)  # re-fit the grid when the view resizes
        root.addWidget(self.view, 1)
        self.hint = label("", "faint")
        root.addWidget(self.hint)

        self.search.textChanged.connect(self.proxy.set_text)
        self.group.buttonClicked.connect(lambda b: self.proxy.set_status(b.property("status")))
        self.sort.currentIndexChanged.connect(lambda _: self.refresh())
        cache().loaded.connect(lambda _: self.view.viewport().update())

    def _arrange_header(self) -> None:
        """Desktop: title left, controls right. Phone: title, then search, then sort + import."""
        if self._head_compact == theme.COMPACT:
            return
        self._head_compact = theme.COMPACT
        for w in (self.titles, self.search, self.sort, self.import_btn):
            self.head_grid.removeWidget(w)
        g = self.head_grid
        for c in range(4):
            g.setColumnStretch(c, 0)
        if theme.COMPACT:
            self.search.setMinimumWidth(0)
            g.addWidget(self.titles, 0, 0, 1, 2)
            g.addWidget(self.search, 1, 0, 1, 2)
            g.addWidget(self.sort, 2, 0)
            g.addWidget(self.import_btn, 2, 1)
            g.setColumnStretch(0, 1)
            self.hint.setText("Tap a show for its profile — status and progress are there")
        else:
            self.search.setMinimumWidth(theme.px(260))
            g.addWidget(self.titles, 0, 0)
            g.addWidget(self.search, 0, 1)
            g.addWidget(self.sort, 0, 2)
            g.addWidget(self.import_btn, 0, 3)
            g.setColumnStretch(0, 1)
            self.hint.setText("Click a show for its profile · right-click to change status or progress")
        set_margins(self.root, page_margin())

    def _update_grid(self) -> None:
        """Phones: as many columns as fit (at least 2), filling the width. Desktop: fixed cards."""
        delegate = self.view.itemDelegate()
        if theme.COMPACT:
            vw = max(1, self.view.viewport().width() - theme.px(4))
            cols = max(2, vw // theme.px(150))
            w = vw // cols
            size = QSize(w, round(w * 1.72))
        else:
            size = QSize(theme.px(172), theme.px(300))
        delegate.cell = size
        self.view.setGridSize(size)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_grid()

    def eventFilter(self, obj, event) -> bool:
        if obj is self.view.viewport() and event.type() == event.Type.Resize:
            self._update_grid()
        return False

    def refresh(self) -> None:
        self._arrange_header()
        state = self.win.state
        key = self.sort.currentData()
        self.model.clear()
        for a in state.library.values():
            item = QStandardItem(a.name)
            item.setData(a.mal_id, ID_ROLE)
            item.setData(" ".join(a.all_titles()).lower(), SEARCH_ROLE)
            item.setData(a.status, STATUS_ROLE)
            item.setEditable(False)
            if key == "score":
                sort_val = -a.mean_score
            elif key == "progress":
                sort_val = -(a.episodes_watched / a.episodes_total if a.episodes_total else 0)
            elif key == "started":
                sort_val = "".join(chr(0x10FFFF - ord(c)) for c in a.started_on) or "\U0010ffff"
            else:
                sort_val = a.name.lower()
            item.setData(sort_val, SORT_ROLE)
            self.model.appendRow(item)
        self.proxy.sort(0)
        counts = {s: 0 for s in LIST_STATUSES}
        for a in state.library.values():
            counts[a.status] = counts.get(a.status, 0) + 1
        self.count.setText(f"{len(state.library)} shows · {counts['watching']} watching · "
                           f"{counts['completed']} completed · {counts[PLAN_TO_WATCH]} plan to watch")
        self._update_grid()

    def _selected(self) -> Anime | None:
        idx = self.view.currentIndex()
        return self.win.state.library.get(idx.data(ID_ROLE)) if idx.isValid() else None

    def _open(self, idx) -> None:
        anime = self.win.state.library.get(idx.data(ID_ROLE))
        if anime:
            self.win.open_profile(anime)

    def _menu(self, pos) -> None:
        from PySide6.QtWidgets import QMenu
        idx = self.view.indexAt(pos)
        if not idx.isValid():
            return
        self.view.setCurrentIndex(idx)
        anime = self._selected()
        menu = QMenu(self)
        status_menu = menu.addMenu("Set status")
        for s in LIST_STATUSES:
            act = status_menu.addAction(STATUS_LABELS[s])
            act.setCheckable(True)
            act.setChecked(anime.status == s)
            act.triggered.connect(lambda _=False, s=s: self.win.set_status(anime, s))
        menu.addAction("Set episodes watched…", self._edit_progress)
        menu.addSeparator()
        excl = menu.addAction("Never suggest this")
        excl.setCheckable(True)
        excl.setChecked(anime.excluded)
        excl.triggered.connect(lambda: self.win.toggle_excluded(anime))
        menu.addAction("Open on MyAnimeList", lambda: self.win.open_mal(anime))
        menu.exec(self.view.viewport().mapToGlobal(pos))

    def _edit_progress(self) -> None:
        anime = self._selected()
        if anime:
            self.win.edit_progress(anime)
