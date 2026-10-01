"""First-run welcome hub: logo and name up front, then a quick setup, then the guided tour."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import QButtonGroup, QFrame, QLabel, QPushButton, QScrollArea, QWidget

from .. import DISPLAY_NAME, __version__
from ..models import EPISODES, TITLE_LANGUAGES
from . import icons, theme
from .common import FlowLayout, Switch, button_row, card, clear, hbox, label, vbox
from .common import asset
from .settings import theme_card

if TYPE_CHECKING:
    from .window import MainWindow

STEPS = ["Welcome", "Your list", "Your week", "Make it yours", "Ready"]


class Glow(QLabel):
    """The round logo on a soft accent glow."""

    def __init__(self, size: int):
        super().__init__()
        self.size_px = theme.px(size)
        self.setFixedSize(round(self.size_px * 1.5), round(self.size_px * 1.5))
        dpr = self.devicePixelRatioF() or 1.0
        pix = QPixmap(asset("logo-round.png")).scaled(round(self.size_px * dpr), round(self.size_px * dpr),
                                                      Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pix.setDevicePixelRatio(dpr)
        self.pix = pix

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = self.rect().center()
        g = QRadialGradient(c, self.width() / 2)
        g.setColorAt(0.0, theme.qcolor(theme.ACCENT, 110))
        g.setColorAt(0.55, theme.qcolor(theme.ACCENT_2, 35))
        g.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(g)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(self.rect()))
        p.drawPixmap(round(c.x() - self.size_px / 2), round(c.y() - self.size_px / 2), self.pix)


class WelcomePage(QWidget):
    def __init__(self, win: MainWindow):
        super().__init__()
        self.win = win
        self.step = 0
        self.import_note = ""
        outer = vbox(self)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QFrame.NoFrame)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("page")
        self.area.setWidget(inner)
        outer.addWidget(self.area)
        center = hbox(inner)
        center.addStretch()
        self.column = QWidget()
        self.column.setMaximumWidth(theme.px(760))
        self.column.setMinimumWidth(theme.px(560))
        self.body = vbox(self.column, 18, 32)
        center.addWidget(self.column, 3)
        center.addStretch()

    # ------------------------------------------------------------------ flow

    def go(self, step: int) -> None:
        self.step = max(0, min(len(STEPS) - 1, step))
        self.refresh()
        self.area.verticalScrollBar().setValue(0)

    def refresh(self) -> None:
        clear(self.body)
        m = theme.px(16 if theme.COMPACT else 32)
        self.body.setContentsMargins(m, m, m, m)
        self.column.setMinimumWidth(0 if theme.COMPACT else theme.px(560))
        self.body.addStretch()
        if self.step > 0:
            self.body.addLayout(self._dots())
        getattr(self, f"_step_{self.step}")()
        self.body.addStretch()

    def _dots(self):
        row = hbox(spacing=8)
        row.addStretch()
        for n, name in enumerate(STEPS):
            dot = QLabel()
            active = n == self.step
            dot.setFixedSize(theme.px(26 if active else 8), theme.px(8))
            color = theme.ACCENT if n <= self.step else theme.SURFACE_3
            dot.setStyleSheet(f"background: {color}; border-radius: {theme.px(4)}px;")
            dot.setToolTip(name)
            row.addWidget(dot)
        row.addStretch()
        return row

    def _nav(self, next_text: str = "Continue", back: bool = True, skip_text: str = ""):
        row = hbox(spacing=10)
        if back:
            b = QPushButton("Back")
            b.setObjectName("ghost")
            b.clicked.connect(lambda: self.go(self.step - 1))
            row.addWidget(b)
        row.addStretch()
        if skip_text:
            s = QPushButton(skip_text)
            s.setObjectName("ghost")
            s.clicked.connect(lambda: self.go(self.step + 1))
            row.addWidget(s)
        n = QPushButton(next_text)
        n.setObjectName("primary")
        n.setDefault(True)
        n.clicked.connect(lambda: self.go(self.step + 1))
        row.addWidget(n)
        self.body.addSpacing(theme.px(8))
        self.body.addLayout(row)

    def _title(self, title: str, subtitle: str) -> None:
        t = label(title, "welcomeTitle", wrap=True)
        t.setAlignment(Qt.AlignCenter)
        self.body.addWidget(t)
        s = label(subtitle, "muted", wrap=True)
        s.setAlignment(Qt.AlignCenter)
        self.body.addWidget(s)
        self.body.addSpacing(theme.px(6))

    # ------------------------------------------------------------------ steps

    def _step_0(self) -> None:
        self.body.addWidget(Glow(140 if theme.COMPACT else 190), alignment=Qt.AlignHCenter)
        name = label(DISPLAY_NAME, "heroName")
        name.setAlignment(Qt.AlignCenter)
        self.body.addWidget(name)
        sub = label("輪廻 — the cycle of rebirth", "heroSub")
        sub.setAlignment(Qt.AlignCenter)
        self.body.addWidget(sub)
        tag = label("Your weekly anime planner. When a show ends, its next season is reborn in its place.",
                    "muted", wrap=True)
        tag.setAlignment(Qt.AlignCenter)
        self.body.addWidget(tag)
        self.body.addSpacing(theme.px(10))

        feats = (vbox if theme.COMPACT else hbox)(spacing=12)
        for ic, head, text in [
            ("week", "Plans your week", "A Sunday-to-Saturday plan built from the shows you're watching."),
            ("stats", "Daily goals", "Finish a day's episodes to check it off. Stats keeps your completed "
             "and failed days."),
            ("next", "Follows every series", "Finish a season and the next one takes its slot automatically."),
            ("sparkle", "Stays in sync", "Connect MyAnimeList or AniList and your progress is saved there "
             "as you watch."),
        ]:
            frame, lay = card(margins=16, spacing=6)
            ico = QLabel()
            ico.setPixmap(icons.pixmap(ic, theme.ACCENT, 26))
            lay.addWidget(ico)
            lay.addWidget(label(head, "cardTitle"))
            lay.addWidget(label(text, "small", wrap=True))
            lay.addStretch()
            feats.addWidget(frame, 1)
        self.body.addLayout(feats)
        self.body.addSpacing(theme.px(10))

        start = QPushButton("Get started")
        start.setObjectName("primary")
        start.setMinimumWidth(theme.px(220))
        start.setMinimumHeight(theme.px(44))
        start.clicked.connect(lambda: self.go(1))
        self.body.addWidget(start, alignment=Qt.AlignHCenter)
        skip = QPushButton("Skip setup")
        skip.setObjectName("link")
        skip.clicked.connect(lambda: self.win.finish_welcome(tour=False))
        self.body.addWidget(skip, alignment=Qt.AlignHCenter)
        foot = label(f"v{__version__}  ·  by Zodchi", "faint")
        foot.setAlignment(Qt.AlignCenter)
        self.body.addWidget(foot)

    def _step_1(self) -> None:
        self._title("Connect your list", "Sign in to MyAnimeList or AniList: Rinne brings in your list and "
                    "keeps your account up to date as you tick episodes. You can do this later from "
                    "Connect in the sidebar.")
        n = len(self.win.state.library)
        if n:
            ok, lay = card(margins=16, spacing=4)
            ok.setProperty("accent", True)
            watching = sum(a.status == "watching" for a in self.win.state.library.values())
            lay.addWidget(label(f"✓  {n} shows in your library · {watching} watching", "cardTitle"))
            lay.addWidget(label(self.import_note or "Covers and details load in the background.", "small", wrap=True))
            self.body.addWidget(ok)

        from .connect import SERVICES, connected_name
        row = (vbox if theme.COMPACT else hbox)(spacing=12)
        for key, name, how in SERVICES:
            frame, cl = card(margins=20, spacing=8)
            cl.addWidget(label(name, "h2"))
            user = connected_name(self.win, key)
            if user:
                cl.addWidget(label(f"✓ Connected as {user}", "small"))
            else:
                cl.addWidget(label(how, "small", wrap=True))
                go = QPushButton(f"Connect {name}")
                go.setObjectName("primary")
                go.setMinimumHeight(theme.px(42))
                go.clicked.connect(lambda _=False, k=key: self._connect(k))
                cl.addWidget(go)
            cl.addStretch()
            row.addWidget(frame, 1)
        self.body.addLayout(row)

        manual = QPushButton("Don't want to connect? Import a file or username instead")
        manual.setObjectName("link")
        manual.clicked.connect(self._manual)
        self.body.addWidget(manual, alignment=Qt.AlignLeft)
        self._nav("Continue" if n else "Skip for now")

    def _connect(self, key: str) -> None:
        def result(msg) -> None:
            self.import_note = msg or "Connected. Bringing in your list…"
            self.refresh()
        (self.win.connect_mal if key == "mal" else self.win.connect_anilist)(result)

    def _manual(self) -> None:
        before = len(self.win.state.library)
        self.win.import_manually()
        added = len(self.win.state.library) - before
        if added:
            self.import_note = f"Added {added} shows. Fetching covers and details in the background…"
        self.refresh()

    def _step_2(self) -> None:
        s = self.win.state.settings
        self._title("How much do you watch?", "Pick a pace. You can fine-tune every day later "
                    "(Settings → Schedule, or − / + on each day).")
        s.plan_by = EPISODES
        for title, days, options in [("Weekdays", range(0, 5), (1, 2, 3, 4, 6)),
                                     ("Weekends", range(5, 7), (0, 2, 4, 6, 8))]:
            frame, lay = card(margins=18, spacing=10)
            lay.addWidget(label(title, "h2"))
            chips = []
            group = QButtonGroup(frame)
            current = s.daily_episodes[days[0]]
            for n in options:
                b = QPushButton("Day off" if n == 0 else f"{n} episode{'s' if n != 1 else ''}")
                b.setObjectName("chip")
                b.setCheckable(True)
                b.setChecked(n == current)
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _=False, n=n, days=days: self._set_days(days, n))
                group.addButton(b)
                chips.append(b)
            lay.addWidget(button_row(*chips))
            self.body.addWidget(frame)
        weekly = sum(s.daily_episodes)
        note = label(f"That's about {weekly} episodes a week "
                     f"(~{round(weekly * 24 / 60)} hours).", "small")
        note.setAlignment(Qt.AlignCenter)
        self.body.addWidget(note)
        self._nav()

    def _set_days(self, days, n: int) -> None:
        s = self.win.state.settings
        for d in days:
            s.daily_episodes[d] = n
        self.win.save()
        self.refresh()

    def _step_3(self) -> None:
        s = self.win.state.settings
        self._title("Make it yours", "Change any of this later in Settings.")
        themes, tl = card(margins=18, spacing=10)
        tl.addWidget(label("Theme", "h2"))
        flow = FlowLayout(spacing=10)
        for key, pal in theme.PALETTES.items():
            flow.addWidget(theme_card(key, pal, key == theme.current,
                                      lambda k=key: (self.win.set_theme(k), self.refresh()),
                                      width=140 if theme.COMPACT else 156))
        host = QWidget()
        host.setLayout(flow)
        tl.addWidget(host)
        self.body.addWidget(themes)

        opts, ol = card(margins=18, spacing=12)
        row = hbox(spacing=10)
        text = vbox(spacing=2)
        text.addWidget(label("Titles", "settingTitle"))
        text.addWidget(label("How show names are written.", "small"))
        row.addLayout(text, 1)
        seg_box = QFrame()
        seg_box.setObjectName("segBox")
        seg = hbox(seg_box, 2, 3)
        group = QButtonGroup(seg_box)
        for key, name in TITLE_LANGUAGES.items():
            b = QPushButton(name)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setChecked(key == s.title_language)
            b.clicked.connect(lambda _=False, k=key: self.win.set_title_language(k))
            group.addButton(b)
            seg.addWidget(b)
        row.addWidget(seg_box)
        ol.addLayout(row)
        options = [
            ("backdrop", "Background slideshow", "Full-HD art from today's shows behind the window.",
             "backdrop"),
            ("discord_enabled", "Discord Rich Presence",
             "Show “Watching Rinne” and today's next episode on your Discord profile.", "discord"),
            ("notify_new_episodes", "New-episode notifications",
             "A desktop notification when a show you're watching airs a new episode.", "save"),
        ]
        for attr, title, desc, kind in options:
            r = hbox(spacing=10)
            tx = vbox(spacing=2)
            tx.addWidget(label(title, "settingTitle"))
            tx.addWidget(label(desc, "small", wrap=True))
            r.addLayout(tx, 1)
            sw = Switch(getattr(s, attr))
            sw.toggled.connect(lambda on, a=attr, k=kind: (setattr(s, a, on), self.win.settings_changed(k)))
            r.addWidget(sw, alignment=Qt.AlignVCenter)
            ol.addLayout(r)
        self.body.addWidget(opts)
        self._nav()

    def _step_4(self) -> None:
        self.body.addWidget(Glow(120), alignment=Qt.AlignHCenter)
        self._title("You're all set", "Want a 30-second tour of where everything is?")
        row = hbox(spacing=10)
        row.addStretch()
        skip = QPushButton("Skip tour")
        skip.setObjectName("ghost")
        skip.clicked.connect(lambda: self.win.finish_welcome(tour=False))
        tour = QPushButton("Take the tour")
        tour.setObjectName("primary")
        tour.setMinimumWidth(theme.px(180))
        tour.clicked.connect(lambda: self.win.finish_welcome(tour=True))
        row.addWidget(skip)
        row.addWidget(tour)
        row.addStretch()
        self.body.addLayout(row)
        back = QPushButton("Back")
        back.setObjectName("link")
        back.clicked.connect(lambda: self.go(self.step - 1))
        self.body.addWidget(back, alignment=Qt.AlignHCenter)
