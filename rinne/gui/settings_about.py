"""Settings section: About (version, feedback, updates, credits, shortcuts)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QGridLayout, QLabel

from .. import DISPLAY_NAME, __version__, updates
from ..models import Settings
from ..logs import log_path
from ..storage import data_dir
from . import theme
from .common import asset, badge, button_row, card, hbox, label, vbox
from ..i18n import _

if TYPE_CHECKING:
    from .window import MainWindow



class AboutSection:
    """Mixed into SettingsPage, which provides _header, _group, _row, _switch, _button, _set."""

    win: MainWindow

    def _build_about(self, s: Settings) -> None:
        from .. import AUTHOR, COMMUNITY_URL, CONTACT_EMAIL, HOMEPAGE_URL, ISSUES_URL, LICENSE
        from ..changelog import CHANGELOG
        from .feedback import FeedbackDialog, system_info, system_info_text

        frame, lay = card(margins=18 if theme.COMPACT else 28, spacing=10)
        top = (vbox if theme.COMPACT else hbox)(spacing=16 if theme.COMPACT else 24)
        logo = QLabel()
        pix = QPixmap(asset("logo-round.png"))
        size = theme.px(110 if theme.COMPACT else 150)
        dpr = self.devicePixelRatioF() or 1.0
        pix = pix.scaled(round(size * dpr), round(size * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pix.setDevicePixelRatio(dpr)
        logo.setPixmap(pix)
        top.addWidget(logo)
        info = vbox(spacing=6)
        info.addStretch()
        info.addWidget(label(DISPLAY_NAME, "h1"))
        row = hbox(spacing=8)
        row.addWidget(badge(_("v{version}").format(version=__version__)))
        row.addWidget(badge(CHANGELOG[0][1], "badgeGreen"))
        row.addWidget(label(_("by {AUTHOR}").format(AUTHOR=AUTHOR), "credit"))
        row.addStretch()
        info.addLayout(row)
        info.addWidget(label(_("輪廻 — the cycle of rebirth. A weekly anime planner for Linux that follows "
                             "each series: when a show ends, its next season is reborn in its place."),
                             "muted", wrap=True))
        about_buttons = [self._button("Send feedback",
                                      lambda: FeedbackDialog(self.win.state, "bug", self).exec(), primary=True)]
        if HOMEPAGE_URL:
            about_buttons.append(self._button("Project page ↗",
                                              lambda: QDesktopServices.openUrl(QUrl(HOMEPAGE_URL))))
        about_buttons.append(self._button("Take the tour", self.win.start_tour))
        info.addWidget(button_row(*about_buttons))
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
        grid.setHorizontalSpacing(theme.px(12 if theme.COMPACT else 24))
        grid.setColumnStretch(1, 1)
        for n, (k, v) in enumerate(system_info(self.win.state)):
            grid.addWidget(label(k, "small"), n, 0)
            grid.addWidget(label(v, "", wrap=True), n, 1)
        n = grid.rowCount()
        grid.addWidget(label(_("Data folder"), "small"), n, 0)
        # A zero-width space after each "/" and "-" lets a long path wrap on narrow screens.
        grid.addWidget(label(str(data_dir()).replace("/", "/\u200b").replace("-", "-\u200b"), "", wrap=True), n, 1)
        if LICENSE:
            grid.addWidget(label(_("License"), "small"), n + 1, 0)
            grid.addWidget(label(LICENSE, ""), n + 1, 1)
        sl.addLayout(grid)
        copy_row = hbox(spacing=8)
        copied = label("", "small")

        def copy_info() -> None:
            from PySide6.QtGui import QGuiApplication
            QGuiApplication.clipboard().setText(system_info_text(self.win.state))
            copied.setText(_("Copied."))

        copy_row.addWidget(self._button("Copy system info", copy_info))
        update_status = label("", "small", wrap=True)

        def check_now() -> None:
            update_status.setText(_("Checking…"))

            def result(rel, error) -> None:
                if error:
                    update_status.setText(_("Couldn't check: {error}").format(error=error))
                elif rel and updates.managed_by():
                    update_status.setText(_("Rinne {version} is available: update it with {value}.").format(version=rel['version'], value=updates.managed_by()))
                elif rel:
                    update_status.setText(_("Rinne {version} is available — use the button in the sidebar.").format(version=rel['version']))
                else:
                    update_status.setText(_("You're up to date (v{version}).").format(version=__version__))

            self.win.check_for_updates(manual=True, on_result=result)

        copy_row.addWidget(self._button("Check for updates", check_now))
        copy_row.addWidget(self._button("Open log", lambda: self._open(log_path())))
        sl.addWidget(update_status)
        copy_row.addWidget(copied)
        copy_row.addStretch()
        sl.addLayout(copy_row)
        self.body.addWidget(sysbox)

        # --- What's new
        self._group("What's new")
        from .dialogs import WhatsNewDialog
        self.body.addWidget(self._button("Show this version's notes", lambda: WhatsNewDialog(self.win).exec()),
                            alignment=Qt.AlignLeft)
        for version, title, notes in CHANGELOG[:3]:
            box, bl = card(margins=16, spacing=6)
            head = hbox(spacing=8)
            head.addWidget(badge(_("v{version}").format(version=version), "badge" if version != __version__ else "badgeGreen"))
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
            ("Ctrl 1 / 2 / 3 / 4", "Your Week / Up Next / Library / Stats"), ("Ctrl ,", "Settings"),
            ("Ctrl R", "Replan from today"), ("Ctrl O", "Import MAL export file"),
            ("Ctrl I", "Import by MAL username"), ("Ctrl + / − / 0", "Zoom in / out / reset"),
            ("Ctrl Q", "Quit"),
        ]):
            grid.addWidget(badge(k, "chipLabel"), n, 0, alignment=Qt.AlignLeft)
            grid.addWidget(label(what, "small"), n, 1)
        kl.addLayout(grid)
        self.body.addWidget(keys)
        foot = label(_("Made with ♥ by {AUTHOR}").format(AUTHOR=AUTHOR), "faint")
        foot.setAlignment(Qt.AlignCenter)
        self.body.addWidget(foot)

    # ------------------------------------------------------------------ helpers
