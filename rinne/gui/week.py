"""Your Week: the 7-day plan, with a card per show each day."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from PySide6.QtCore import QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QApplication, QFrame, QGraphicsOpacityEffect, QGridLayout, QPushButton, QScrollArea, QToolButton, QWidget,
)

from .. import artwork, models, scheduler
from ..i18n import _
from ..models import EPISODES, WEEKDAYS, Anime
from . import theme
from .common import (
    ElidedLabel, FlowLayout, airing_text, badge, button_row, card, clear, fmt_minutes, hbox, label,
    page_margin, progress, progress_text, scroll_page, set_margins, two_line_label, vbox, watch_button,
)
from .images import Cover

if TYPE_CHECKING:
    from .window import MainWindow



class ShowDayCard(QFrame):
    """One show's episodes for one day, stacked in a single card."""

    toggled = Signal(int)  # index into state.week.items
    opened = Signal()

    def __init__(self, anime: Anime | None, entries: list[tuple[int, object]], missed: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("episode")
        if not theme.COMPACT:
            self.setFixedWidth(theme.px(300))
        mal_id = entries[0][1].mal_id
        details = artwork.episodes(anime) if anime else {}
        title = anime.name if anime else f"#{mal_id}"
        total = anime.episodes_total if anime else 0
        all_done = all(it.done for _, it in entries)
        self.setProperty("missed", missed and not all_done)
        self.setProperty("finale", any(total and it.episode == total and not it.done for _, it in entries))

        lay = hbox(self, 12, 10)
        lay.addWidget(Cover(anime.image_url if anime else "", title, 46, 66, 7), alignment=Qt.AlignTop)
        col = vbox(spacing=4)
        if theme.COMPACT:
            col.addWidget(ElidedLabel(title, "cardTitle"))
        else:
            col.addWidget(two_line_label(title, theme.px(300 - 46 - 24 - 20)))
        eps = [it.episode for _, it in entries]
        if len(eps) > 1:
            span = f"Episodes {eps[0]}–{eps[-1]}" if eps == list(range(eps[0], eps[-1] + 1)) \
                else "Episodes " + ", ".join(map(str, eps))
            col.addWidget(label(span, "faint"))

        for idx, it in entries:
            row_w = QWidget()
            row = hbox(row_w, 8)
            ep = details.get(str(it.episode)) or {}
            ep_title = artwork.episode_title(ep, models.title_language) if ep else ""
            if ep.get("image"):
                row.addWidget(Cover(ep["image"], str(it.episode), 52, 30, 4))
            text = vbox(spacing=0)
            head = hbox(spacing=6)
            head.addWidget(label(f"Episode {it.episode}", "small"))
            if total and it.episode == total:
                head.addWidget(badge("Finale"))
            elif it.episode == 1:
                head.addWidget(badge("New", "badgeGreen"))
            head.addStretch()
            text.addLayout(head)
            if ep_title:
                text.addWidget(ElidedLabel(ep_title, "epTitle"))
            row.addLayout(text, 1)
            check = QToolButton()
            check.setObjectName("check")
            check.setCheckable(True)
            check.setChecked(it.done)
            check.setText("✓" if it.done else "")
            check.setCursor(Qt.PointingHandCursor)
            check.setToolTip(("Mark as unwatched" if it.done else "Mark as watched") + f" — episode {it.episode}")
            check.clicked.connect(lambda _=False, i=idx: self.toggled.emit(i))
            row.addWidget(check)
            tips = [f"{title} — episode {it.episode}" + (f": {ep_title}" if ep_title else "")]
            if ep.get("airdate"):
                tips.append(f"Aired {ep['airdate']}")
            if ep.get("overview"):
                tips.append(ep["overview"][:220] + ("…" if len(ep["overview"]) > 220 else ""))
            if it.note:
                tips.append(it.note)
            if missed and not it.done:
                tips.append("Missed — tick it if you watched it, or it'll be rescheduled on replan")
            row_w.setToolTip("\n".join(tips))
            if it.done and not all_done:
                fx = QGraphicsOpacityEffect(row_w)
                fx.setOpacity(0.45)
                row_w.setGraphicsEffect(fx)
            col.addWidget(row_w)
        watch = watch_button(anime) if anime else None
        if watch is not None and not all_done:
            col.addWidget(watch, alignment=Qt.AlignLeft)
        col.addStretch()
        lay.addLayout(col, 1)

        if anime and anime.genres:
            self.setToolTip(f"{title}\n{', '.join(anime.genres[:5])}")
        if all_done:
            fx = QGraphicsOpacityEffect(self)
            fx.setOpacity(0.45)
            self.setGraphicsEffect(fx)
        self.setCursor(Qt.PointingHandCursor)
        self.mal_id = mal_id
        self.on: date | None = None  # set by the week page; enables dragging
        self._press = None
        self._dragged = False

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._press, self._dragged = event.position().toPoint(), False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (self._press is not None and self.on is not None and event.buttons() & Qt.LeftButton
                and (event.position().toPoint() - self._press).manhattanLength() >= QApplication.startDragDistance()):
            self._dragged = True
            self._press = None
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(DRAG_MIME, f"{self.mal_id}|{self.on.isoformat()}".encode())
            drag.setMimeData(mime)
            pix = self.grab()
            drag.setPixmap(pix.scaledToWidth(max(1, pix.width() * 3 // 4), Qt.SmoothTransformation))
            drag.setHotSpot(QPoint(theme.px(20), theme.px(20)))
            drag.exec(Qt.MoveAction)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and not self._dragged:
            self.opened.emit()
        self._press = None
        super().mouseReleaseEvent(event)


DRAG_MIME = "application/x-rinne-show"


class DayRow(QFrame):
    """One day of the agenda: date and daily amount on the left, episode cards flowing right."""

    amount_changed = Signal(int, int)  # day, delta
    moved = Signal(int, object, object)  # mal_id, from date, to date
    reordered = Signal(object, list)  # date, mal_ids in the new order

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
            col = vbox(self, 8, 12)
            head = hbox(spacing=8)
            head.addWidget(label(WEEKDAYS[on.weekday()], "h2"))
            if on == today:
                head.addWidget(badge("Today"))
            head.addStretch()
            col.addLayout(head)
            sub = hbox(spacing=6)
            sub.addWidget(label(f"{on.day} {on:%b}" + (f" · {summary}" if summary else ""), "faint"), 1)
            sub.addWidget(minus)
            value.setMinimumWidth(theme.px(64))
            sub.addWidget(value)
            sub.addWidget(plus)
            col.addLayout(sub)
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

    # ---- drag & drop: move a show here from another day, or reorder within this day
    def enable_drops(self, on: date) -> None:
        self.on = on
        self.setAcceptDrops(True)

    def _cards(self) -> list:
        return [c for c in self.cards.findChildren(ShowDayCard, options=Qt.FindDirectChildrenOnly)]

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(DRAG_MIME):
            event.acceptProposedAction()
            self.setProperty("dropTarget", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event) -> None:
        self.setProperty("dropTarget", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event) -> None:
        self.dragLeaveEvent(event)
        try:
            mal_s, from_s = bytes(event.mimeData().data(DRAG_MIME)).decode().split("|")
            mal_id, from_date = int(mal_s), date.fromisoformat(from_s)
        except ValueError:
            return
        event.acceptProposedAction()
        if from_date != self.on:
            self.moved.emit(mal_id, from_date, self.on)
            return
        # Same day: put the dragged show before the card it was dropped on.
        pos = self.cards.mapFrom(self, event.position().toPoint())
        order = [c.mal_id for c in self._cards()]
        target = next((c.mal_id for c in self._cards() if c.geometry().contains(pos)), None)
        if mal_id in order:
            order.remove(mal_id)
        order.insert(order.index(target) if target in order else len(order), mal_id)
        self.reordered.emit(self.on, order)

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
        flags = [badge("Paused", "chipLabel")] if anime.paused else []
        if anime.pinned:
            flags.append(badge("📌 Pinned"))
        if anime.pace:
            flags.append(badge(f"{anime.pace}/day", "chipLabel"))
        if flags:
            lay.addWidget(button_row(*flags, spacing=4))
        if anime.paused:
            fx = QGraphicsOpacityEffect(self)
            fx.setOpacity(0.55)
            self.setGraphicsEffect(fx)
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
        titles.addWidget(label(_("Your Week"), "h1"))
        titles.addWidget(label(f"{start:%d %b} – {end:%d %b %Y}", "muted"))
        head.addLayout(titles)
        head.addStretch()
        settings_btn = QPushButton("Customize days")
        settings_btn.setObjectName("ghost")
        settings_btn.clicked.connect(lambda: self.win.open_settings("schedule"))
        replan = QPushButton("Replan from today")
        replan.setObjectName("primary")
        replan.setToolTip("Start a fresh 7-day plan today, ignoring past days (Ctrl R)")
        replan.clicked.connect(self.win.replan_fresh)
        self.replan_btn = replan
        if theme.COMPACT:  # buttons on their own (wrapping) row below the title
            self.body.addLayout(head)
            self.body.addWidget(button_row(settings_btn, replan))
        else:
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

        # Now watching (paused shows too, so they can be found and resumed).
        self.body.addWidget(label("Now watching", "h2"))
        watching_all = scheduler.current_rotation(state.library, include_paused=True)
        if watching_all:
            strip_area = QScrollArea()
            strip_area.setWidgetResizable(True)
            strip_area.setFrameShape(QFrame.NoFrame)
            strip_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            strip = QWidget()
            strip.setObjectName("page")
            row = hbox(strip, 12)
            for a in watching_all:
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
        if not theme.COMPACT:  # too long for a phone header; the − / + are self-explanatory there
            sched_head.addWidget(label(f"Planning by {unit} per day · use − / + on a day to adjust", "faint"))
        self.body.addLayout(sched_head)
        self.first_day = None
        for day in range(scheduler.PLAN_DAYS):
            on = start + timedelta(days=day)
            day_items = [(n, i) for n, i in enumerate(items) if i.day == day]
            if on < today and not day_items:
                continue  # nothing happened that day; keep today near the top
            row = DayRow(on.weekday(), on, today, s.day_amount(on.weekday()), s.plan_by == EPISODES,
                         mins(i for _idx, i in day_items), len(day_items))
            row.amount_changed.connect(self.win.change_day_amount)
            if on >= today:
                row.enable_drops(on)
                row.moved.connect(self.win.move_show)
                row.reordered.connect(self.win.reorder_day)
            # One card per show, in the plan's order (fewest episodes left first).
            groups: dict[int, list] = {}
            for n, it in day_items:
                groups.setdefault(it.mal_id, []).append((n, it))
            for mal_id, entries in groups.items():
                anime = state.library.get(mal_id)
                show_card = ShowDayCard(anime, entries, on < today)
                if on >= today:
                    show_card.on = on  # draggable
                show_card.toggled.connect(self.win.toggle_item)
                if anime:
                    show_card.opened.connect(lambda a=anime: self.win.open_profile(a))
                row.add(show_card)
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
