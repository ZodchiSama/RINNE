"""Interface tests: the real window, offscreen, with a temporary profile and no network."""

import os
import socket
import sys
import urllib.error
import urllib.request
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QEvent, QMimeData, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402
from PySide6.QtWidgets import QAbstractScrollArea, QApplication, QWidget  # noqa: E402

from rinne.models import FINISHED_AIRING, Anime, Settings  # noqa: E402
from rinne.storage import State, load_state, save_state  # noqa: E402


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication(sys.argv)


def show(mal_id, title, **kw):
    kw.setdefault("episodes_total", 12)
    kw.setdefault("airing_status", FINISHED_AIRING)
    kw.setdefault("status", "watching")
    return Anime(mal_id=mal_id, title=title, enriched=True, artwork_checked=True, anilist_id=mal_id,
                 title_native="アニメ", meta_version=99, **kw)


@pytest.fixture
def win(app, tmp_path, monkeypatch, request):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    def offline(*_a, **_k):
        raise urllib.error.URLError(socket.gaierror(-3, "Temporary failure in name resolution"))
    monkeypatch.setattr(urllib.request, "urlopen", offline)

    shows = [show(1, "Frieren", episodes_watched=3, episodes_total=28),
             show(2, "Dandadan", episodes_watched=10),
             show(3, "Ao no Hako", episodes_total=25),
             show(4, "Mushishi", status="plan_to_watch", episodes_total=26),
             show(5, "Ping Pong", status="completed", episodes_watched=11, episodes_total=11, user_score=9)]
    from rinne import __version__
    settings = Settings(check_updates=False, discord_enabled=False, notify_new_episodes=False,
                        last_seen_version=__version__,
                        notify_premieres=False, weekly_recap=False, sync_mal=False, sync_anilist=False)
    state = State(library={a.mal_id: a for a in shows}, settings=settings)
    state.onboarded = True
    catalog = getattr(request, "param", None)  # indirect parametrize: a translation to use
    if catalog:
        import json

        from rinne import i18n
        (tmp_path / "xx.json").write_text(json.dumps(catalog), encoding="utf-8")
        monkeypatch.setattr(i18n, "LOCALE_DIR", tmp_path)
        state.settings.language = "xx"
    save_state(state)

    from rinne.gui import window
    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *exc: errors.append(exc))
    w = window.MainWindow()
    w.notify = lambda *a: None
    w.resize(1400, 900)
    w.show()
    app.processEvents()
    w.errors = errors
    yield w
    w._quitting = True
    w.close()
    w.deleteLater()
    # processEvents() skips deferred deletes; without this every old window stays alive and
    # makes each later stylesheet change slower.
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    from rinne import i18n
    i18n.set_language("en")
    assert not errors, errors


def test_every_page_renders(win, app):
    for n, page in enumerate(win.pages[:4]):
        win._go(n)
        app.processEvents()
        assert win.stack.currentWidget() is page
        assert page.isVisible()
    win.open_profile(win.state.library[1])
    app.processEvents()
    assert win.stack.currentWidget() is win.profile_page
    win.open_settings()
    app.processEvents()
    assert win.stack.currentWidget() is win.settings_page


def test_ticking_an_episode_advances_progress_and_saves(win, app):
    items = win.state.week.items
    idx = next(i for i, it in enumerate(items) if it.mal_id == 2 and not it.done)
    win.toggle_item(idx)
    app.processEvents()
    assert win.state.library[2].episodes_watched == 11
    assert load_state().library[2].episodes_watched == 11  # written to disk


def test_stale_pages_refresh_when_opened(win, app):
    win._go(0)
    lib = win.lib_page
    win.state.library[4].status = "watching"
    win.refresh()  # library is hidden: marked stale, not rebuilt
    assert 2 in win._stale
    win._go(2)
    assert 2 not in win._stale
    assert "4 watching" in lib.count.text()


