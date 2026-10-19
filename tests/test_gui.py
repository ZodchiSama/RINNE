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

from PySide6.QtCore import QEvent, QMimeData, QPointF, Qt, QThread  # noqa: E402
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
    from rinne import net
    monkeypatch.setattr(net, "online", lambda timeout=3.0: True)

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
    catalog = getattr(request, "param", None)  # indirect parametrize: a language code, or a test catalog
    if isinstance(catalog, str):
        state.settings.language = catalog
    elif catalog:
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
    dst = next((r for r in rows if r.on > today), None)
    if dst is None:
        pytest.skip("Saturday: no later day this week to drop onto")
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


def test_offline_chip_and_catching_up_when_back(win, app, monkeypatch):
    import time

    from rinne import net
    state = {"up": False}
    monkeypatch.setattr(net, "online", lambda timeout=3.0: state["up"])
    pulled = []
    monkeypatch.setattr(win, "pull_accounts", lambda: pulled.append(1))

    def check():
        win.check_online()
        end = time.time() + 3
        while time.time() < end and win._online_timer.isActive() is False:
            app.processEvents()
            time.sleep(0.01)
        app.processEvents()

    win._online_timer.stop()
    check()
    assert win.offline and win.offline_btn.isVisible() and "offline" in win.toast.text.text()
    win._online_timer.stop()
    state["up"] = True
    check()
    assert not win.offline and not win.offline_btn.isVisible()
    assert pulled == [1] and win.toast.text.text() == "Back online"


ALLOWED_LATIN = {"Rinne", "MyAnimeList", "AniList", "MAL", "Shikimori", "Discord", "Zodchi", "OVA", "ONA", "Ctrl",
                 "Rich", "Presence", "GitHub", "Full", "HD", "API", "ID", "Client", "Application", "Google",
                 "Thunderbird", "GNOME", "ics", "Linux", "Windows", "TheTVDB", "ani", "zip", "Jikan", "Qt"}


def _latin_words(win, page):
    import re

    from PySide6.QtWidgets import QAbstractButton, QLabel
    titles = {w for a in win.state.library.values() for t in a.all_titles() for w in re.findall(r"[A-Za-z]+", t)}
    found = set()
    for w in page.findChildren(QLabel) + page.findChildren(QAbstractButton):
        if not w.isVisible():
            continue
        text = re.sub(r"<[^>]+>", " ", re.sub(r"(?s)<code>.*?</code>", " ", w.text()))  # paths stay as they are
        text = re.sub(r"[\w.-]+\.(?:net|com|co|io|me|org)\S*", " ", text)  # and so do web addresses
        for word in re.findall(r"[A-Za-z]{2,}", text):
            if not ({word, word.capitalize()} & ALLOWED_LATIN) and word.lower() not in {x.lower() for x in ALLOWED_LATIN} \
                    and word not in titles:
                found.add(f"{word} ({text.strip()[:40]!r})")
    return found


@pytest.mark.parametrize("win", ["ru"], indirect=True)
def test_russian_interface_has_no_leftover_english(win, app):
    """Every visible label and button on the main pages is translated (names and brands aside)."""
    for n in range(4):
        win._go(n)
        app.processEvents()
        assert not _latin_words(win, win.pages[n]), (n, sorted(_latin_words(win, win.pages[n]))[:10])
    win.open_profile(win.state.library[1])
    app.processEvents()
    assert not _latin_words(win, win.profile_page), sorted(_latin_words(win, win.profile_page))[:10]
    for section in ("general", "schedule", "notifications", "accounts", "data"):
        win.open_settings(section)
        app.processEvents()
        assert not _latin_words(win, win.settings_page), (section, sorted(_latin_words(win, win.settings_page))[:10])


