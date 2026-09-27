"""Desktop integration for the main window: tray icon, notifications, Discord Rich Presence."""

from __future__ import annotations

import shutil
import time
from datetime import date, datetime, timedelta

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .. import DISPLAY_NAME, scheduler
from ..discord_rpc import DiscordRPC, build_activity
from ..models import CURRENTLY_AIRING, WATCHING
from ..platform import is_android


def app_icon() -> QIcon:
    from .settings import asset
    icon = QIcon()
    for n in (16, 24, 32, 48, 64, 128, 256, 512):
        icon.addFile(asset(f"icon-{n}.png"))
    return icon


class DesktopMixin:
    """Mixed into MainWindow; relies on self.state, self.save(), self.statusBar()."""

    def _init_desktop(self) -> None:
        self._quitting = False
        self._tray: QSystemTrayIcon | None = None
        self._tray_next: QAction | None = None
        self._rpc: DiscordRPC | None = None
        self._rpc_last: dict | None = None
        self._rpc_sent_at = 0.0
        self._started_at = time.time()
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = QSystemTrayIcon(app_icon(), self)
            self._tray.setToolTip(DISPLAY_NAME)
            menu = QMenu()
            menu.addAction(f"Open {DISPLAY_NAME}", self.show_window)
            self._tray_next = menu.addAction("Nothing planned today")
            self._tray_next.setEnabled(False)
            menu.addSeparator()
            menu.addAction("Quit", self.quit_app)
            self._tray.setContextMenu(menu)
            self._tray.activated.connect(self._tray_activated)
            self._tray_menu = menu
        self.update_tray()
        # Coalesce bursts of changes (e.g. ticking several episodes) into one Discord update.
        self._presence_timer = QTimer(self, singleShot=True, interval=2000, timeout=self.update_presence)
        self._desk_timer = QTimer(self, interval=60 * 1000, timeout=self._desktop_tick)
        self._desk_timer.start()
        QTimer.singleShot(2000, self._desktop_tick)

    # ------------------------------------------------------------------ tray / window

    def tray_available(self) -> bool:
        return self._tray is not None

    def close_keeps_running(self) -> bool:
        return self._tray is not None and self.state.settings.close_to_tray

    def update_tray(self) -> None:
        if self._tray is None:
            return
        s = self.state.settings
        self._tray.setVisible(s.close_to_tray or s.start_minimized)
        nxt = self.next_up()
        if self._tray_next is not None:
            self._tray_next.setText(f"Up next: {nxt[0].name} — ep {nxt[1]}" if nxt else "All caught up today")

    def should_start_hidden(self) -> bool:
        return self._tray is not None and self.state.settings.start_minimized

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self.show_window()

    def quit_app(self) -> None:
        self._quitting = True
        self.close()
        QApplication.instance().quit()

    # ------------------------------------------------------------------ notifications

    def notify(self, title: str, body: str) -> None:
        from .settings import asset
        if shutil.which("notify-send"):
            QProcess.startDetached("notify-send", ["-a", DISPLAY_NAME, "-i", asset("icon-256.png"), title, body])
        elif self._tray is not None:
            self._tray.show()
            self._tray.showMessage(title, body, app_icon(), 8000)
        else:
            self.statusBar().showMessage(f"{title} — {body}", 10000)

    def test_notification(self) -> None:
        nxt = self.next_up()
        self.notify(DISPLAY_NAME, f"Notifications work! Up next: {nxt[0].name}, episode {nxt[1]}."
                    if nxt else "Notifications work!")

    def next_up(self):
        """(anime, episode) of today's first unwatched planned episode, or None."""
        week, start = self.state.week, scheduler.plan_start(self.state)
        if not week or not start:
            return None
        offset = (date.today() - start).days
        for it in week.items:
            if it.day == offset and not it.done and it.mal_id in self.state.library:
                return self.state.library[it.mal_id], it.episode
        return None

    def _today_items(self):
        week, start = self.state.week, scheduler.plan_start(self.state)
        if not week or not start:
            return []
        offset = (date.today() - start).days
        return [i for i in week.items if i.day == offset]

    def _desktop_tick(self) -> None:
        s = self.state.settings
        now = datetime.now()
        changed = False
        if s.notify_new_episodes:
            for a in self.state.library.values():
                if a.status != WATCHING or a.airing_status != CURRENTLY_AIRING or not a.next_airing:
                    continue
                try:
                    aired_at = datetime.fromisoformat(a.next_airing)
                except ValueError:
                    continue
                # Only announce recent releases, so a first run doesn't flood you.
                if aired_at <= now <= aired_at + timedelta(hours=12) and \
                        self.state.notified.get(a.mal_id, 0) < a.next_episode:
                    self.state.notified[a.mal_id] = a.next_episode
                    self.notify(f"New episode: {a.name}", f"Episode {a.next_episode} is out.")
                    changed = True
        if s.daily_reminder and self.state.last_reminder != date.today().isoformat():
            hh, mm = (int(x) for x in (s.reminder_time or "19:00").split(":"))
            if (now.hour, now.minute) >= (hh, mm):
                items = self._today_items()
                todo = [i for i in items if not i.done]
                if todo:
                    names = []
                    for i in todo:
                        a = self.state.library.get(i.mal_id)
                        if a and a.name not in names:
                            names.append(a.name)
                    self.notify("Today's plan", f"{len(todo)} episode{'s' if len(todo) != 1 else ''} to go: "
                                + ", ".join(names[:4]) + ("…" if len(names) > 4 else ""))
                self.state.last_reminder = date.today().isoformat()
                changed = True
        if changed:
            self.save()
        self.update_tray()
        self.update_presence()

    # ------------------------------------------------------------------ Discord

    def _presence_activity(self) -> dict:
        s = self.state.settings
        items = self._today_items()
        done = sum(i.done for i in items)
        nxt = self.next_up()
        progress = f"{done} of {len(items)} episodes watched today" if items else "No episodes planned today"
        if s.discord_private:
            return build_activity(None, "Planning the week" if items else "Taking a day off", progress,
                                  buttons=False, started=self._started_at)
        if nxt:
            anime, ep = nxt
            total = f" of {anime.episodes_total}" if anime.episodes_total else ""
            return build_activity(anime.name, anime.name, f"Up next: episode {ep}{total} · {progress}",
                                  anime.image_url if s.discord_show_cover else "", anime.mal_id,
                                  s.discord_buttons, self._started_at)
        return build_activity(None, "All caught up today ✓" if items else "Planning the week",
                              f"{len(self.state.week.items) if self.state.week else 0} episodes in this week's plan",
                              buttons=False, started=self._started_at)

    def schedule_presence(self) -> None:
        if getattr(self, "_presence_timer", None) is not None and self.state.settings.discord_enabled:
            self._presence_timer.start()

    def update_presence(self, force: bool = False) -> None:
        s = self.state.settings
        client_id = s.discord_client_id()
        if not s.discord_enabled or is_android():  # no desktop Discord to talk to on Android
            if self._rpc is not None:
                self._rpc.close()
                self._rpc = None
                self._rpc_last = None
            return
        if self._rpc is None or self._rpc.client_id != client_id:
            if self._rpc is not None:
                self._rpc.close()
            self._rpc = DiscordRPC(client_id)
            self._rpc_last = None
        activity = self._presence_activity()
        # Discord rate-limits updates; only resend on change (or every 15 min as a keep-alive).
        if not force and activity == self._rpc_last and time.time() - self._rpc_sent_at < 900:
            return
        if self._rpc.set_activity(activity):
            self._rpc_last, self._rpc_sent_at = activity, time.time()

    def discord_status(self) -> str:
        s = self.state.settings
        if not s.discord_enabled:
            return "Rich Presence is off."
        if self._rpc is not None and self._rpc.connected:
            return "Connected — your status is showing on Discord."
        return self._rpc.last_error if self._rpc and self._rpc.last_error else "Not connected yet."

    def test_discord(self) -> str:
        enabled = self.state.settings.discord_enabled
        self.state.settings.discord_enabled = True
        self.update_presence(force=True)
        self.state.settings.discord_enabled = enabled
        ok = self._rpc is not None and self._rpc.connected
        if not enabled:
            self.update_presence()  # turn it back off
        return ("Connected! Check your Discord profile." + ("" if enabled else " (Enable it to keep it on.)")
                if ok else f"Couldn't connect: {self._rpc.last_error if self._rpc else 'unknown error'}")

    def shutdown_desktop(self) -> None:
        if self._rpc is not None:
            self._rpc.close()
        if self._tray is not None:
            self._tray.hide()
