"""The Settings page. Changes apply immediately (no Save button)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QTime, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFileDialog, QFrame, QGridLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QRadioButton, QSlider, QSpinBox, QTimeEdit, QWidget,
)

from .. import DISPLAY_NAME, __version__
from ..models import EPISODES, MINUTES, TITLE_LANGUAGES, WEEKDAYS, Settings
from ..storage import cache_dir, data_dir, state_path
from . import files, theme
from ..platform import is_android
from .common import (
    Clickable, FlowLayout, Switch, badge, card, clear, hbox, label, set_margins, touch_scroll, vbox,
)
from .pages import scroll_page

if TYPE_CHECKING:
    from .window import MainWindow

SECTIONS = [
    ("general", "General"),
    ("appearance", "Appearance"),
    ("schedule", "Schedule"),
    ("notifications", "Notifications"),
    ("discord", "Discord"),
    ("data", "Library && Data"),  # && = a literal & in button text
    ("about", "About"),
]
START_PAGES = [("week", "Your Week"), ("next", "Up Next"), ("library", "Library")]
DISCORD_PORTAL = "https://discord.com/developers/applications"


def asset(name: str) -> str:
    return str(Path(__file__).resolve().parent.parent / "assets" / name)


def folder_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.exists() else 0


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


def theme_card(key: str, pal: dict, selected: bool, on_click, width: int = 190) -> QFrame:
    """A clickable preview of a theme's colours."""
    frame = QFrame()
    frame.setObjectName("themeCard")
    frame.setProperty("selected", selected)
    frame.setFixedWidth(theme.px(width))
    lay = vbox(frame, 8, 10)
    preview = QLabel()
    preview.setFixedHeight(theme.px(96))
    preview.setStyleSheet(
        f"background: {pal['BG']}; border-radius: {theme.px(8)}px; border: 1px solid {pal['BORDER']};")
    inner = vbox(preview, 6, 10)
    top = QLabel("Your Week")
    top.setStyleSheet(f"color: {pal['H1']}; font-weight: 800; font-size: {theme.px(14)}px;"
                      "background: transparent; border: none;")
    inner.addWidget(top)
    bar = QLabel()
    bar.setFixedHeight(theme.px(8))
    bar.setStyleSheet(f"border: none; border-radius: {theme.px(4)}px; background: qlineargradient("
                      f"x1:0, y1:0, x2:1, y2:0, stop:0 {pal['ACCENT']}, stop:1 {pal['ACCENT_2']});")
    inner.addWidget(bar)
    row = hbox(spacing=6)
    for c in (pal["SURFACE"], pal["SURFACE_2"], pal["SURFACE_3"]):
        chip = QLabel()
        chip.setFixedSize(theme.px(34), theme.px(22))
        chip.setStyleSheet(f"background: {c}; border-radius: {theme.px(5)}px; border: 1px solid {pal['BORDER']};")
        row.addWidget(chip)
    row.addStretch()
    inner.addLayout(row)
    lay.addWidget(preview)
    name_row = hbox()
    name_row.addWidget(label(pal["label"], "settingTitle"))
    name_row.addStretch()
    if selected:
        name_row.addWidget(badge("Active"))
    lay.addLayout(name_row)
    Clickable(frame).clicked.connect(on_click)
    return frame


