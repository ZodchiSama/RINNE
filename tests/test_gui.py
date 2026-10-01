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
    settings = Settings(check_updates=False, discord_enabled=False, notify_new_episodes=False,
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
    for _ in range(2):  # the first resize switches to the phone layout, which lowers the minimum width
        win.resize(320, 700)
        app.processEvents()
    assert win.width() <= 360, win.minimumSizeHint()
    for n in range(4):
        win._go(n)
        app.processEvents()
        assert not _overflowing(win.pages[n], win.width()), (n, _overflowing(win.pages[n], win.width())[:5])


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
