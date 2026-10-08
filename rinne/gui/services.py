"""Window features that talk to the outside world: update check, new seasons, account sync, imports."""

from __future__ import annotations

import copy
from datetime import date

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from .. import HOMEPAGE_URL, anilist, announcements, mal, models, scheduler, shikimori, sync, updates
from .profile import pick_title
from ..logs import log
from ..models import WATCHING, Anime


class ServicesMixin:
    """Mixed into MainWindow; uses its state, _run, save, refresh and notify."""

    # ------------------------------------------------------------------ updates

    def check_for_updates(self, manual: bool = False, on_result=None) -> None:
        """Ask GitHub for a newer release (daily on startup, or from the About page)."""
        s = self.state.settings

        def done(rel) -> None:
            s.last_update_check = date.today().isoformat()
            self.save()
            manager = updates.managed_by()
            self.update_info = None if manager else rel  # packaged copies update through their manager
            if rel:
                log.info("Update available: %s", rel["version"])
                self.statusBar().showMessage(f"Rinne {rel['version']} is available"
                                             + (f": update it with {manager}" if manager else ""), 10000)
            self._show_update_chip()
            if rel and not manager and s.update_alerted != rel["version"]:
                s.update_alerted = rel["version"]  # one popup and one notification per release
                self.save()
                if s.notify_updates:
                    self.notify(f"Rinne {rel['version']} is available", "Open Rinne to see what's new.")
                if not manual:
                    from .dialogs import UpdateDialog
                    UpdateDialog(rel, self.open_update_page, self).exec()
            if on_result:
                on_result(rel, None)

        def failed(msg: str) -> None:
            log.info("Update check failed: %s", msg)
            if on_result:
                on_result(None, msg)

        self._run(updates.check, (), done, with_progress=False, exclusive=False, on_error=failed)

    def _auto_update_check(self) -> None:
        s = self.state.settings
        if updates.managed_by():
            return  # Flatpak or the distro package manager handles updates
        if s.check_updates and s.last_update_check != date.today().isoformat():
            self.check_for_updates()

    def _show_update_chip(self) -> None:
        info = getattr(self, "update_info", None)
        if hasattr(self, "update_btn"):
            self.update_btn.setVisible(bool(info))
            if info:
                self.update_btn.setText(f"⬆  Update to {info['version']}")
                self.update_btn.setToolTip("Open the download page")

    def open_update_page(self) -> None:
        info = getattr(self, "update_info", None)
        QDesktopServices.openUrl(QUrl(info["url"] if info else HOMEPAGE_URL))

    # ------------------------------------------------------------------ new seasons

    def check_announcements(self) -> None:
        """Daily: announced/airing sequels of your shows that aren't on your list."""
        def done(results: list) -> None:
            self.announcements = results
            s = self.state.settings
            for r in announcements.premiered(results, self.state.announced):
                title = pick_title(r["node"].get("title"), r["node"].get("idMal"))
                if s.auto_add_sequels:
                    self.add_sequel(r["mal_id"], start=False, quiet=True)
                if s.notify_premieres and self.state.announced.get(r["mal_id"]):  # skip first sighting
                    self.notify("New season out now",
                                f"{title} (after {r['after'].name}) has started airing."
                                + (" Added to Plan to Watch." if s.auto_add_sequels else ""))
            self.state.announced = {r["mal_id"]: r["node"]["status"] for r in results}
            self.save()
            if self.stack.currentWidget() is self.next_page:
                self.next_page.refresh()

        self._run(announcements.check, (self.state.library,), done, with_progress=False,
                  exclusive=False, on_error=lambda msg: log.info("Announcement check failed: %s", msg))

    def add_sequel(self, mal_id: int, start: bool = False, quiet: bool = False) -> None:
        """Add an announced/airing sequel to the library (Plan to Watch, or start watching)."""
        if mal_id in self.state.library:
            if start:
                self.start_show(self.state.library[mal_id])
            return

        def done(anime) -> None:
            if anime is None:
                return
            anime.status, anime.added_by_app = "plan_to_watch", True
            self.state.library[anime.mal_id] = anime
            self.announcements = [r for r in getattr(self, "announcements", []) if r["mal_id"] != mal_id]
            if start:
                self.start_show(anime)
            else:
                self.save()
                self.refresh()
            if not quiet:
                self.statusBar().showMessage(f"Added {anime.name} to Plan to Watch", 6000)

        self._run(anilist.lookup, (mal_id,), done, with_progress=False, exclusive=False,
                  on_error=lambda msg: QMessageBox.warning(self, "Couldn't add the season", msg))

    # ------------------------------------------------------------------ account sync

    def _sync_targets(self) -> tuple[dict | None, str | None]:
        s = self.state.settings
        mal_tokens = s.mal_token if (s.mal_token and s.sync_mal) else None
        al_token = s.anilist_token if (s.anilist_token and s.sync_anilist) else None
        return mal_tokens, al_token

    def schedule_sync(self) -> None:
        if not hasattr(self, "_sync_timer"):
            self._sync_timer = QTimer(self, singleShot=True, interval=4000, timeout=self.sync_now)
        if any(self._sync_targets()):
            self._sync_timer.start()

    def sync_now(self, on_result=None) -> None:
        """Push status / episodes / score changes to the connected accounts."""
        mal_tokens, al_token = self._sync_targets()
        if not (mal_tokens or al_token) or getattr(self, "_syncing", False):
            return
        lib, synced = self.state.library, self.state.synced
        changes = {a.mal_id: a for svc in ("mal", "anilist")
                   if (mal_tokens if svc == "mal" else al_token)
                   for a in sync.pending_changes(lib, synced.get(svc, {}))}
        if not changes:
            if on_result:
                on_result("Everything is already in sync.")
            return
        batch = [copy.copy(a) for a in changes.values()]
        self._syncing = True

        def done(res: dict) -> None:
            self._syncing = False
            s = self.state.settings
            for svc in ("mal", "anilist"):
                done_ids = set(res[svc])
                if done_ids:
                    target = self.state.synced.setdefault(svc, {})
                    for a in batch:
                        if a.mal_id in done_ids:
                            target[a.mal_id] = sync.snapshot(a)
            if res["mal_tokens"]:
                s.mal_token = res["mal_tokens"]
            for svc in res["expired"]:
                name = "MyAnimeList" if svc == "mal" else "AniList"
                if svc == "mal":
                    s.mal_token, s.mal_user = {}, ""
                else:
                    s.anilist_token, s.anilist_user = "", ""
                self.notify(f"Reconnect {name}", f"Rinne's sign-in to {name} expired. Connect again in "
                            "Settings → Accounts to keep syncing.")
            for err in res["errors"][:5]:
                log.warning("Sync: %s", err)
            self.save()
            msg = f"Synced {len(batch)} change{'s' if len(batch) != 1 else ''}" + \
                (f" · {len(res['errors'])} failed (see log)" if res["errors"] else "")
            self.statusBar().showMessage(msg, 6000)
            if on_result:
                on_result(msg)
            if self.stack.currentWidget() is self.settings_page:
                self.settings_page.refresh()

        def failed(msg: str) -> None:
            self._syncing = False
            if on_result:
                on_result(f"Sync failed: {msg}")

        self._run(sync.push_all, (batch, self.state.settings.mal_api_client_id(), mal_tokens, al_token),
                  done, with_progress=False, exclusive=False, on_error=failed)

    def connect_mal(self, on_result=None) -> None:
        s = self.state.settings

        def job(client_id):
            tokens = sync.mal_authorize(client_id)
            return tokens, sync.mal_username(tokens)

        def done(result) -> None:
            tokens, name = result
            s.mal_token, s.mal_user, s.sync_mal = tokens, name, True
            self.state.synced["mal"] = sync.baseline(self.state.library)
            self.save()
            self.statusBar().showMessage(f"Connected to MyAnimeList as {name}", 6000)
            if on_result:
                on_result(None)
            self.pull_account("mal")

        def failed(msg: str) -> None:
            if on_result:
                on_result(msg)

        self.statusBar().showMessage("Waiting for you to approve Rinne on MyAnimeList (in your browser)…")
        self._run(job, (s.mal_api_client_id(),), done, with_progress=False, exclusive=False, on_error=failed)

    def connect_anilist(self, on_result=None) -> None:
        s = self.state.settings
        try:
            sync.anilist_open_signin()
        except sync.SyncError as e:
            QMessageBox.information(self, "AniList", str(e))
            return
        token, ok = QInputDialog.getText(
            self, "Connect AniList", "Approve Rinne in your browser, then paste the code AniList shows here:")
        if not ok or not token.strip():
            return
        token = token.strip()

        def done(name: str) -> None:
            s.anilist_token, s.anilist_user, s.sync_anilist = token, name, True
            if not s.anilist_username:
                s.anilist_username = name
            self.state.synced["anilist"] = sync.baseline(self.state.library)
            self.save()
            self.statusBar().showMessage(f"Connected to AniList as {name}", 6000)
            if on_result:
                on_result(None)
            self.pull_account("anilist")

        self._run(sync.anilist_viewer, (token,), done, with_progress=False, exclusive=False,
                  on_error=lambda msg: (on_result or (lambda m: QMessageBox.warning(self, "AniList", m)))(msg))

    def pull_account(self, service: str) -> None:
        """Bring in the list of a connected account (private entries too)."""
        s = self.state.settings

        def job(progress=None):
            if service == "mal":
                tokens = sync.mal_valid_token(s.mal_api_client_id(), s.mal_token)
                return tokens, mal.fetch_mal_list("@me", s.mal_api_client_id(), progress,
                                                  token=tokens["access_token"])
            return None, anilist.fetch_user_list(s.anilist_user, progress, token=s.anilist_token)[0]

        def done(result) -> None:
            tokens, entries = result
            if tokens:
                s.mal_token = tokens
            self._finish_import(entries)
            # What the account holds now is the starting point for sync, so the import itself
            # isn't sent back.
            self.state.synced[service] = sync.baseline(self.state.library)
            self.save()
            self.refresh()

        self._run(job, (), done)

    def disconnect_account(self, service: str) -> None:
        s = self.state.settings
        if service == "mal":
            s.mal_token, s.mal_user = {}, ""
        else:
            s.anilist_token, s.anilist_user = "", ""
        self.state.synced.pop(service, None)
        self.save()

    # ------------------------------------------------------------------ import

    def import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open MAL export", "", "MAL export (*.xml *.xml.gz *.gz);;All files (*)")
        if not path:
            return
        try:
            entries = mal.parse_mal_export(path)
        except (mal.ImportError_, OSError) as e:
            QMessageBox.warning(self, "Import failed", str(e))
            return
        self._finish_import(entries)

    def import_anilist(self, username: str | None = None) -> None:
        """Import a public AniList list by username (no account or key needed)."""
        s = self.state.settings
        if username is None:
            name, ok = QInputDialog.getText(self, "Import from AniList", "AniList username:",
                                            text=s.anilist_username)
            if not ok or not name.strip():
                return
            username = name
        s.anilist_username = username.strip()
        self.save()

        def done(result) -> None:
            entries, skipped = result
            self._finish_import(entries)
            if skipped:
                self.statusBar().showMessage(
                    f"Imported {len(entries)} shows from AniList · {skipped} without a MyAnimeList "
                    "entry couldn't be added", 10000)

        self._run(anilist.fetch_user_list, (s.anilist_username,), done)

    def import_username(self) -> None:
        s = self.state.settings
        if not s.mal_api_client_id():
            QMessageBox.information(
                self, "Client ID needed",
                "Importing by username uses the official MAL API, which needs a free Client ID "
                "(myanimelist.net/apiconfig → Create ID, app type “other”).<br><br>"
                "Paste it in Settings, or use <b>From MAL export file</b> instead.")
            self.open_settings("data")
            return
        name, ok = QInputDialog.getText(self, "Import from MAL", "MAL username:", text=s.mal_username)
        if not ok or not name.strip():
            return
        s.mal_username = name.strip()
        self._run(mal.fetch_mal_list, (s.mal_username, s.mal_api_client_id()), self._finish_import)

    def _finish_import(self, entries: list[Anime]) -> None:
        added, updated = mal.merge_import(self.state.library, entries)
        self.save()
        self.statusBar().showMessage(f"Imported: {added} new, {updated} updated", 8000)
        self.run_enrich()
        if models.title_language == models.RUSSIAN:
            self.fetch_russian_titles()

    def import_shikimori(self, username: str | None = None) -> None:
        """Import a public Shikimori list by nickname. Russian titles come with it."""
        s = self.state.settings
        if username is None:
            name, ok = QInputDialog.getText(self, "Import from Shikimori", "Shikimori nickname:",
                                            text=s.shikimori_username)
            if not ok or not name.strip():
                return
            username = name
        s.shikimori_username = username.strip()
        self.save()

        def done(entries) -> None:
            self._finish_import(entries)
            if s.title_language != models.RUSSIAN and QMessageBox.question(
                    self, "Russian titles", "Show titles in Russian? You can change this any time in "
                    "Settings → General → Titles.") == QMessageBox.Yes:
                self.set_title_language(models.RUSSIAN)

        self._run(shikimori.fetch_user_list, (s.shikimori_username,), done)

    def fetch_russian_titles(self) -> None:
        """Russian titles (from Shikimori) for every show that doesn't have one yet."""
        missing = [a.mal_id for a in self.state.library.values() if not a.title_ru]
        if not missing:
            return

        def done(titles) -> None:
            changed = shikimori.apply_russian(self.state.library, titles)
            if changed:
                self.save()
                self.refresh()
                self.statusBar().showMessage(f"Russian titles added for {changed} show{'s' if changed != 1 else ''}",
                                             5000)
            elif self.statusBar().currentMessage().startswith("Fetching Russian titles"):
                self.statusBar().clearMessage()

        self._run(shikimori.russian_titles, (missing,), done, exclusive=False)

    def _startup_enrich(self) -> None:
        # Episode titles/thumbnails for the shows being watched (airing ones refresh every 2 days).
        self.fetch_artwork(scheduler.current_rotation(self.state.library), refresh=True)
        # Retry anything a previous session couldn't look up (and backfill new fields).
        if any(a.needs_enrichment for a in self.state.library.values()):
            self.run_enrich()
        if models.title_language == models.RUSSIAN:
            self.fetch_russian_titles()  # cached, so only new shows are looked up
        if self.state.settings.refresh_on_startup:
            airing = [a for a in self.state.library.values()
                      if a.status == WATCHING and a.airing_status == "currently_airing"]
            if airing:
                cid = self.state.settings.mal_api_client_id()

                def job(entries, progress, should_stop):
                    return mal.enrich(entries, cid, progress, should_stop, force=True)

                self._run(job, (airing,), self._enriched, cancellable=True)

    def run_enrich(self, force: bool = False) -> None:
        wanted = list(self.state.library.values())
        if not force and not any(a.needs_enrichment for a in wanted):
            self.replan()
            return

        def job(entries, cid, progress, should_stop):
            return mal.enrich(entries, cid, progress, should_stop, force=force)

        self._run(job, (wanted, self.state.settings.mal_api_client_id()), self._enriched,
                  cancellable=True)

    def _enriched(self, count: int) -> None:
        self.statusBar().showMessage(f"Updated details for {count} shows", 8000)
        self.replan()