class SettingsPage(QWidget):
    def __init__(self, win: MainWindow):
        super().__init__()
        self.win = win
        self.section = "general"
        root = hbox(self, 0)

        side = self.side = QFrame()
        side.setObjectName("page")
        side_lay = vbox(side, 4, 24)
        side_lay.addWidget(label("Settings", "h1"))
        side_lay.addSpacing(theme.px(10))
        self.nav = QButtonGroup(self)
        for n, (key, text) in enumerate(SECTIONS):
            b = QPushButton(text)
            b.setObjectName("subnav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty("key", key)
            self.nav.addButton(b, n)
            side_lay.addWidget(b)
        side_lay.addStretch()
        side.setFixedWidth(theme.px(220))
        root.addWidget(side)
        self.nav.idClicked.connect(lambda n: self.show_section(SECTIONS[n][0]))

        self.area, inner = scroll_page()
        self.body = vbox(inner, 14, 24)
        root.addWidget(self.area, 1)
        self._replan_timer = QTimer(self, singleShot=True, interval=500,
                                    timeout=lambda: self.win.settings_changed("replan"))

    # ------------------------------------------------------------------ navigation

    def show_section(self, key: str) -> None:
        self.section = key
        self.refresh()
        self.area.verticalScrollBar().setValue(0)

    def sections(self) -> list[tuple[str, str]]:
        """Discord needs the desktop Discord app, so its section is hidden on Android."""
        return [(k, v) for k, v in SECTIONS if not (k == "discord" and is_android())]

    def refresh(self) -> None:
        for b in self.nav.buttons():
            b.setChecked(b.property("key") == self.section)
            b.setVisible(b.property("key") in dict(self.sections()))
        clear(self.body)
        set_margins(self.body, 14 if theme.COMPACT else 24)
        self.side.setVisible(not theme.COMPACT)
        if theme.COMPACT:
            self.body.addWidget(self._section_tabs())
        s = self.win.state.settings
        getattr(self, f"_build_{self.section}")(s)
        self.body.addStretch()

    def _section_tabs(self) -> QWidget:
        """Phones: the section list as a sideways-scrolling row of tabs."""
        from PySide6.QtWidgets import QScrollArea
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        host.setObjectName("page")
        row = hbox(host, 6)
        for key, text in self.sections():
            b = QPushButton(text)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setChecked(key == self.section)
            b.clicked.connect(lambda _=False, k=key: self.show_section(k))
            row.addWidget(b)
        row.addStretch()
        area.setWidget(host)
        area.setFixedHeight(host.sizeHint().height() + theme.px(2))
        touch_scroll(area)
        return area

    # ------------------------------------------------------------------ building blocks

    def _header(self, title: str, subtitle: str = "") -> None:
        self.body.addWidget(label(title, "h1"))
        if subtitle:
            self.body.addWidget(label(subtitle, "muted", wrap=True))
        self.body.addSpacing(theme.px(4))

    def _group(self, title: str) -> None:
        self.body.addSpacing(theme.px(8))
        self.body.addWidget(label(title.upper(), "sideSection"))

    def _row(self, title: str, description: str, control: QWidget | None = None,
             stretch_control: bool = False) -> QFrame:
        frame = QFrame()
        frame.setObjectName("settingRow")
        # Phones: text above the control, except compact on/off switches which stay inline.
        stacked = theme.COMPACT and control is not None and not isinstance(control, Switch)
        row = (vbox if stacked else hbox)(frame, 10 if stacked else 16, 14)
        text = vbox(spacing=3)
        text.addWidget(label(title, "settingTitle", wrap=True))
        if description:
            desc = label(description, "small", wrap=True, rich=True)
            desc.setOpenExternalLinks(True)
            text.addWidget(desc)
        row.addLayout(text, 1)
        if control is not None:
            if stacked and stretch_control:
                row.addWidget(control)
            elif stacked:
                row.addWidget(control, alignment=Qt.AlignLeft)
            elif stretch_control:
                row.addWidget(control, 1)
            else:
                row.addWidget(control, alignment=Qt.AlignVCenter | Qt.AlignRight)
        self.body.addWidget(frame)
        return frame

    def _switch(self, title: str, description: str, attr: str, kind: str = "save",
                enabled: bool = True) -> Switch:
        s = self.win.state.settings
        sw = Switch(getattr(s, attr))
        sw.setEnabled(enabled)

        def changed(on: bool) -> None:
            setattr(s, attr, on)
            self.win.settings_changed(kind)

        sw.toggled.connect(changed)
        self._row(title, description, sw)
        return sw

    def _combo(self, items: list[tuple[str, str]], current: str) -> QComboBox:
        box = QComboBox()
        for key, text in items:
            box.addItem(text, key)
        idx = next((i for i, (k, _) in enumerate(items) if k == current), 0)
        box.setCurrentIndex(idx)
        box.setMinimumWidth(theme.px(170))
        return box

    def _button(self, text: str, fn, primary: bool = False) -> QPushButton:
        b = QPushButton(text)
        b.setObjectName("primary" if primary else "ghost")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(fn)
        return b

    # ------------------------------------------------------------------ General

    def _build_general(self, s: Settings) -> None:
        self._header("General", "How Rinne starts and behaves on your desktop.")
        self._group("Startup")
        start = self._combo(START_PAGES, s.start_page)
        start.currentIndexChanged.connect(lambda _: self._set("start_page", start.currentData()))
        self._row("Open on", "The page Rinne shows when it starts.", start)
        tray = self.win.tray_available() and not is_android()
        if not is_android():
            self._switch("Start minimized to the tray", "Launch quietly in the system tray." +
                         ("" if tray else " <i>(No system tray detected.)</i>"), "start_minimized", enabled=tray)
        self._switch("Check airing shows on startup",
                     "Refresh episode counts and next-episode dates for shows you're watching that "
                     "are still airing.", "refresh_on_startup")

        if not is_android():
            self._group("Window")
            self._switch("Keep running in the tray when closed",
                     "Closing the window hides Rinne to the tray so notifications keep working. "
                         "Quit from the tray menu." + ("" if tray else " <i>(No system tray detected.)</i>"),
                         "close_to_tray", kind="tray", enabled=tray)

        self._group("Getting started")
        again = QWidget()
        al = hbox(again, 8)
        al.addWidget(self._button("Show the welcome screen", self.win.show_welcome))
        al.addWidget(self._button("Take the tour", self.win.start_tour))
        self._row("Welcome & tour", "Run the first-launch setup or the guided tour again.", again)

        self._group("Titles")
        lang = self._combo(list(TITLE_LANGUAGES.items()), s.title_language)
        lang.currentIndexChanged.connect(lambda _: self.win.set_title_language(lang.currentData()))
        self._row("Show titles in", "Romaji, English or Japanese. Searching matches all three.", lang)

    # ------------------------------------------------------------------ Appearance

    def _build_appearance(self, s: Settings) -> None:
        self._header("Appearance", "Themes, the background slideshow and interface size.")
        self._group("Theme")
        flow = FlowLayout(spacing=12)
        for key, pal in theme.PALETTES.items():
            flow.addWidget(theme_card(key, pal, key == theme.current, lambda k=key: self._pick_theme(k),
                                      width=150 if theme.COMPACT else 190))
        host = QWidget()
        host.setLayout(flow)
        self.body.addWidget(host)

        self._group("Background slideshow")
        self._switch("Slideshow of today's shows",
                     "Full-HD fan art of today's shows fades behind the window.", "backdrop", kind="backdrop")
        secs = QSpinBox(minimum=4, maximum=120, value=s.slide_seconds)
        secs.setSuffix(" s")
        secs.valueChanged.connect(lambda v: self._set("slide_seconds", v, "backdrop"))
        self._row("Time per image", "How long each image stays before fading to the next.", secs)
        dim = self._combo([("0", "Light"), ("1", "Medium"), ("2", "Strong")], str(s.backdrop_dim))
        dim.currentIndexChanged.connect(lambda _: self._set("backdrop_dim", int(dim.currentData()), "backdrop"))
        self._row("Dimming", "How much the images are darkened (or lightened) behind the text.", dim)

        self._group("Size")
        zoom_w = QWidget()
        zl = hbox(zoom_w, 10)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(round(theme.MIN_ZOOM * 100), round(theme.MAX_ZOOM * 100))
        slider.setSingleStep(10)
        slider.setPageStep(10)
        slider.setValue(round(theme.zoom() * 100))
        slider.setFixedWidth(theme.px(220))
        value = label(f"{round(theme.zoom() * 100)}%", "small")
        value.setFixedWidth(theme.px(44))
        slider.valueChanged.connect(lambda v: value.setText(f"{v}%"))
        slider.sliderReleased.connect(lambda: self.win.set_zoom(slider.value() / 100))
        slider.valueChanged.connect(lambda v: None if slider.isSliderDown() else self.win.set_zoom(v / 100))
        zl.addWidget(slider)
        zl.addWidget(value)
        self._row("Interface size", "Also Ctrl + / Ctrl − / Ctrl 0, or Ctrl + mouse wheel.", zoom_w)

    def _theme_card(self, key: str, pal: dict, selected: bool) -> QFrame:
        return theme_card(key, pal, selected, lambda: self._pick_theme(key))

    def _pick_theme(self, key: str) -> None:
        self.win.set_theme(key)

    # ------------------------------------------------------------------ Schedule

    def _build_schedule(self, s: Settings) -> None:
        self._header("Schedule", "How much you watch each day and how finished shows are replaced.")
        self._group("Your week")
        mode_w = QWidget()
        ml = hbox(mode_w, 18)
        by_eps, by_min = QRadioButton("Episodes per day"), QRadioButton("Minutes per day")
        (by_eps if s.plan_by == EPISODES else by_min).setChecked(True)
        grp = QButtonGroup(mode_w)
        grp.addButton(by_eps)
        grp.addButton(by_min)
        ml.addWidget(by_eps)
        ml.addWidget(by_min)

        def mode_changed() -> None:
            new = EPISODES if by_eps.isChecked() else MINUTES
            if new != s.plan_by:
                s.plan_by = new
                self._replan_timer.start()
                QTimer.singleShot(0, self.refresh)

        by_eps.toggled.connect(lambda _: mode_changed())
        self._row("Plan by", "Count episodes, or budget minutes (longer episodes take more of the day).", mode_w)

        days_w = QWidget()
        grid = QGridLayout(days_w)
        grid.setHorizontalSpacing(theme.px(8))
        grid.setContentsMargins(0, 0, 0, 0)
        eps = s.plan_by == EPISODES
        spins = []
        for i, day in enumerate(WEEKDAYS):
            # Phones: two rows (Mon–Thu, Fri–Sun) so seven boxes fit the width.
            r, c = ((i // 4) * 2, i % 4) if theme.COMPACT else (0, i)
            grid.addWidget(label(day[:3], "small"), r, c, alignment=Qt.AlignCenter)
            sp = QSpinBox(minimum=0, maximum=24 if eps else 24 * 60, singleStep=1 if eps else 15)
            sp.setValue(s.day_amount(i))
            sp.setSuffix("" if theme.COMPACT else (" ep" if eps else " min"))
            sp.setAlignment(Qt.AlignCenter)
            sp.valueChanged.connect(lambda v, i=i: (s.set_day_amount(i, v), self._replan_timer.start()))
            grid.addWidget(sp, r + 1, c)
            spins.append(sp)
        self._row("Each day", "Set a day to 0 for a day off.", days_w, stretch_control=True)

        presets = QWidget()
        pl = hbox(presets, 6)
        base = 2 if eps else 60

        def apply(values):
            for sp, v in zip(spins, values):
                sp.setValue(v)

        for text, fn in [("Same every day", lambda: apply([spins[0].value() or base] * 7)),
                         ("Weekends ×2", lambda: apply([spins[0].value() or base] * 5 + [(spins[0].value() or base) * 2] * 2)),
                         ("Weekdays off", lambda: apply([0] * 5 + [max(spins[5].value(), spins[6].value()) or base * 2] * 2))]:
            b = QPushButton(text)
            b.setObjectName("chip")
            b.clicked.connect(fn)
            pl.addWidget(b)
        self._row("Quick set", "", presets)

        cap = QSpinBox(minimum=1, maximum=24, value=s.max_eps_per_show_per_day)
        cap.setSuffix(" ep")
        cap.valueChanged.connect(lambda v: self._set("max_eps_per_show_per_day", v, "replan"))
        self._row("Episodes of one show per day",
                  "Kept when possible. Exceeded only to fill a day when you're watching few shows.", cap)

        self._group("When a show finishes")
        self._switch("Start the next season automatically",
                     "Follows the sequel chain (adding it from AniList if it isn't on your list); "
                     "otherwise picks the best show from Plan to Watch.", "auto_replace")
        self._switch("Follow the series into movies, OVAs and specials",
                     "Off: only TV seasons count as the next entry; films and specials in between are skipped.",
                     "follow_extras", kind="replan")
        self._switch("Allow currently-airing shows as Plan to Watch picks",
                     "Airing shows are paced as episodes release.", "allow_airing", kind="replan")
        self.body.addWidget(self._button("Replan from today", self.win.replan_fresh, primary=True),
                            alignment=Qt.AlignLeft)

    # ------------------------------------------------------------------ Notifications

    def _build_notifications(self, s: Settings) -> None:
        self._header("Notifications", "Desktop notifications about your shows.")
        if is_android():
            self.body.addWidget(label("Notifications aren't available on Android yet — they're coming "
                                      "in a future version.", "muted", wrap=True))
            return
        self._switch("New episode aired",
                     "When a new episode of a show on your Watching list comes out.", "notify_new_episodes")
        self._switch("Daily reminder", "A summary of today's plan at a time you choose.", "daily_reminder")
        t = QTimeEdit(QTime.fromString(s.reminder_time, "HH:mm"))
        t.setDisplayFormat("HH:mm")
        t.timeChanged.connect(lambda v: self._set("reminder_time", v.toString("HH:mm")))
        self._row("Reminder time", "", t)
        self.body.addWidget(self._button("Send a test notification", self.win.test_notification),
                            alignment=Qt.AlignLeft)
        if not self.win.close_keeps_running():
            self.body.addWidget(label("Notifications only arrive while Rinne is running. Turn on "
                                      "“Keep running in the tray when closed” in General to get "
                                      "them with the window closed.", "faint", wrap=True))

    # ------------------------------------------------------------------ Discord

    def _build_discord(self, s: Settings) -> None:
        self._header("Discord", "Show what you're watching on your Discord profile (Rich Presence).")
        self._switch("Enable Rich Presence",
                     "Works automatically while the Discord desktop app is running: your profile shows "
                     "“Watching Rinne” with today's next episode.", "discord_enabled", kind="discord")

        self._group("What to show")
        self._switch("Show cover art", "Uses the show's cover as the large image.", "discord_show_cover", kind="discord")
        self._switch("Show a “View on MyAnimeList” button", "", "discord_buttons", kind="discord")
        self._switch("Private mode", "Hide show titles — only shows how much of today's plan you've watched.",
                     "discord_private", kind="discord")

        status_w = QWidget()
        sl = hbox(status_w, 10)
        self.discord_status = label(self.win.discord_status(), "small", wrap=True)
        sl.addWidget(self.discord_status, 1)
        sl.addWidget(self._button("Test connection", self._test_discord))
        self._row("Status", "Nothing showing? In Discord, turn on User Settings → Activity Privacy → "
                  "“Share your detected activities with others”.", status_w, stretch_control=True)

        self._group("Advanced")
        app_id = QLineEdit(s.discord_app_id)
        app_id.setPlaceholderText("Rinne (built in)")
        app_id.setMinimumWidth(theme.px(260))
        app_id.editingFinished.connect(lambda: self._set("discord_app_id", app_id.text().strip(), "discord"))
        self._row("Custom Application ID",
                  "Leave empty to use Rinne's own Discord app. Set your own to show a different name or art "
                  "(create one in the <a href='" + DISCORD_PORTAL + "'>Developer Portal</a>).", app_id)

    def _test_discord(self) -> None:
        self.discord_status.setText(self.win.test_discord())

    # ------------------------------------------------------------------ Library & Data

    def _build_data(self, s: Settings) -> None:
        self._header("Library & Data", "Your MyAnimeList connection, caches and backups.")
        self._group("MyAnimeList")
        user = QLineEdit(s.mal_username)
        user.setMinimumWidth(theme.px(240))
        user.editingFinished.connect(lambda: self._set("mal_username", user.text().strip()))
        self._row("Username", "Used by “Import from MAL username”.", user)
        cid = QLineEdit(s.mal_client_id)
        cid.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        cid.setPlaceholderText("optional")
        cid.setMinimumWidth(theme.px(240))
        cid.editingFinished.connect(lambda: self._set("mal_client_id", cid.text().strip()))
        self._row("API Client ID",
                  "Only needed to import by username (free at myanimelist.net/apiconfig). "
                  "Importing an export file needs nothing.", cid)
        imp = QWidget()
        il = hbox(imp, 8)
        il.addWidget(self._button("Import export file…", self.win.import_file))
        il.addWidget(self._button("Import by username", self.win.import_username))
        il.addWidget(self._button("Refresh all details", lambda: self.win.run_enrich(force=True)))
        self._row("Import", f"{len(self.win.state.library)} shows in your library.", imp)

        self._group("Storage")
        d = data_dir()
        self._row("Data folder", f"<code>{d}</code>", self._button("Open", lambda: self._open(d)))
        img = cache_dir() / "images"
        self._row("Image cache", f"Cover art and backgrounds — {human_size(folder_size(img))}.",
                  self._button("Clear", lambda: self._clear(img, "image cache")))
        meta = [cache_dir() / k for k in ("anilist", "anilist_profile", "anilist_chain", "artwork", "jikan", "mal")]
        self._row("Metadata cache", f"Show details from AniList and others — "
                  f"{human_size(sum(folder_size(m) for m in meta))}. Clearing makes Rinne fetch fresh details.",
                  self._button("Clear", lambda: self._clear(meta, "metadata cache")))

        self._group("Backup")
        bk = QWidget()
        bl = hbox(bk, 8)
        bl.addWidget(self._button("Export backup…", self._export))
        bl.addWidget(self._button("Restore backup…", self._restore))
        self._row("Library backup", "Your library, progress, plan and settings in one file.", bk)
        self._row("Reset settings", "Restore every setting to its default. Your library is kept.",
                  self._button("Reset", self._reset))

    def _open(self, path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _clear(self, paths, what: str) -> None:
        if QMessageBox.question(self, "Clear cache", f"Clear the {what}?") != QMessageBox.Yes:
            return
        for p in paths if isinstance(paths, list) else [paths]:
            shutil.rmtree(p, ignore_errors=True)
        self.refresh()

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export backup", str(Path.home() / "rinne-backup.json"),
                                              "Rinne backup (*.json)")
        if path:
            self.win.save()
            files.write_bytes(path, state_path().read_bytes())
            self.win.statusBar().showMessage("Backup saved", 6000)

    def _restore(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Restore backup", str(Path.home()), "Rinne backup (*.json)")
        if not path:
            return
        if QMessageBox.question(self, "Restore backup",
                                "Replace your current library, plan and settings with this backup?") != QMessageBox.Yes:
            return
        self.win.restore_backup(path)

    def _reset(self) -> None:
        if QMessageBox.question(self, "Reset settings", "Reset all settings to their defaults?") == QMessageBox.Yes:
            self.win.reset_settings()

    # ------------------------------------------------------------------ About

    def _build_about(self, s: Settings) -> None:
        from .. import AUTHOR, COMMUNITY_URL, CONTACT_EMAIL, HOMEPAGE_URL, ISSUES_URL, LICENSE
        from ..changelog import CHANGELOG
        from .feedback import FeedbackDialog, system_info, system_info_text

        frame, lay = card(margins=28, spacing=10)
        top = hbox(spacing=24)
        logo = QLabel()
        pix = QPixmap(asset("logo-round.png"))
        size = theme.px(150)
        dpr = self.devicePixelRatioF() or 1.0
        pix = pix.scaled(round(size * dpr), round(size * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pix.setDevicePixelRatio(dpr)
        logo.setPixmap(pix)
        top.addWidget(logo)
        info = vbox(spacing=6)
        info.addStretch()
        info.addWidget(label(DISPLAY_NAME, "h1"))
        row = hbox(spacing=8)
        row.addWidget(badge(f"v{__version__}"))
        row.addWidget(badge(CHANGELOG[0][1], "badgeGreen"))
        row.addWidget(label(f"by {AUTHOR}", "credit"))
        row.addStretch()
        info.addLayout(row)
        info.addWidget(label("輪廻 — the cycle of rebirth. A weekly anime planner for Linux that follows "
                             "each series: when a show ends, its next season is reborn in its place.",
                             "muted", wrap=True))
        actions = hbox(spacing=8)
        actions.addWidget(self._button("Send feedback", lambda: FeedbackDialog(self.win.state, "bug", self).exec(),
                                       primary=True))
        if HOMEPAGE_URL:
            actions.addWidget(self._button("Project page ↗", lambda: QDesktopServices.openUrl(QUrl(HOMEPAGE_URL))))
        actions.addWidget(self._button("Take the tour", self.win.start_tour))
        actions.addStretch()
        info.addLayout(actions)
        info.addStretch()
        top.addLayout(info, 1)
        lay.addLayout(top)
        self.body.addWidget(frame)

        # --- Feedback & contact
        self._group("Feedback & contact")
        self._row("Report a bug", "Something broken or confusing? Describe it and Rinne adds the details "
                  "needed to fix it.", self._button("Report…", lambda: FeedbackDialog(self.win.state, "bug", self).exec()))
        self._row("Suggest a feature", "Ideas for making Rinne better are always welcome.",
                  self._button("Suggest…", lambda: FeedbackDialog(self.win.state, "idea", self).exec()))
        if ISSUES_URL:
            self._row("Issue tracker", "See known issues and follow what's being worked on.",
                      self._button("Open ↗", lambda: QDesktopServices.openUrl(QUrl(ISSUES_URL))))
        if COMMUNITY_URL:
            self._row("Community", "Chat with other Rinne users and the developer.",
                      self._button("Join ↗", lambda: QDesktopServices.openUrl(QUrl(COMMUNITY_URL))))
        if CONTACT_EMAIL:
            self._row("Contact", f"Reach {AUTHOR} directly at <b>{CONTACT_EMAIL}</b>.",
                      self._button("Email ↗", lambda: QDesktopServices.openUrl(QUrl(f"mailto:{CONTACT_EMAIL}"))))

        # --- Version & system
        self._group("Version & system")
        sysbox, sl = card(margins=16, spacing=6)
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.px(24))
        grid.setColumnStretch(1, 1)
        for n, (k, v) in enumerate(system_info(self.win.state)):
            grid.addWidget(label(k, "small"), n, 0)
            grid.addWidget(label(v, "", wrap=True), n, 1)
        n = grid.rowCount()
        grid.addWidget(label("Data folder", "small"), n, 0)
        grid.addWidget(label(str(data_dir()), "", wrap=True), n, 1)
        if LICENSE:
            grid.addWidget(label("License", "small"), n + 1, 0)
            grid.addWidget(label(LICENSE, ""), n + 1, 1)
        sl.addLayout(grid)
        copy_row = hbox(spacing=8)
        copied = label("", "small")

        def copy_info() -> None:
            from PySide6.QtGui import QGuiApplication
            QGuiApplication.clipboard().setText(system_info_text(self.win.state))
            copied.setText("Copied.")

        copy_row.addWidget(self._button("Copy system info", copy_info))
        copy_row.addWidget(copied)
        copy_row.addStretch()
        sl.addLayout(copy_row)
        self.body.addWidget(sysbox)

        # --- What's new
        self._group("What's new")
        for version, title, notes in CHANGELOG[:3]:
            box, bl = card(margins=16, spacing=6)
            head = hbox(spacing=8)
            head.addWidget(badge(f"v{version}", "badge" if version != __version__ else "badgeGreen"))
            head.addWidget(label(title, "settingTitle"))
            head.addStretch()
            bl.addLayout(head)
            for note in notes:
                bl.addWidget(label(f"•  {note}", "small", wrap=True))
            self.body.addWidget(box)

        # --- Privacy
        self._group("Privacy")
        priv, pl = card(margins=16, spacing=6)
        for line in [
            "Everything — your library, progress and settings — stays on this computer.",
            "No accounts, analytics or tracking. Rinne never sends your list anywhere.",
            "To show details it looks up shows by ID on AniList, and fan art via ani.zip / TheTVDB.",
            "MyAnimeList is contacted only when you import by username.",
            "Discord Rich Presence talks only to the Discord app on your computer, and can be turned off.",
        ]:
            pl.addWidget(label(f"•  {line}", "small", wrap=True))
        self.body.addWidget(priv)

        # --- Data sources
        self._group("Data sources & thanks")
        for name, what, url in [
            ("AniList", "Show details, titles, relations, cast and airing dates", "https://anilist.co"),
            ("MyAnimeList", "Your list (export file or API)", "https://myanimelist.net"),
            ("ani.zip / TheTVDB", "Full-HD fan art for backgrounds and banners", "https://thetvdb.com"),
            ("Jikan", "Fallback details from MyAnimeList", "https://jikan.moe"),
        ]:
            self._row(name, what, self._button("Visit", lambda u=url: QDesktopServices.openUrl(QUrl(u))))

        # --- Shortcuts
        self._group("Keyboard shortcuts")
        keys, kl = card(margins=16, spacing=6)
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.px(24))
        grid.setColumnStretch(1, 1)
        for n, (k, what) in enumerate([
            ("Ctrl 1 / 2 / 3", "Your Week / Up Next / Library"), ("Ctrl ,", "Settings"),
            ("Ctrl R", "Replan from today"), ("Ctrl O", "Import MAL export file"),
            ("Ctrl I", "Import by MAL username"), ("Ctrl + / − / 0", "Zoom in / out / reset"),
            ("Ctrl Q", "Quit"),
        ]):
            grid.addWidget(badge(k, "chipLabel"), n, 0, alignment=Qt.AlignLeft)
            grid.addWidget(label(what, "small"), n, 1)
        kl.addLayout(grid)
        self.body.addWidget(keys)
        foot = label(f"Made with ♥ by {AUTHOR}", "faint")
        foot.setAlignment(Qt.AlignCenter)
        self.body.addWidget(foot)

    # ------------------------------------------------------------------ helpers

    def _set(self, attr: str, value, kind: str = "save") -> None:
        setattr(self.win.state.settings, attr, value)
        if kind == "replan":
            self._replan_timer.start()
        else:
            self.win.settings_changed(kind)