def test_dropping_a_show_on_another_day_moves_it(win, app):
    today = date.today()
    week = win.week_page
    rows = [r for r in week.findChildren(QWidget) if getattr(r, "on", None) and r.acceptDrops()]
    src = next(r for r in rows if r.on == today and r._cards())
    dst = next(r for r in rows if r.on > today)
    mal_id = src._cards()[0].mal_id
    mime = QMimeData()
    mime.setData("application/x-rinne-show", f"{mal_id}|{today.isoformat()}".encode())
    event = QDropEvent(QPointF(5, 5), Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
    dst.dropEvent(event)
    app.processEvents()
    start = date.fromisoformat(win.state.week.week_start)
    on_dst = [it.mal_id for it in win.state.week.items if it.day == (dst.on - start).days]
    on_src = [it.mal_id for it in win.state.week.items if it.day == (today - start).days]
    assert mal_id in on_dst
    assert mal_id not in on_src


def _widest(win: QWidget, limit: int = 330) -> list[str]:
    """The innermost visible widgets that need more than `limit` px (for failure messages)."""
    wide = [w for w in win.findChildren(QWidget) if w.isVisible() and w.minimumSizeHint().width() > limit]
    inner = [w for w in wide if not any(c in wide for c in w.findChildren(QWidget))]
    return [f"{type(w).__name__}#{w.objectName()} {w.minimumSizeHint().width()}px "
            f"{getattr(w, 'text', lambda: '')()!r:.40}" for w in inner][:8]


def _overflowing(page: QWidget, limit: int) -> list[str]:
    """Visible widgets whose right edge passes `limit`, ignoring ones inside sideways-scrolling areas."""
    bad = []
    for w in page.findChildren(QWidget):
        if not w.isVisible() or w.width() == 0:
            continue
        parent, sideways = w.parentWidget(), False
        while parent is not None and parent is not page:
            if isinstance(parent, QAbstractScrollArea) and (
                    parent.property("sideways") or parent.horizontalScrollBarPolicy() != Qt.ScrollBarAlwaysOff):
                sideways = True
                break
            parent = parent.parentWidget()
        if sideways:
            continue
        right = w.mapTo(page.window(), w.rect().topRight()).x()
        if right > limit + 1:
            bad.append(f"{type(w).__name__}#{w.objectName()} right={right}")
    return bad


def test_phone_width_has_no_sideways_overflow(win, app):
    import time
    # The first resize switches to the phone layout, which lowers the minimum width; some
    # platforms (Windows) deliver the resize events a little later, so keep trying briefly.
    end = time.time() + 5
    while time.time() < end and win.width() > 360:
        win.resize(320, 700)
        app.processEvents()
        time.sleep(0.02)
    assert win.width() <= 360, (win.minimumSizeHint(), _widest(win))
    for n in range(4):
        win._go(n)
        app.processEvents()
        assert not _overflowing(win.pages[n], win.width()), (n, _overflowing(win.pages[n], win.width())[:5],
                                                              _widest(win.pages[n], 250))


@pytest.mark.parametrize("win", [{"_language": "Test", "Library": "Bibliothek",
                                  "Appearance": "Aussehen", "Interface language": "Sprache"}], indirect=True)
def test_interface_uses_the_chosen_translation(win, app):
    from PySide6.QtWidgets import QLabel, QPushButton
    texts = {b.text() for b in win.findChildren(QPushButton)}
    assert "Bibliothek" in texts and "Library" not in texts
    assert "Up Next" in texts  # untranslated strings stay English
    win.open_settings()
    app.processEvents()
    assert "Aussehen" in {b.text() for b in win.settings_page.findChildren(QPushButton)}
    win.settings_page.show_section("general")
    app.processEvents()
    assert "Sprache" in {lbl.text() for lbl in win.settings_page.findChildren(QLabel)}


def test_finishing_today_celebrates_then_folds_the_day(win, app, monkeypatch):
    import time

    from rinne.gui import week as week_mod
    monkeypatch.setattr(week_mod, "CELEBRATION_MS", 60)
    monkeypatch.setattr(week_mod, "FOLD_MS", 40)
    win._on_finished = lambda *a: None  # a finale opens a "what's next" dialog
    win._go(0)
    today = (date.today() - date.fromisoformat(win.state.week.week_start)).days
    while not win.state.week.day_complete(today):
        idx = next(n for n, it in enumerate(win.state.week.items) if it.day == today and not it.done)
        before = [(it.mal_id, it.episode) for it in win.state.week.items if it.day == today]
        win.toggle_item(idx)
        app.processEvents()
        after = [(it.mal_id, it.episode) for it in win.state.week.items if it.day == today]
        assert sorted(before) == sorted(after)  # ticking doesn't reshuffle today's list
    assert win.state.day_log[date.today().isoformat()] == "done"
    assert win.week_page.findChildren(week_mod.Celebration)  # playing over today's row
    end = time.time() + 2
    while time.time() < end and not win.week_page.findChildren(week_mod.CompletedDay):
        app.processEvents()
        time.sleep(0.01)
    assert win.week_page.findChildren(week_mod.CompletedDay)  # folded to one line
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert not win.week_page.findChildren(week_mod.Celebration)


def test_manual_import_explains_what_connecting_gives_unless_connected(win, app, monkeypatch):
    from rinne.gui import connect
    asked = []
    monkeypatch.setattr(connect, "confirm_manual", lambda w: asked.append(1) or False)
    imported = []
    monkeypatch.setattr(win, "import_file", lambda: imported.append("file"))
    win.import_manually("file")
    assert asked == [1] and imported == []  # chose "Connect instead" / cancel
    win.state.settings.anilist_token = "t"
    win.import_manually("file")
    assert asked == [1] and imported == ["file"]  # connected: no nagging


def test_whats_new_shows_once_after_an_update(win, app, monkeypatch):
    from rinne.gui import dialogs
    shown = []
    monkeypatch.setattr(dialogs.WhatsNewDialog, "exec", lambda self: shown.append(1))
    win.state.settings.last_seen_version = "0.5.2"
    win._maybe_whats_new()
    win._maybe_whats_new()
    assert shown == [1]


def test_update_popup_and_notification_once_per_release(win, app, monkeypatch):
    from rinne import updates
    from rinne.gui import dialogs
    popups, notes = [], []
    monkeypatch.setattr(dialogs.UpdateDialog, "exec", lambda self: popups.append(1))
    monkeypatch.setattr(win, "notify", lambda title, body: notes.append(title))
    monkeypatch.setattr(updates, "managed_by", lambda: "")
    rel = {"version": "9.0.0", "url": "https://example.com", "name": "", "notes": "**Big** update"}
    monkeypatch.setattr(updates, "check", lambda: rel)
    import time
    for _ in range(2):  # the second check finds the same release
        win.update_info = None
        win.check_for_updates()
        end = time.time() + 3
        while time.time() < end and win.update_info is None:  # the check runs in a worker thread
            app.processEvents()
            time.sleep(0.01)
    assert popups == [1] and notes == ["Rinne 9.0.0 is available"]


def test_only_the_current_page_is_highlighted_in_the_sidebar(win, app):
    """After a profile or Settings (which clear the highlight), clicking pages must move it."""
    win.open_profile(win.state.library[1])
    app.processEvents()
    for n in (1, 2, 3, 0):
        win.nav.button(n).click()  # a real click, like the mouse
        app.processEvents()
        assert [b.isChecked() for b in win.nav.buttons()] == [i == n for i in range(4)]
    win.open_settings()
    app.processEvents()
    win.nav.button(2).click()
    app.processEvents()
    assert [b.isChecked() for b in win.nav.buttons()] == [False, False, True, False]
    assert not win.settings_btn.isChecked()


def test_background_pull_brings_in_progress_made_elsewhere(win, app, monkeypatch):
    import time

    from rinne import anilist
    from rinne.gui import services
    win.state.settings.anilist_token, win.state.settings.anilist_user = "tok", "me"
    win.state.synced["anilist"] = {}
    account = []
    for a in win.state.library.values():
        b = Anime(**{k: v for k, v in a.to_dict().items()})
        if a.mal_id == 2:
            b.episodes_watched = a.episodes_watched + 1  # watched one more on AniList's app
        account.append(b)
    monkeypatch.setattr(anilist, "fetch_user_list", lambda user, progress=None, token="": (account, 0))
    pushed = []
    monkeypatch.setattr(services.sync, "push_all", lambda *a, **k: pushed.append(a) or {})
    start = date.fromisoformat(win.state.week.week_start)
    today = (date.today() - start).days
    first = next(it for it in win.state.week.items if it.mal_id == 2 and it.day == today)
    win.pull_accounts()
    end = time.time() + 3
    while time.time() < end and win.state.library[2].episodes_watched != first.episode:
        app.processEvents()
        time.sleep(0.01)
    assert win.state.library[2].episodes_watched == first.episode
    ticked = next(it for it in win.state.week.items if it.mal_id == 2 and it.episode == first.episode)
    assert ticked.done  # the plan knows it was watched elsewhere
    assert "Updated from AniList: 1 show" in win.statusBar().currentMessage()
    assert sync_pending(win) == []  # nothing to send back


def sync_pending(win):
    from rinne import sync
    return sync.pending_changes(win.state.library, win.state.synced["anilist"])


def test_a_tick_can_be_undone(win, app):
    win._on_finished = lambda *a: None
    start = date.fromisoformat(win.state.week.week_start)
    today = (date.today() - start).days
    idx = next(n for n, it in enumerate(win.state.week.items) if it.day == today and it.mal_id == 1)
    before = win.state.library[1].episodes_watched
    win.toggle_item(idx)
    app.processEvents()
    assert win.state.library[1].episodes_watched == before + 1
    assert win.toast.isVisible() and "watched" in win.toast.text.text()
    win.toast.action.click()  # Undo
    app.processEvents()
    assert win.state.library[1].episodes_watched == before
    assert not win.toast.isVisible()
    assert not any(it.done for it in win.state.week.items if it.mal_id == 1 and it.day == today)