def test_sharing_a_show(win, app):
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtGui import QKeySequence
    from PySide6.QtWidgets import QLabel

    from rinne.gui import share
    a = win.state.library[1]
    a.anilist_id, a.user_score = 154587, 9
    card = share.render_card(a)
    assert (card.width(), card.height()) == (1200, 630)
    sites = dict(share.links(a))
    assert sites == {"MyAnimeList": "https://myanimelist.net/anime/1", "AniList": "https://anilist.co/anime/154587",
                     "Shikimori": "https://shikimori.io/animes/1"}
    assert share.share_text(a) == "Frieren — Watching · episode 3 of 28 · ★ 9/10\nhttps://myanimelist.net/anime/1"

    share.copy_card(win, a)
    assert not QApplication.clipboard().pixmap().isNull()
    menu = share.share_menu(win, a)
    menu.actions()[-1].trigger()  # Copy title
    assert QApplication.clipboard().text() == "Frieren"

    # Ctrl C on a selected poster in the Library copies its title.
    win._go(2)
    app.processEvents()
    view = win.lib_page.view
    row = next(r for r in range(win.lib_page.proxy.rowCount())
               if win.lib_page.proxy.index(r, 0).data(_Qt.DisplayRole) == "Dandadan")
    view.setCurrentIndex(win.lib_page.proxy.index(row, 0))
    view.setFocus()
    QApplication.clipboard().clear()
    from PySide6.QtTest import QTest
    QTest.keySequence(view, QKeySequence.Copy)
    assert QApplication.clipboard().text() == "Dandadan"

    # The profile's title can be selected and copied by hand.
    win.open_profile(a)
    app.processEvents()
    titles = [w for w in win.profile_page.findChildren(QLabel) if w.text() == "Frieren"]
    assert titles and titles[0].textInteractionFlags() & _Qt.TextSelectableByMouse


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="desktop icon folders are a Linux thing")
def test_stale_installed_icons_are_refreshed(win, tmp_path, monkeypatch):
    """Icons install.sh copied into the desktop's icon folder are replaced when the app's icon changes;
    sizes that were never installed aren't created."""
    from rinne.gui.common import asset
    base = tmp_path / "data" / "icons" / "hicolor"
    old = base / "256x256" / "apps" / "rinne.png"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old icon")
    monkeypatch.setattr("rinne.gui.desktop.QProcess.startDetached", lambda *a: True)
    win.refresh_installed_icons()
    assert old.read_bytes() == open(asset("icon-256.png"), "rb").read()
    assert not (base / "48x48" / "apps" / "rinne.png").exists()


def test_week_card(win, app):
    from datetime import timedelta

    from rinne.gui import share
    from rinne.models import ScheduleItem
    start = date.fromisoformat(win.state.week.week_start)
    win.state.week.items = [ScheduleItem(d, m, 1, done=(d < 2 or (d == 2 and m == 1))) for d in range(7) for m in (1, 2)]
    w = share.week_summary(win.state, start + timedelta(days=3))
    assert w["days"] == ["done", "done", "open", "today", "upcoming", "upcoming", "upcoming"]
    assert (w["episodes"], w["complete"], w["planned"]) == (5, 2, 7)
    assert {a.mal_id for a in w["shows"]} == {1, 2}
    card = share.render_week_card(win.state, start + timedelta(days=3))
    assert (card.width(), card.height()) == (1200, 630)


def test_build_my_watching_list_previews_then_applies(win, app, monkeypatch):
    from rinne.gui import lineup_dialog
    shown = {}

    def run(dlg):
        shown["ok"] = dlg.ok.text()
        dlg.size.setValue(2)  # 3 watching → 2: the lowest-ranked one moves to On Hold
        app.processEvents()
        shown["hold"] = [a.title for a in dlg.result.hold]
        dlg.accept()
        return True
    monkeypatch.setattr(lineup_dialog.LineupDialog, "exec", run)
    win.build_lineup()
    app.processEvents()
    lib = win.state.library
    watching = [a for a in lib.values() if a.status == "watching"]
    assert len(watching) == 2 and shown["hold"] == ["Ao no Hako"]  # unstarted, so it goes first
    assert all(lib[i].status == "on_hold" for i, a in lib.items() if a.title in shown["hold"])
    assert win.state.settings.lineup_size == 2
    assert all(it.mal_id in {a.mal_id for a in watching} for it in win.state.week.items)


