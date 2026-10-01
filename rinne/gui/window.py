"""Main window: sidebar navigation, background tasks, zoom, and user actions."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QInputDialog, QLabel, QMainWindow, QMenu, QMessageBox, QProgressBar,
    QPushButton, QSizePolicy, QStackedWidget, QToolButton, QWidget,
)

from .. import DISPLAY_NAME, __version__, artwork, i18n, mal, models, scheduler
from ..i18n import _
from ..logs import log
from ..models import COMPLETED, WATCHING, Anime
from ..storage import load_state, save_state
from . import icons, theme
from .common import Clickable, ElidedLabel, clear, hbox, label, vbox
from .images import Cover
from .backdrop import Backdrop
from .desktop import DesktopMixin, app_icon
from .dialogs import ReplacementDialog
from .library import LibraryPage
from .profile import ProfilePage
from .services import ServicesMixin
from .common import asset
from .settings import SettingsPage
from .stats_page import StatsPage
from .tour import Step, TourOverlay
from .upnext import UpNextPage
from .welcome import WelcomePage
from .week import WeekPage


class Worker(QObject):
    progress = Signal(int, int, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable, args: tuple, with_progress: bool, cancellable: bool):
        super().__init__()
        self.fn, self.args = fn, args
        self.with_progress, self.cancellable = with_progress, cancellable
        self.stop_requested = False
        self.on_done: Callable = lambda result: None
        self.on_error: Callable[[str], None] | None = None

    def run(self) -> None:
        kwargs = {}
        if self.with_progress:
            kwargs["progress"] = self.progress.emit
        if self.cancellable:
            kwargs["should_stop"] = lambda: self.stop_requested
        try:
            self.done.emit(self.fn(*self.args, **kwargs))
        except mal.ImportError_ as e:
            log.warning("%s failed: %s", getattr(self.fn, "__name__", "task"), e)
            self.failed.emit(str(e))
        except Exception as e:  # surface anything unexpected instead of dying silently
            log.exception("%s crashed", getattr(self.fn, "__name__", "task"))
            self.failed.emit(f"{type(e).__name__}: {e}")


class MainWindow(ServicesMixin, DesktopMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(DISPLAY_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1480, 900)
        self.state = load_state()
        i18n.set_language(self.state.settings.language)  # before any widget is built
        models.title_language = self.state.settings.title_language
        s = self.state.settings
        theme.apply(QApplication.instance(), s.zoom, s.theme, s.backdrop)
        self._jobs: list[tuple[QThread, Worker]] = []
        self._exclusive: tuple[QThread, Worker] | None = None
        self._queue: list[tuple] = []

        self.backdrop = Backdrop()
        self.setCentralWidget(self.backdrop)
        # The shell switches between the welcome hub and the app itself.
        self.shell = QStackedWidget()
        vbox(self.backdrop, 0).addWidget(self.shell)
        self.main_view = QWidget()
        main_col = vbox(self.main_view, 0)
        self.root = hbox(spacing=0)
        main_col.addLayout(self.root, 1)
        # Phones / narrow windows: a bottom navigation bar replaces the sidebar.
        self.bottom_bar = QFrame()
        self.bottom_bar.setObjectName("bottomBar")
        self.bottom_bar.hide()
        main_col.addWidget(self.bottom_bar)
        self._compact: bool | None = None
        self.shell.addWidget(self.main_view)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.root.addWidget(self.sidebar)
        self.stack = QStackedWidget()
        self.root.addWidget(self.stack, 1)

        self.week_page = WeekPage(self)
        self.next_page = UpNextPage(self)
        self.lib_page = LibraryPage(self)
        self.profile_page = ProfilePage(self)
        self.settings_page = SettingsPage(self)
        self.stats_page = StatsPage(self)
        # Indexes 0–3 match the navigation buttons (Your Week, Up Next, Library, Stats).
        self.pages = [self.week_page, self.next_page, self.lib_page, self.stats_page,
                      self.profile_page, self.settings_page]
        for p in self.pages:
            self.stack.addWidget(p)
        self._stale: set[int] = set(range(len(self.pages)))
        self.stack.currentChanged.connect(self._page_shown)
        self._back_to = 0
        self._art_requested: set[int] = set()
        self.welcome = WelcomePage(self)
        self.shell.addWidget(self.welcome)
        self._build_sidebar()
        self._build_bottom_bar()
        if theme.COMPACT:
            self.sidebar.hide()

        self.busy = QProgressBar()
        self.busy.setObjectName("busy")
        self.busy.setMaximumWidth(theme.px(220))
        self.busy.setTextVisible(False)
        self.busy.hide()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("ghost")
        self.cancel_btn.hide()
        self.cancel_btn.clicked.connect(self._cancel_worker)
        self.statusBar().addPermanentWidget(self.busy)
        self.statusBar().addPermanentWidget(self.cancel_btn)

        self._shortcuts()
        QApplication.instance().installEventFilter(self)

        self._timer = QTimer(self, interval=15 * 60 * 1000, timeout=self._check_rollover)
        self._timer.start()
        self._check_rollover(refresh=False)
        self._configure_backdrop()
        self._init_desktop()
        start = {"week": 0, "next": 1, "library": 2}.get(s.start_page, 0)
        self._nav_to(start)
        if not self.state.onboarded:
            self.show_welcome()
        self.refresh()
        self.backdrop.set_enabled(self.state.settings.backdrop)
        QTimer.singleShot(300, self._startup_enrich)
        QTimer.singleShot(5000, self._auto_update_check)
        QTimer.singleShot(8000, self.check_announcements)

    # ------------------------------------------------------------------ layout

    def _build_sidebar(self) -> None:
        self.sidebar.setFixedWidth(theme.px(240))
        lay = vbox(self.sidebar, 2, 14)
        lay.addSpacing(theme.px(4))

        # Brand
        brand = hbox(spacing=10)
        logo = QLabel()
        size = theme.px(44)
        dpr = self.devicePixelRatioF() or 1.0
        pix = QPixmap(asset("logo-round.png")).scaled(round(size * dpr), round(size * dpr),
                                                      Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pix.setDevicePixelRatio(dpr)
        logo.setPixmap(pix)
        brand.addWidget(logo)
        names = vbox(spacing=0)
        names.addWidget(label(DISPLAY_NAME, "brand"))
        names.addWidget(label("輪廻 · anime planner", "brandSub"))
        brand.addLayout(names, 1)
        lay.addLayout(brand)
        lay.addSpacing(theme.px(16))

        # Navigation
        self.nav = QButtonGroup(self)
        self.nav_badges: dict[int, QLabel] = {}

        def nav_button(text: str, icon_name: str) -> QPushButton:
            b = QPushButton(text)
            b.setObjectName("nav")
            b.setIcon(icons.icon(icon_name))
            b.setIconSize(QSize(theme.px(19), theme.px(19)))
            b.setCursor(Qt.PointingHandCursor)
            return b

        lay.addWidget(label("PLAN", "sideSection"))
        for n, (text, icon_name) in enumerate([(_("Your Week"), "week"), (_("Up Next"), "next"),
                                               (_("Library"), "library"), (_("Stats"), "stats")]):
            if n == 2:
                lay.addWidget(label("COLLECTION", "sideSection"))
            b = nav_button(text, icon_name)
            b.setCheckable(True)
            inner = hbox(b, 0)
            inner.setContentsMargins(0, 0, theme.px(10), 0)
            inner.addStretch()
            count = label("", "navBadge")
            count.hide()
            inner.addWidget(count, alignment=Qt.AlignVCenter)
            self.nav_badges[n] = count
            self.nav.addButton(b, n)
            lay.addWidget(b)
        self.nav.button(0).setChecked(True)
        self.nav.idClicked.connect(self._go)

        imp = nav_button(_("Import"), "import")
        menu = QMenu(imp)
        menu.addAction("From MAL export file…", self.import_file)
        menu.addAction("From MAL username…", self.import_username)
        menu.addAction("From AniList username…", self.import_anilist)
        menu.addSeparator()
        menu.addAction("Refresh all show details", lambda: self.run_enrich(force=True))
        imp.clicked.connect(lambda: menu.exec(imp.mapToGlobal(imp.rect().topRight())))
        imp.setToolTip("Import or refresh your MyAnimeList list")
        self.import_btn = imp
        lay.addWidget(imp)

        lay.addStretch()

        # Up next mini card (filled by _update_sidebar_live)
        self.up_next_host = QWidget()
        self.up_next_lay = vbox(self.up_next_host, 0)
        lay.addWidget(self.up_next_host)
        lay.addSpacing(theme.px(10))

        line = QFrame()
        line.setObjectName("divider")
        lay.addWidget(line)
        lay.addSpacing(theme.px(6))
        self.settings_btn = nav_button(_("Settings"), "settings")
        self.settings_btn.setCheckable(True)
        self.settings_btn.clicked.connect(lambda: self.open_settings())
        lay.addWidget(self.settings_btn)

        self.update_btn = QPushButton("")
        self.update_btn.setObjectName("updateChip")
        self.update_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn.clicked.connect(self.open_update_page)
        self.update_btn.setVisible(bool(getattr(self, "update_info", None)))
        lay.addWidget(self.update_btn)
        foot = label(f"v{__version__}  ·  by <span style='color:{theme.ACCENT}; font-weight:700'>Zodchi</span>",
                     "faint", rich=True)
        foot.setAlignment(Qt.AlignCenter)
        lay.addSpacing(theme.px(4))
        lay.addWidget(foot)
        self._update_sidebar_live()

    def _update_sidebar_live(self) -> None:
        """Refresh the parts of the sidebar that change with your plan."""
        if not hasattr(self, "up_next_lay"):
            return
        items = self._today_items()
        left = sum(not i.done for i in items)
        badge_w = self.nav_badges.get(0)
        if badge_w is not None:
            badge_w.setText(str(left))
            badge_w.setVisible(left > 0)
            badge_w.setToolTip(f"{left} episode{'s' if left != 1 else ''} left today")
        watching = len(scheduler.current_rotation(self.state.library))
        b1 = self.nav_badges.get(1)
        if b1 is not None:
            b1.hide()
        clear(self.up_next_lay)
        frame = QFrame()
        frame.setObjectName("upNextCard")
        fl = hbox(frame, 10, 10)
        nxt = self.next_up()
        if nxt:
            anime, ep = nxt
            fl.addWidget(Cover(anime.image_url, anime.name, 36, 52, 6))
            col = vbox(spacing=1)
            col.addWidget(label("UP NEXT TODAY", "sideSection"))
            t = ElidedLabel(anime.name, "cardTitle")
            col.addWidget(t)
            col.addWidget(label(f"Episode {ep}" + (f" of {anime.episodes_total}" if anime.episodes_total else ""),
                                "small"))
            fl.addLayout(col, 1)
            frame.setCursor(Qt.PointingHandCursor)
            Clickable(frame).clicked.connect(lambda a=anime: self.open_profile(a))
            frame.setToolTip(f"Open {anime.name}")
        else:
            col = vbox(spacing=1)
            col.addWidget(label("TODAY", "sideSection"))
            col.addWidget(label("All caught up ✓" if items else
                                ("Day off" if watching else "Nothing planned"), "cardTitle"))
            col.addWidget(label(f"{watching} show{'s' if watching != 1 else ''} in rotation", "small"))
            fl.addLayout(col, 1)
        self.up_next_lay.addWidget(frame)

    def _rebuild_sidebar(self) -> None:
        current = self.stack.currentIndex()
        old = self.sidebar
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.root.replaceWidget(old, self.sidebar)
        old.hide()  # deletion is deferred; don't let it show through a translucent sidebar
        old.deleteLater()
        self._build_sidebar()
        if self.nav.button(current) is not None:
            self.nav.button(current).setChecked(True)
        else:  # on the profile page, which has no nav button
            self._clear_nav()

    def _go(self, n: int) -> None:
        self.stack.setCurrentIndex(n)
        self.settings_btn.setChecked(False)
        self._sync_bottom_bar()
        self._page_shown(n)  # no-op if currentChanged already refreshed it

    def refresh_pages(self, skip=None) -> None:
        """Refresh the visible page now; the others are marked stale and refresh when opened.

        Rebuilding every page on each tick gets slow with thousands of shows."""
        current = self.stack.currentIndex()
        for i, p in enumerate(self.pages):
            if p is skip:
                continue
            if i == current:
                p.refresh()
            else:
                self._stale.add(i)

    def _page_shown(self, n: int) -> None:
        if n in self._stale:
            self._stale.discard(n)
            self.pages[n].refresh()

    def open_profile(self, anime: Anime) -> None:
        if self.stack.currentWidget() is not self.profile_page:
            self._back_to = self.stack.currentIndex()
        self._clear_nav()
        self.stack.setCurrentWidget(self.profile_page)
        self.profile_page.show_anime(anime)

    def _clear_nav(self) -> None:
        self.nav.setExclusive(False)
        for b in self.nav.buttons():
            b.setChecked(False)
        self.settings_btn.setChecked(self.stack.currentWidget() is self.settings_page)
        self._sync_bottom_bar()

    # ------------------------------------------------------------------ phone layout

    def _build_bottom_bar(self) -> None:
        lay = hbox(self.bottom_bar, 0)
        lay.setContentsMargins(theme.px(6), theme.px(4), theme.px(6), theme.px(6))
        self.bnav: list[QToolButton] = []
        for n, (text, icon_name) in enumerate([(_("Week"), "week"), (_("Up Next"), "next"), (_("Library"), "library"),
                                               (_("Stats"), "stats"), (_("Settings"), "settings")]):
            b = QToolButton()
            b.setObjectName("bnav")
            b.setText(text)
            b.setIcon(icons.icon(icon_name))
            b.setIconSize(QSize(theme.px(22), theme.px(22)))
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setCheckable(True)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            b.clicked.connect(lambda _=False, n=n: self.open_settings() if n == 4 else self._nav_to(n))
            lay.addWidget(b)
            self.bnav.append(b)

    def _sync_bottom_bar(self) -> None:
        if not hasattr(self, "bnav"):
            return
        current = self.stack.currentIndex()
        for n, b in enumerate(self.bnav):
            b.setChecked(n == current if n < 4 else self.stack.currentWidget() is self.settings_page)

    def _apply_compact(self) -> None:
        """Switch between the desktop layout and the phone layout."""
        compact = self.width() < theme.px(820)
        if compact == self._compact:
            return
        self._compact = compact
        theme.COMPACT = compact
        self.sidebar.setVisible(not compact)
        self.bottom_bar.setVisible(compact)
        self.statusBar().setVisible(not compact and self.shell.currentWidget() is self.main_view)
        self._sync_bottom_bar()
        if compact:
            self.setMinimumWidth(0)
            QTimer.singleShot(0, self._fit_screen)
        QTimer.singleShot(0, self._refresh_all)

    def _fit_screen(self) -> None:
        """Never be wider than the screen (the window may have been sized for the desktop layout)."""
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen is None:
            return
        if self.width() > screen.width():
            self.resize(screen.width(), self.height())

    def _refresh_all(self) -> None:
        self.refresh_pages()
        if self.shell.currentWidget() is self.welcome:
            self.welcome.refresh()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "bottom_bar"):
            self._apply_compact()

    def nav_target(self, n: int):
        """The navigation button for page n in whichever layout is showing (for the tour)."""
        if theme.COMPACT:
            return self.bnav[n]
        return self.settings_btn if n == 4 else self.nav.button(n)

    def go_back(self) -> None:
        self._nav_to(self._back_to)

    def set_theme(self, name: str) -> None:
        if not name or name == theme.current:
            return
        self.state.settings.theme = name
        self._restyle()

    def set_backdrop(self, on: bool) -> None:
        if on == theme.BACKDROP:
            return
        self.state.settings.backdrop = on
        self._restyle()

    def _restyle(self) -> None:
        s = self.state.settings
        theme.apply(QApplication.instance(), theme.zoom(), s.theme, s.backdrop)
        self._rebuild_sidebar()
        self.backdrop.set_enabled(s.backdrop)
        self._update_backdrop()
        self.refresh_pages()
        if self.stack.currentWidget() is self.profile_page:
            self._clear_nav()
        self.save()

    def _update_backdrop(self) -> None:
        """Slides come from today's planned shows, or everything you're watching on a day off."""
        lib, week = self.state.library, self.state.week
        start = scheduler.plan_start(self.state)
        ids: list[int] = []
        if week and start:
            offset = (date.today() - start).days
            ids = [i.mal_id for i in week.items if i.day == offset]
        if not ids:
            ids = [a.mal_id for a in scheduler.current_rotation(lib)]
        shows = [lib[i] for i in dict.fromkeys(ids) if i in lib]
        # Full-HD fan art when we have it; banners/covers (blurred) as a fallback.
        self.backdrop.set_slides([(a.fanart_url, True) if a.fanart_url
                                  else (a.banner_url or a.image_url, False) for a in shows])
        if self.state.settings.backdrop:
            self.fetch_artwork(shows)

    def fetch_artwork(self, shows: list[Anime], refresh: bool = False) -> None:
        """Look up HD artwork and episode details (once per session per show). With refresh,
        already-checked shows are included too (the on-disk cache decides what's re-fetched)."""
        todo = [a for a in shows if (refresh or not a.artwork_checked) and a.mal_id not in self._art_requested]
        if not todo:
            return
        self._art_requested.update(a.mal_id for a in todo)

        def done(result: dict) -> None:
            changed = False
            for mal_id, art in result.items():
                if art and mal_id in self.state.library:
                    artwork.apply(self.state.library[mal_id], art)
                    changed = True
            if changed:
                self.save()
                self._update_backdrop()
                if self.stack.currentWidget() is self.profile_page:
                    self.profile_page.refresh()
                elif self.stack.currentWidget() is self.week_page:
                    self.week_page.refresh()  # episode titles and thumbnails

        self._run(artwork.fetch_many, (todo,), done, with_progress=False, exclusive=False,
                  on_error=lambda _msg: None)

    def set_title_language(self, lang: str) -> None:
        models.title_language = self.state.settings.title_language = lang
        self.save()
        self.refresh_pages()

    def _shortcuts(self) -> None:
        for keys, fn in [
            (("Ctrl++", "Ctrl+=", QKeySequence.ZoomIn), lambda: self.set_zoom(theme.zoom() + 0.1)),
            (("Ctrl+-", QKeySequence.ZoomOut), lambda: self.set_zoom(theme.zoom() - 0.1)),
            (("Ctrl+0",), lambda: self.set_zoom(1.0)),
            (("Ctrl+O",), self.import_file),
            (("Ctrl+I",), self.import_username),
            (("Ctrl+R",), self.replan_fresh),
            (("Ctrl+,",), lambda: self.open_settings()),
            (("Ctrl+Q",), self.quit_app),
            (("Ctrl+1",), lambda: self._nav_to(0)),
            (("Ctrl+2",), lambda: self._nav_to(1)),
            (("Ctrl+3",), lambda: self._nav_to(2)),
            (("Ctrl+4",), lambda: self._nav_to(3)),
        ]:
            seen = set()
            for k in keys:
                seq = QKeySequence(k)
                if seq.isEmpty() or seq.toString() in seen:
                    continue
                seen.add(seq.toString())
                QShortcut(seq, self, activated=fn, context=Qt.ApplicationShortcut)

    def _nav_to(self, n: int) -> None:
        self.nav.setExclusive(True)
        self.nav.button(n).setChecked(True)
        self._go(n)

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Wheel and event.modifiers() & Qt.ControlModifier:
            step = 0.1 if event.angleDelta().y() > 0 else -0.1
            self.set_zoom(theme.zoom() + step)
            return True
        return False

    def set_zoom(self, z: float) -> None:
        z = round(min(theme.MAX_ZOOM, max(theme.MIN_ZOOM, z)), 2)
        if abs(z - theme.zoom()) < 1e-6:
            return
        theme.apply(QApplication.instance(), z)
        self.state.settings.zoom = z
        self.busy.setMaximumWidth(theme.px(220))
        self._rebuild_sidebar()
        self.refresh_pages()
        if self.stack.currentWidget() is self.profile_page:
            self._clear_nav()
        self.statusBar().showMessage(f"Zoom {round(z * 100)}%", 1500)
        self.save()

    # ------------------------------------------------------------------ state

    def save(self) -> None:
        save_state(self.state)

    def _write_calendar(self) -> None:
        if self.state.settings.calendar_file:
            from ..calendar_export import write
            try:
                write(self.state)
            except OSError as e:
                log.warning("Couldn't write the calendar file: %s", e)

    def refresh(self) -> None:
        self.schedule_sync()
        self._write_calendar()
        self._update_backdrop()
        self.schedule_presence()
        self._update_sidebar_live()
        if self.shell.currentWidget() is self.welcome:
            self.welcome.refresh()
        self.refresh_pages()

    def replan(self) -> None:
        scheduler.replan(self.state)
        self.save()
        self.refresh()

    def replan_fresh(self) -> None:
        """Start a new 7-day plan today, dropping past days."""
        scheduler.fresh_plan(self.state)
        self.save()
        self.refresh()
        self.statusBar().showMessage("New plan: 7 days starting today", 5000)

    def _check_rollover(self, refresh: bool = True) -> None:
        if self.state.library and scheduler.plan_expired(self.state):
            scheduler.replan(self.state)
            self.save()
            if refresh:
                self.refresh()

    # ------------------------------------------------------------------ actions

    def toggle_item(self, idx: int) -> None:
        item = self.state.week.items[idx]
        event = scheduler.toggle_item(self.state, item)
        self.save()
        self.refresh()
        if event.finished:
            self._on_finished(event.finished)

    def move_show(self, mal_id: int, from_date, to_date) -> None:
        """Drag & drop: move a show's episodes from one day to another."""
        scheduler.move_show(self.state, mal_id, from_date, to_date)
        self.save()
        self.refresh()
        a = self.state.library.get(mal_id)
        self.statusBar().showMessage(f"Moved {a.name if a else 'show'} to {to_date:%A}", 5000)

    def reorder_day(self, on, mal_ids: list) -> None:
        scheduler.reorder_day(self.state, on, mal_ids)
        self.save()
        self.refresh()

    def set_show_option(self, anime: Anime, **values) -> None:
        """Per-show planning controls: paused / pinned / pace."""
        for key, value in values.items():
            setattr(anime, key, value)
        self.replan()

    def change_day_amount(self, day: int, delta: int) -> None:
        s = self.state.settings
        s.set_day_amount(day, max(0, s.day_amount(day) + delta))
        self.replan()

    def edit_progress(self, anime: Anime) -> None:
        maximum = anime.episodes_total or 9999
        n, ok = QInputDialog.getInt(self, "Episodes watched", anime.name,
                                    anime.episodes_watched, 0, maximum)
        if ok:
            self.apply_progress(anime, n)

    def apply_progress(self, anime: Anime, watched: int) -> None:
        event = scheduler.set_progress(self.state, anime, watched)
        self.replan()
        if event.finished:
            self._on_finished(event.finished)

    def set_status(self, anime: Anime, status: str) -> None:
        if status == COMPLETED and anime.episodes_total:
            self.apply_progress(anime, anime.episodes_total)
            return
        anime.status = status
        if status == WATCHING and not anime.started_on:
            anime.started_on = date.today().isoformat()
        self.replan()

    def start_show(self, anime: Anime) -> None:
        from ..recommender import rank
        rotation = scheduler.current_rotation(self.state.library)
        sug = next((s for s in rank(self.state.library, None, rotation) if s.anime is anime), None)
        anime.origin = {"date": date.today().isoformat(), "kind": "manual",
                        "reasons": [t for p, t in sug.reasons if p > 0][:4] if sug else []}
        anime.status = WATCHING
        anime.started_on = date.today().isoformat()
        self.replan()
        self._nav_to(0)
        self.statusBar().showMessage(f"Started {anime.name}", 5000)

    def toggle_excluded(self, anime: Anime) -> None:
        anime.excluded = not anime.excluded
        self.replan()

    def open_mal(self, anime: Anime) -> None:
        QDesktopServices.openUrl(QUrl(f"https://myanimelist.net/anime/{anime.mal_id}"))

    def _on_finished(self, finished: Anime) -> None:
        if not self.state.settings.auto_replace:
            self.statusBar().showMessage(f"Finished {finished.name}!", 8000)
            return
        cid = self.state.settings.mal_api_client_id()
        self.statusBar().showMessage(f"Finished {finished.name} — finding what comes next…")

        def find(state, show):
            return scheduler.find_replacement(state, show, lambda i: mal.lookup(i, cid))

        def done(result):
            sug, fetched = result
            added = []
            if sug:
                added = scheduler.apply_replacement(self.state, sug, fetched, finished=finished).added
            scheduler.replan(self.state)
            self.save()
            self.refresh()
            self.statusBar().clearMessage()
            ReplacementDialog(finished, sug, added, self).exec()
            if any(a.needs_enrichment for a in added):
                self.run_enrich()  # couldn't fetch details just now; retry in the background

        self._run(find, (self.state, finished), done, with_progress=False, exclusive=False)

    def open_settings(self, section: str | None = None) -> None:
        if self.stack.currentWidget() not in (self.profile_page, self.settings_page):
            self._back_to = self.stack.currentIndex()
        self.stack.setCurrentWidget(self.settings_page)
        self._clear_nav()
        self.settings_page.show_section(section or self.settings_page.section)

    # ------------------------------------------------------------------ welcome & tour

    def show_welcome(self) -> None:
        self.statusBar().hide()
        self.shell.setCurrentWidget(self.welcome)
        self.welcome.go(0)

    def finish_welcome(self, tour: bool) -> None:
        self.state.onboarded = True
        scheduler.replan(self.state)
        self.save()
        self.shell.setCurrentWidget(self.main_view)
        self.statusBar().setVisible(not theme.COMPACT)
        self._nav_to(0)
        self.refresh()
        if tour:
            QTimer.singleShot(250, self.start_tour)

    def start_tour(self) -> None:
        if self.shell.currentWidget() is not self.main_view:
            self.shell.setCurrentWidget(self.main_view)
        week = lambda: self._nav_to(0)  # noqa: E731
        steps = [
            Step(_("Your Week"), "Your plan for the next 7 days, built from the shows on your Watching list.",
                 lambda: self.nav_target(0), week),
            Step("Tick as you watch", "Click the circle on an episode when you've watched it — the rest of the "
                 "week replans itself. Use − / + on a day to watch more or less that day. Click any card "
                 "to open the show's profile.", lambda: getattr(self.week_page, "first_day", None), week),
            Step("Replan from today", "Fell behind or changed your mind? Start a fresh 7-day plan from today.",
                 lambda: getattr(self.week_page, "replan_btn", None), week),
            Step(_("Up Next"), "What takes over when each show ends. The next season always comes first — "
                 "even if it isn't on your MAL list yet — otherwise the best pick from Plan to Watch.",
                 lambda: self.nav_target(1)),
            Step(_("Library"), "Your whole list as posters. Click any show for its profile: why it's on your "
                 "list, cast & voice actors, and new seasons coming up.", lambda: self.nav_target(2)),
            Step(_("Stats"), "Episodes per week and per day, streaks, top genres and all-time totals.",
                 lambda: self.nav_target(3)),
            Step("Import", "Bring in or refresh your MyAnimeList list any time.",
                 lambda: getattr(self.lib_page, "import_btn", None) if theme.COMPACT else self.import_btn,
                 (lambda: self._nav_to(2)) if theme.COMPACT else None),
            Step("Up next today", "Today's next episode, always one click away.",
                 lambda: None if theme.COMPACT else self.up_next_host),
            Step(_("Settings"), "Themes, the background slideshow, notifications, Discord and more. "
                 "That's the tour — enjoy Rinne!", lambda: self.nav_target(4)),
        ]
        self._tour = TourOverlay(self.centralWidget(), steps)
        self._tour.finished.connect(lambda: self._nav_to(0))
        self._tour.start()

    def import_username_direct(self, username: str, client_id: str) -> None:
        self._run(mal.fetch_mal_list, (username, client_id), self._finish_import)

    def settings_changed(self, kind: str = "save") -> None:
        """Called by the Settings page after it changes a setting."""
        s = self.state.settings
        if kind == "replan":
            scheduler.replan(self.state)
            self.save()
            self.refresh_pages(skip=self.settings_page)
            return
        if kind == "backdrop":
            self._configure_backdrop()
            if s.backdrop != theme.BACKDROP:
                self._restyle()
        elif kind == "discord":
            self.update_presence(force=True)
            if self.stack.currentWidget() is self.settings_page:
                QTimer.singleShot(1200, self.settings_page.refresh)
        elif kind == "tray":
            self.update_tray()
        elif kind == "calendar":
            self._write_calendar()
        self.save()

    def _configure_backdrop(self) -> None:
        s = self.state.settings
        self.backdrop.configure(s.slide_seconds, s.backdrop_dim)

    def restore_backup(self, path: str) -> None:
        import json

        from ..storage import State
        try:
            state = State.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError) as e:
            QMessageBox.warning(self, "Restore failed", f"That file isn't a valid backup: {e}")
            return
        self.state = state
        models.title_language = state.settings.title_language
        self.save()
        self._restyle()
        self.replan()
        self.statusBar().showMessage("Backup restored", 6000)

    def reset_settings(self) -> None:
        from ..models import Settings
        old = self.state.settings
        fresh = Settings()
        # Keep account details: they're data, not preferences.
        fresh.mal_username, fresh.mal_client_id = old.mal_username, old.mal_client_id
        fresh.discord_app_id = old.discord_app_id
        self.state.settings = fresh
        models.title_language = fresh.title_language
        self.save()
        self._restyle()
        self.replan()

    # ------------------------------------------------------------------ background work

    def _run(self, fn: Callable, args: tuple, on_done: Callable, with_progress: bool = True,
             cancellable: bool = False, exclusive: bool = True,
             on_error: Callable[[str], None] | None = None) -> None:
        """Run `fn` on a worker thread. Exclusive jobs (imports, metadata refresh) run one at a
        time; non-exclusive ones (a finale's replacement lookup) start immediately."""
        if exclusive and self._exclusive is not None:
            self._queue.append((fn, args, on_done, with_progress, cancellable, on_error))
            return
        thread = QThread(self)
        worker = Worker(fn, args, with_progress, cancellable)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.on_done = on_done
        worker.on_error = on_error
        # Connect to bound methods of this window so results are delivered on the GUI thread
        # (a plain function or lambda would run on the worker thread).
        worker.progress.connect(self._on_progress)
        worker.done.connect(self._on_job_done)
        worker.failed.connect(self._on_job_failed)
        for sig in (worker.done, worker.failed):
            sig.connect(thread.quit)
        job = (thread, worker)
        thread.finished.connect(lambda job=job: self._job_finished(job))
        self._jobs.append(job)
        if exclusive:
            self._exclusive = job
        self.busy.setRange(0, 0)
        self.busy.show()
        self.cancel_btn.setVisible(any(w.cancellable for _, w in self._jobs))
        thread.start()

    def _on_job_done(self, result) -> None:
        worker = self.sender()
        if isinstance(worker, Worker):
            worker.on_done(result)

    def _on_job_failed(self, message: str) -> None:
        log.warning("Background task failed: %s", message)
        worker = self.sender()
        if isinstance(worker, Worker) and worker.on_error:
            worker.on_error(message)
        else:
            QMessageBox.warning(self, "Something went wrong", message)

    def _on_progress(self, n: int, total: int, text: str) -> None:
        self.busy.setRange(0, total)
        self.busy.setValue(n)
        self.statusBar().showMessage(text)

    def _cancel_worker(self) -> None:
        for _job, worker in self._jobs:
            if worker.cancellable:
                worker.stop_requested = True

    def _job_finished(self, job: tuple) -> None:
        thread, worker = job
        self._jobs.remove(job)
        worker.deleteLater()
        thread.deleteLater()
        if job is self._exclusive:
            self._exclusive = None
        self.save()
        if not self._jobs:
            self.busy.hide()
        self.cancel_btn.setVisible(any(w.cancellable for _, w in self._jobs))
        if self._queue and self._exclusive is None:
            fn, args, on_done, wp, c, err = self._queue.pop(0)
            self._run(fn, args, on_done, wp, c, on_error=err)

    def closeEvent(self, event) -> None:
        if not self._quitting and self.close_keeps_running():
            self.save()
            self.hide()
            event.ignore()
            if not getattr(self, "_told_tray", False):
                self._told_tray = True
                self.notify(DISPLAY_NAME, "Still running in the tray. Quit from the tray menu.")
            return
        self.shutdown_desktop()
        self._queue.clear()
        for thread, worker in list(self._jobs):
            worker.stop_requested = True
            thread.quit()
            if not thread.wait(3000):
                # Stuck in a slow network retry; nothing it holds needs cleaning up.
                thread.terminate()
                thread.wait()
        self.save()
        super().closeEvent(event)
