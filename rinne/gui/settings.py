"""The Settings page. Changes apply immediately (no Save button)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QTime, Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFrame, QGridLayout, QLabel, QLineEdit, QPushButton, QRadioButton, QSlider,
    QSpinBox, QTimeEdit, QWidget,
)

from .. import i18n
from ..i18n import _, N_
from ..models import EPISODES, MINUTES, TITLE_LANGUAGES, WEEKDAYS, Settings
from . import theme
from .common import Clickable, FlowLayout, Switch, badge, button_row, clear, hbox, label, set_margins, vbox
from .common import scroll_page
from .settings_about import AboutSection
from .settings_data import DataSections

if TYPE_CHECKING:
    from .window import MainWindow

SECTIONS = [  # N_ marks them for translation; they're translated when shown
    ("general", N_("General")),
    ("appearance", N_("Appearance")),
    ("schedule", N_("Schedule")),
    ("notifications", N_("Notifications")),
    ("discord", N_("Discord")),
    ("accounts", N_("Accounts")),
    ("data", N_("Library && Data")),  # && = a literal & in button text
    ("about", N_("About")),
]
START_PAGES = [("week", N_("Your Week")), ("next", N_("Up Next")), ("library", N_("Library"))]
DISCORD_PORTAL = "https://discord.com/developers/applications"


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


class SettingsPage(DataSections, AboutSection, QWidget):
    def __init__(self, win: MainWindow):
        super().__init__()
        self.win = win
        self.section = "general"
        root = hbox(self, 0)

        side = self.side = QFrame()
        side.setObjectName("page")
        side_lay = vbox(side, 4, 24)
        side_lay.addWidget(label(_("Settings"), "h1"))
        side_lay.addSpacing(theme.px(10))
        self.nav = QButtonGroup(self)
        for n, (key, text) in enumerate(SECTIONS):
            b = QPushButton(_(text))
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
        return list(SECTIONS)

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
        area.setProperty("sideways", True)
        area.setFixedHeight(host.sizeHint().height() + theme.px(2))
        return area

    # ------------------------------------------------------------------ building blocks

    def _header(self, title: str, subtitle: str = "") -> None:
        self.body.addWidget(label(_(title), "h1"))
        if subtitle:
            self.body.addWidget(label(_(subtitle), "muted", wrap=True))
        self.body.addSpacing(theme.px(4))

    def _group(self, title: str) -> None:
        self.body.addSpacing(theme.px(8))
        self.body.addWidget(label(_(title).upper(), "sideSection"))

    def _row(self, title: str, description: str, control: QWidget | None = None,
             stretch_control: bool = False) -> QFrame:
        frame = QFrame()
        frame.setObjectName("settingRow")
        # Phones: text above the control, except compact on/off switches which stay inline.
        stacked = theme.COMPACT and control is not None and not isinstance(control, Switch)
        row = (vbox if stacked else hbox)(frame, 10 if stacked else 16, 14)
        text = vbox(spacing=3)
        text.addWidget(label(_(title), "settingTitle", wrap=True))
        if description:
            desc = label(_(description), "small", wrap=True, rich=True)
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
        b = QPushButton(_(text))
        b.setObjectName("primary" if primary else "ghost")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(fn)
        return b

    # ------------------------------------------------------------------ General

    def _build_general(self, s: Settings) -> None:
        self._header("General", "How Rinne starts and behaves on your desktop.")
        self._group("Startup")
        start = self._combo([(k, _(t)) for k, t in START_PAGES], s.start_page)
        start.currentIndexChanged.connect(lambda _: self._set("start_page", start.currentData()))
        self._row("Open on", "The page Rinne shows when it starts.", start)
        tray = self.win.tray_available()
        self._switch("Start minimized to the tray", "Launch quietly in the system tray." +
                     ("" if tray else " <i>(No system tray detected.)</i>"), "start_minimized", enabled=tray)
        self._switch("Check for updates", "Once a day, look for a newer Rinne release on GitHub.",
                     "check_updates")
        self._switch("Check airing shows on startup",
                     "Refresh episode counts and next-episode dates for shows you're watching that "
                     "are still airing.", "refresh_on_startup")

        self._group("Window")
        self._switch("Keep running in the tray when closed",
                     "Closing the window hides Rinne to the tray so notifications keep working. "
                     "Quit from the tray menu." + ("" if tray else " <i>(No system tray detected.)</i>"),
                     "close_to_tray", kind="tray", enabled=tray)

        self._group("Getting started")
        again = button_row(self._button("Show the welcome screen", self.win.show_welcome),
                           self._button("Take the tour", self.win.start_tour))
        self._row("Welcome & tour", "Run the first-launch setup or the guided tour again.", again)

        self._group("Titles")
        lang = self._combo(list(TITLE_LANGUAGES.items()), s.title_language)
        lang.currentIndexChanged.connect(lambda _: self.win.set_title_language(lang.currentData()))
        self._row("Show titles in", "Romaji, English or Japanese. Searching matches all three.", lang)

        self._group("Language")
        langs = [("auto", "System default")] + [(k, v) for k, v in i18n.available().items()]
        ui_lang = self._combo(langs, s.language)
        ui_lang.currentIndexChanged.connect(lambda _i: self._set("language", ui_lang.currentData()))
        self._row("Interface language", "Takes effect the next time Rinne starts. Only English is "
                  "included so far: <a href=\"https://github.com/ZodchiSama/RINNE/blob/main/CONTRIBUTING.md"
                  "#translating-rinne\">help translate Rinne</a>.", ui_lang)

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
        if theme.COMPACT:
            slider.setMinimumWidth(theme.px(120))
        else:
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
        ml = (vbox if theme.COMPACT else hbox)(mode_w, 8 if theme.COMPACT else 18)
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
            if theme.COMPACT:
                sp.setMinimumWidth(theme.px(48))
            sp.valueChanged.connect(lambda v, i=i: (s.set_day_amount(i, v), self._replan_timer.start()))
            grid.addWidget(sp, r + 1, c)
            spins.append(sp)
        self._row("Each day", "Set a day to 0 for a day off.", days_w, stretch_control=True)

        preset_buttons = []
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
            preset_buttons.append(b)
        self._row("Quick set", "", button_row(*preset_buttons, spacing=6), stretch_control=True)

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
        self._switch("Catch up on airing shows",
                     "When you're two or more episodes behind on an airing show, it goes first each day "
                     "and gets an extra episode until you're caught up.", "catch_up_airing", kind="replan")

        self._group("New seasons")
        self._switch("Tell me when a new season premieres",
                     "When a sequel of a show you've watched starts airing, you get a notification and it "
                     "appears under Up Next.", "notify_premieres")
        self._switch("Add new seasons to Plan to Watch automatically",
                     "Premiered sequels are added for you (they still only join your plan when a show "
                     "finishes or you start them).", "auto_add_sequels")

        self._group("Calendar")
        cal_buttons = button_row(self._button("Export calendar file…", self._export_calendar))
        self._row("Export your plan", "An .ics file with one all-day event per show per day, for Google "
                  "Calendar, Thunderbird, GNOME Calendar and others.", cal_buttons)
        from ..calendar_export import calendar_path
        self._switch("Keep a calendar file up to date",
                     f"Rinne rewrites <code>{str(calendar_path()).replace('/', '/&#8203;')}</code> whenever "
                     "the plan changes. Subscribe to it in your calendar app to always see this week's plan.",
                     "calendar_file", kind="calendar")
        self.body.addWidget(self._button("Replan from today", self.win.replan_fresh, primary=True),
                            alignment=Qt.AlignLeft)

    # ------------------------------------------------------------------ Notifications

    def _build_notifications(self, s: Settings) -> None:
        self._header("Notifications", "Desktop notifications about your shows.")
        self._switch("New episode aired",
                     "When a new episode of a show on your Watching list comes out.", "notify_new_episodes")
        self._switch("Daily reminder", "A summary of today's plan at a time you choose.", "daily_reminder")
        self._switch("Weekly recap", "Saturday evening: how many episodes you watched, what you finished and "
                     "your streak.", "weekly_recap")
        self._switch("Weekly goals", "When a new week starts (with how last week went), and on Saturday "
                     "evening if days are still unfinished before the week restarts.", "notify_goals")
        self._switch("Updates", "When a new version of Rinne is out.", "notify_updates")
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

    # ------------------------------------------------------------------ Accounts

    def _set(self, attr: str, value, kind: str = "save") -> None:
        setattr(self.win.state.settings, attr, value)
        if kind == "replan":
            self._replan_timer.start()
        else:
            self.win.settings_changed(kind)