def test_expired_sign_in_is_shown_and_reconnecting_sends_what_changed(win, app, monkeypatch):
    """Oct 14: MAL's sign-in expired, Rinne dropped it with one easy-to-miss notification, and a
    reconnect would have reset the baseline, so the ticks made meanwhile were never sent."""
    from rinne import mal, sync
    s = win.state.settings
    s.mal_token, s.mal_user = {"access_token": "x", "refresh_token": "y", "expires_at": 9e12}, "Zodchi"
    win.state.synced["mal"] = sync.baseline(win.state.library)

    def rejected(*a, **k):
        raise mal.SignInRejected("expired")
    monkeypatch.setattr(mal, "fetch_mal_list", rejected)
    win.pull_account("mal", quiet=True)
    for _i in range(50):
        app.processEvents()
        if not s.mal_token:
            break
        QThread.msleep(20)
    assert not s.mal_token and s.expired_accounts == {"mal": "Zodchi"}
    assert win.toast.isVisible() and "MyAnimeList" in win.toast.text.text()

    win.state.library[1].episodes_watched += 1  # watched while disconnected
    win._keep_or_reset_baseline("mal", "zodchi")  # same account comes back
    assert [a.mal_id for a in sync.pending_changes(win.state.library, win.state.synced["mal"])] == [1]
    assert s.expired_accounts == {}

    s.expired_accounts = {"mal": "Zodchi"}
    win._keep_or_reset_baseline("mal", "someone_else")  # a different account starts fresh
    assert sync.pending_changes(win.state.library, win.state.synced["mal"]) == []

    win.state.library[1].episodes_watched += 1  # expired under 1.1.4: no record of whose it was
    win._keep_or_reset_baseline("mal", "zodchi")
    assert [a.mal_id for a in sync.pending_changes(win.state.library, win.state.synced["mal"])] == [1]
    win.disconnect_account("mal")  # Disconnect forgets the baseline: connecting again starts fresh
    win._keep_or_reset_baseline("mal", "zodchi")
    assert sync.pending_changes(win.state.library, win.state.synced["mal"]) == []


def test_overtime_section_saves_last_weeks_days(win, app):
    from datetime import datetime, timedelta as td

    from rinne import scheduler
    from rinne.models import ScheduleItem, WeekPlan
    st = win.state
    start = date.fromisoformat(st.week.week_start) - td(days=7)
    watched = st.library[2].episodes_watched
    # Last week: Monday left one episode of Dandadan unwatched; Sunday was completed.
    st.overtime = WeekPlan(start.isoformat(), [ScheduleItem(1, 2, watched + 1)], calendar=True)
    st.overtime_until = (datetime.now() + td(hours=3)).isoformat(timespec="minutes")
    st.day_log[start.isoformat()] = "done"
    win._go(0)
    win.refresh()
    app.processEvents()
    assert win.week_page.overtime is not None and "left" in win.week_page.overtime_left.text()
    win.toggle_overtime(0)
    app.processEvents()
    assert st.day_log[(start + td(days=1)).isoformat()] == "saved"
    assert st.overtime is None and win.week_page.overtime is None
    assert "saved" in win.toast.text.text()
    assert scheduler.overtime_days(st) == []


def test_a_second_launch_shows_the_running_window_instead(win, app):
    """Two copies (one hidden in the tray) saved over each other's ticks."""
    from rinne.gui import instance
    shown = []
    server = instance.claim(lambda: shown.append(True))
    assert server is not None
    assert instance.claim(lambda: None) is None  # the second launch steps aside…
    for _i in range(50):
        app.processEvents()
        if shown:
            break
        QThread.msleep(10)
    assert shown  # …and the first one comes forward
    server.close()


def test_copies_of_overtime_episodes_are_dropped_on_startup(app, tmp_path, monkeypatch):
    """Experimental builds v1.1.5.3–5 planned overtime's episodes into the new week too; a restart
    during overtime drops those copies and fills the room, leaving today's other episodes alone."""
    from datetime import datetime, timedelta as td

    from rinne import scheduler
    from rinne.gui import window
    from rinne.models import ScheduleItem, WeekPlan
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("x")))
    st = State(library={1: show(1, "Frieren", episodes_watched=3, episodes_total=28),
                        2: show(2, "Dandadan", episodes_watched=0, episodes_total=12)},
               settings=Settings(check_updates=False, discord_enabled=False, sync_anilist=False,
                                 daily_episodes=[2] * 7))
    st.onboarded = True
    today = date.today()
    first = scheduler.week_start_of(today)
    d = (today - first).days
    st.week = WeekPlan(first.isoformat(), [ScheduleItem(d, 1, 4), ScheduleItem(d, 2, 1)], calendar=True)
    st.overtime = WeekPlan((first - td(days=7)).isoformat(), [ScheduleItem(1, 1, 4)], calendar=True)
    st.overtime_until = (datetime.now() + td(hours=2)).isoformat(timespec="minutes")
    save_state(st)
    w = window.MainWindow()
    try:
        todays = {(i.mal_id, i.episode) for i in w.state.week.items if i.day == d}
        assert (1, 4) not in todays  # the copy is gone (it's overtime's)…
        assert (2, 1) in todays  # …today's own episode stays put…
        assert len(todays) == 2  # …and the room is filled again
    finally:
        w._quitting = True
        w.close()
