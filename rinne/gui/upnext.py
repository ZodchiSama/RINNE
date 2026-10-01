"""Up Next: what replaces each show you're watching, and new seasons."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QPushButton, QWidget

from .. import scheduler
from ..i18n import _
from ..models import Anime
from ..recommender import SERIES, rank
from . import theme
from .common import (
    Clickable, ElidedLabel, badge, button_row, card, clear, hbox, label, page_margin, progress, progress_text,
    scroll_page, set_margins, vbox,
)
from .images import Cover

if TYPE_CHECKING:
    from .window import MainWindow



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
        titles.addWidget(label(_("Up Next"), "h1"))
        titles.addWidget(label("What takes over when each show finishes. The next season always "
                               "comes first — even if it isn't on your MAL list yet.", "muted", wrap=True))
        self.body.addLayout(titles)

        news = getattr(self.win, "announcements", None) or []
        if news:
            self.body.addWidget(label("New seasons", "h2"))
            self.body.addWidget(label("Sequels of shows you've watched that are airing or announced — and not on "
                                      "your list yet.", "muted", wrap=True))
            for entry in news[:8]:
                self.body.addWidget(self._announcement(entry))
            self.body.addSpacing(theme.px(8))

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
        image = nxt.image_url
        if not image:  # a season not on the list yet: the new-seasons check may have its cover
            node = next((r["node"] for r in getattr(self.win, "announcements", None) or []
                         if r["mal_id"] == nxt.mal_id), {})
            image = (node.get("coverImage") or {}).get("large", "")
        lay.addWidget(Cover(image, nxt.name, 70, 100, 8))
        right = vbox(spacing=4)
        if sug.kind == SERIES:
            kind = ("Next season · will be added from MAL", "badgeAmber") \
                if nxt.mal_id not in self.win.state.library else ("Next season", "badgeGreen")
        else:
            kind = ("From Plan to Watch", "badge")
        right.addWidget(badge(*kind), alignment=Qt.AlignLeft)
        right.addWidget(label(nxt.name, "bigTitle", wrap=True))
        for _points, text in sug.reasons[:3]:
            right.addWidget(label(text, "small", wrap=True))
        right.addStretch()
        lay.addLayout(right, 1)
        return frame

    def _announcement(self, entry: dict) -> QFrame:
        from .profile import pick_title, when_text  # (profile imports this module)
        node = entry["node"]
        title = pick_title(node.get("title"))
        frame, lay = card(margins=12, spacing=14, horizontal=True)
        lay.addWidget(Cover((node.get("coverImage") or {}).get("large", ""), title, 58, 82, 8), alignment=Qt.AlignTop)
        col = vbox(spacing=4)
        airing = node.get("status") == "RELEASING"
        tags = [badge("Airing now", "badgeGreen") if airing else badge("Announced", "badgeAmber")]
        if node.get("format"):
            tags.append(badge(node["format"].replace("_", " "), "chipLabel"))
        col.addWidget(button_row(*tags, spacing=6))
        col.addWidget(label(title, "cardTitle", wrap=True))
        col.addWidget(label(when_text(node), "small", wrap=True))
        col.addWidget(label(f"Follows {entry['after'].name}", "faint", wrap=True))
        add = QPushButton("Add to Plan to Watch")
        add.setObjectName("ghost")
        add.clicked.connect(lambda: self.win.add_sequel(entry["mal_id"]))
        buttons = [add]
        if airing:
            start = QPushButton("Start watching")
            start.setObjectName("primary")
            start.clicked.connect(lambda: self.win.add_sequel(entry["mal_id"], start=True))
            buttons.append(start)
        col.addWidget(button_row(*buttons))
        lay.addLayout(col, 1)
        return frame

    def _pick_row(self, n: int, sug) -> QFrame:
        a = sug.anime
        frame, lay = card(margins=10, spacing=14, horizontal=True)
        frame.setProperty("clickable", True)
        Clickable(frame).clicked.connect(lambda: self.win.open_profile(a))
        if not theme.COMPACT:
            num = label(str(n), "h2")
            num.setFixedWidth(theme.px(26))
            num.setAlignment(Qt.AlignCenter)
            lay.addWidget(num)
        lay.addWidget(Cover(a.image_url, a.name, 48, 68, 6), alignment=Qt.AlignTop)
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
        if theme.COMPACT:  # buttons under the text on phones, wrapping if needed
            mid.addWidget(button_row(never, start))
        else:
            lay.addWidget(never)
            lay.addWidget(start)
        return frame


# =========================================================================== Library
