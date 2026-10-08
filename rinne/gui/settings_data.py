"""Settings sections: Accounts and Library & Data."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QLineEdit, QMessageBox

from ..i18n import _, _n
from ..models import Settings
from ..storage import cache_dir, data_dir, state_path
from . import theme
from .common import folder_size, human_size, button_row, label

if TYPE_CHECKING:
    from .window import MainWindow



class DataSections:
    """Mixed into SettingsPage, which provides _header, _group, _row, _switch, _button, _set."""

    win: MainWindow

    def _build_accounts(self, s: Settings) -> None:
        from .. import ANILIST_CLIENT_ID
        self._header("Accounts", "Connect MyAnimeList or AniList and Rinne keeps your list up to date: "
                     "episodes you tick, status changes and scores are sent a few seconds later.")
        status_label = label("", "small", wrap=True)

        def result(msg) -> None:
            status_label.setText(msg or "")
            QTimer.singleShot(100, self.refresh)

        for svc, name, user, connected, available, sync_attr in [
            ("mal", "MyAnimeList", s.mal_user, bool(s.mal_token), bool(s.mal_api_client_id()), "sync_mal"),
            ("anilist", "AniList", s.anilist_user, bool(s.anilist_token), bool(ANILIST_CLIENT_ID), "sync_anilist"),
        ]:
            self._group(name)
            if connected:
                disc = self._button("Disconnect", lambda _=False, v=svc: (self.win.disconnect_account(v), self.refresh()))
                self._row(_("Connected as {value}").format(value=user or _('your account')),
                          "Only status, episodes watched and score are sent — for shows that change.", disc)
                self._switch(_("Send my progress to {name}").format(name=name), "", sync_attr, kind="save")
            elif available:
                go = self._button(_("Connect {name}").format(name=name), (lambda: self.win.connect_mal(result)) if svc == "mal"
                                  else (lambda: self.win.connect_anilist(result)), primary=True)
                how = (_("Opens MyAnimeList in your browser; approve Rinne and you're done.")
                       if svc == "mal" else
                       _("Opens AniList in your browser; approve Rinne, then paste the code it shows."))
                self._row("Not connected", how, go)
            else:
                self._row("Not available in this build", _("{name} sign-in hasn't been set up yet.").format(name=name), None)
        if s.mal_token or s.anilist_token:
            self._group("Sync")
            self._row("Sync now", "Send any changes immediately instead of waiting a few seconds.",
                      self._button("Sync now", lambda: (status_label.setText(_("Syncing…")),
                                                        self.win.sync_now(result))))
        self.body.addWidget(status_label)
        self.body.addWidget(label(_("Sign-ins are stored only on this computer, in Rinne's data folder. Backups "
                                  "you export include them — keep backup files private."), "faint", wrap=True))

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
        cid.setPlaceholderText(_("optional"))
        cid.setMinimumWidth(theme.px(240))
        cid.editingFinished.connect(lambda: self._set("mal_client_id", cid.text().strip()))
        self._row("API Client ID",
                  "Optional. Rinne has its own; set yours (myanimelist.net/apiconfig) only if you "
                  "want MyAnimeList requests to use it.", cid)
        imp = button_row(self._button("Import export file…", lambda: self.win.import_manually("file")),
                         self._button("Import by username", lambda: self.win.import_manually("mal")),
                         self._button("Import from AniList…", lambda: self.win.import_manually("anilist")),
                         self._button("Import from Shikimori…", lambda: self.win.import_manually("shikimori")),
                         self._button("Refresh all details", lambda: self.win.run_enrich(force=True)))
        self._row("Import", _n("{n} show in your library.", "{n} shows in your library.", len(self.win.state.library)), imp)

        self._group("Storage")
        d = data_dir()
        self._row("Data folder", f"<code>{d}</code>", self._button("Open", lambda: self._open(d)))
        img = cache_dir() / "images"
        self._row("Image cache", _("Cover art and backgrounds — {value}.").format(value=human_size(folder_size(img))),
                  self._button("Clear", lambda: self._clear(img, "image cache")))
        meta = [cache_dir() / k for k in ("anilist", "anilist_profile", "anilist_chain", "artwork", "jikan", "mal")]
        self._row("Metadata cache", _("Show details from AniList and others — {value}. Clearing makes Rinne fetch fresh details.").format(value=human_size(sum(folder_size(m) for m in meta))),
                  self._button("Clear", lambda: self._clear(meta, "metadata cache")))

        self._group("Backup")
        bk = button_row(self._button("Export backup…", self._export),
                        self._button("Restore backup…", self._restore))
        self._row("Library backup", "Your library, progress, plan and settings in one file.", bk)
        self._row("Reset settings", "Restore every setting to its default. Your library is kept.",
                  self._button("Reset", self._reset))

    def _export_calendar(self) -> None:
        from ..calendar_export import write
        path, _filter = QFileDialog.getSaveFileName(self, _("Export calendar"), str(Path.home() / "rinne-plan.ics"),
                                              "iCalendar file (*.ics)")
        if path:
            write(self.win.state, Path(path))
            self.win.statusBar().showMessage(_("Calendar saved to {path}").format(path=path), 6000)

    def _open(self, path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _clear(self, paths, what: str) -> None:
        if QMessageBox.question(self, _("Clear cache"), _("Clear the {what}?").format(what=what)) != QMessageBox.Yes:
            return
        for p in paths if isinstance(paths, list) else [paths]:
            shutil.rmtree(p, ignore_errors=True)
        self.refresh()

    def _export(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(self, _("Export backup"), str(Path.home() / "rinne-backup.json"),
                                              "Rinne backup (*.json)")
        if path:
            self.win.save()
            shutil.copyfile(state_path(), path)
            self.win.statusBar().showMessage(_("Backup saved"), 6000)

    def _restore(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, _("Restore backup"), str(Path.home()), "Rinne backup (*.json)")
        if not path:
            return
        if QMessageBox.question(self, _("Restore backup"),
                                _("Replace your current library, plan and settings with this backup?")) != QMessageBox.Yes:
            return
        self.win.restore_backup(path)

    def _reset(self) -> None:
        if QMessageBox.question(self, _("Reset settings"), _("Reset all settings to their defaults?")) == QMessageBox.Yes:
            self.win.reset_settings()

    # ------------------------------------------------------------------ About
