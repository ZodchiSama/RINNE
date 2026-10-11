"""Sharing a show: a card image with your progress, links to MyAnimeList / AniList / Shikimori,
a short text, or just the title — copied to the clipboard or saved."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu

from .. import DISPLAY_NAME
from ..i18n import _
from ..models import Anime, status_label
from .common import asset
from .images import cache

if TYPE_CHECKING:
    from .window import MainWindow

CARD_W, CARD_H = 1200, 630
# Brand colours (brand/README.md), dark mode: the card looks the same whatever theme you use.
BG_TOP, BG_BOTTOM = QColor("#1b1830"), QColor("#0e1016")
GRAD_A, GRAD_B = QColor("#8b5cf6"), QColor("#ec4899")
TEXT, MUTED, SOFT = QColor("#ece8f6"), QColor("#a5a3b8"), QColor("#c9b8ff")


def links(anime: Anime) -> list[tuple[str, str]]:
    """(site, url) for the show on each site that has it."""
    out = [("MyAnimeList", f"https://myanimelist.net/anime/{anime.mal_id}")]
    if anime.anilist_id:
        out.append(("AniList", f"https://anilist.co/anime/{anime.anilist_id}"))
    out.append(("Shikimori", f"https://shikimori.io/animes/{anime.mal_id}"))
    return out


def progress_line(anime: Anime) -> str:
    """"Watching · episode 6 of 28 · ★ 9/10" — the entry, in the interface language."""
    parts = [status_label(anime.status)]
    if anime.episodes_total:
        parts.append(_("episode {n} of {total}").format(n=anime.episodes_watched, total=anime.episodes_total))
    elif anime.episodes_watched:
        parts.append(_("episode {n}").format(n=anime.episodes_watched))
    if anime.user_score:
        parts.append(f"★ {anime.user_score}/10")
    return " · ".join(parts)


def share_text(anime: Anime) -> str:
    return f"{anime.name} — {progress_line(anime)}\n{links(anime)[0][1]}"


def render_card(anime: Anime) -> QPixmap:
    """A 1200×630 image (the size social sites preview): cover, title, your progress and score."""
    pix = QPixmap(CARD_W, CARD_H)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    bg = QLinearGradient(0, 0, 0, CARD_H)
    bg.setColorAt(0, BG_TOP)
    bg.setColorAt(1, BG_BOTTOM)
    p.fillRect(pix.rect(), bg)

    # The wheel, large and faint, behind the right edge (as on the brand banners).
    mark = QPixmap(asset("mark-dark.png"))
    if not mark.isNull():
        p.setOpacity(0.10)
        size = 760
        p.drawPixmap(QRectF(CARD_W - size * 0.62, (CARD_H - size) / 2, size, size), mark, QRectF(mark.rect()))
        p.setOpacity(1.0)

    # Cover.
    cw, ch, x0, y0 = 300, 430, 70, 100
    cover = cache().cover(anime.image_url, anime.name, cw, ch, 22)
    p.drawPixmap(x0, y0, cover)

    left, right = x0 + cw + 56, CARD_W - 70
    width = right - left
    y = y0

    def font(size: int, weight=QFont.Normal, italic: bool = False) -> QFont:
        f = QFont()
        f.setPixelSize(size)
        f.setWeight(weight)
        f.setItalic(italic)
        return f

    # Title: up to three lines, shrinking for long names.
    for size in (64, 54, 46, 40):
        f = font(size, QFont.Bold)
        rect = QFontMetrics(f).boundingRect(0, 0, width, 10_000, Qt.TextWordWrap, anime.name)
        if rect.height() <= QFontMetrics(f).lineSpacing() * 3:
            break
    p.setFont(f)
    p.setPen(TEXT)
    title_h = min(rect.height(), QFontMetrics(f).lineSpacing() * 3)
    p.drawText(QRectF(left, y, width, title_h), Qt.TextWordWrap, anime.name)
    y += title_h + 10

    other = next((t for t in (anime.title_english, anime.title_native, anime.title_romaji)
                  if t and t != anime.name), "")
    if other:
        p.setFont(font(26))
        p.setPen(MUTED)
        p.drawText(QRectF(left, y, width, 36), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(font(26)).elidedText(other, Qt.ElideRight, width))
        y += 48

    # Status and score.
    y = max(y + 18, y0 + 230)
    p.setFont(font(30, QFont.DemiBold))
    p.setPen(SOFT)
    status = status_label(anime.status)
    p.drawText(QRectF(left, y, width, 40), Qt.AlignLeft | Qt.AlignVCenter, status)
    if anime.user_score:
        p.setPen(QColor("#fbbf24"))
        sw = QFontMetrics(font(30, QFont.DemiBold)).horizontalAdvance(status)
        p.drawText(QRectF(left + sw + 28, y, 300, 40), Qt.AlignLeft | Qt.AlignVCenter, f"★ {anime.user_score}/10")
    y += 60

    # Progress bar.
    total = anime.episodes_total
    done = anime.episodes_watched
    frac = min(1.0, done / total) if total else (1.0 if done else 0.0)
    bar = QRectF(left, y, width, 16)
    path = QPainterPath()
    path.addRoundedRect(bar, 8, 8)
    p.fillPath(path, QColor(255, 255, 255, 28))
    if frac > 0:
        fill = QPainterPath()
        fill.addRoundedRect(QRectF(left, y, max(16, width * frac), 16), 8, 8)
        g = QLinearGradient(left, 0, left + width, 0)
        g.setColorAt(0, GRAD_A)
        g.setColorAt(1, GRAD_B)
        p.fillPath(fill, g)
    y += 30
    p.setFont(font(26))
    p.setPen(MUTED)
    eps = (_("Episode {n} of {total}").format(n=done, total=total) if total
           else _("Episode {n}").format(n=done))
    p.drawText(QRectF(left, y, width, 36), Qt.AlignLeft | Qt.AlignVCenter, eps)

    # Footer: the small wheel and the app name.
    small = QPixmap(asset("mark-simple-dark.png"))
    fy = CARD_H - 70
    if not small.isNull():
        p.drawPixmap(QRectF(left, fy - 4, 44, 44), small, QRectF(small.rect()))
    p.setFont(font(28, QFont.Bold))
    p.setPen(TEXT)
    p.drawText(QRectF(left + 58, fy, 400, 36), Qt.AlignLeft | Qt.AlignVCenter, DISPLAY_NAME.upper())
    p.setFont(font(22, italic=True))
    p.setPen(MUTED)
    p.drawText(QRectF(left + 180, fy, width - 180, 36), Qt.AlignLeft | Qt.AlignVCenter,
               _("輪廻 · anime planner"))
    p.setPen(QPen(QColor(255, 255, 255, 18), 2))
    p.drawRoundedRect(QRectF(pix.rect()).adjusted(1, 1, -1, -1), 0, 0)
    p.end()
    return pix


def copy_text(win: MainWindow, text: str, what: str) -> None:
    QApplication.clipboard().setText(text)
    win.toast.show_message(_("Copied {what}").format(what=what), ms=2500)


def copy_card(win: MainWindow, anime: Anime) -> None:
    QApplication.clipboard().setPixmap(render_card(anime))
    win.toast.show_message(_("Card copied — paste it into Discord or anywhere else"), ms=3500)


def save_card(win: MainWindow, anime: Anime) -> None:
    safe = "".join(c for c in anime.name if c.isalnum() or c in " -_").strip()[:60] or "rinne"
    path, _filter = QFileDialog.getSaveFileName(win, _("Save card"), str(Path.home() / f"{safe}.png"),
                                                _("PNG image (*.png)"))
    if path:
        render_card(anime).save(path, "PNG")
        win.toast.show_message(_("Card saved"), ms=2500)


def share_menu(win: MainWindow, anime: Anime, parent=None) -> QMenu:
    """The Share menu for a show (profile button, Library and Your Week right-click)."""
    menu = QMenu(parent or win)
    menu.addAction(_("Copy as image"), lambda: copy_card(win, anime))
    menu.addAction(_("Save image…"), lambda: save_card(win, anime))
    menu.addSeparator()
    for site, url in links(anime):
        menu.addAction(_("Copy {site} link").format(site=site), lambda u=url: copy_text(win, u, _("link")))
    menu.addAction(_("Copy as text"), lambda: copy_text(win, share_text(anime), _("text")))
    menu.addAction(_("Copy title"), lambda: copy_text(win, anime.name, _("title")))
    return menu


# --------------------------------------------------------------------------- your week


def week_summary(state, today=None) -> dict:
    """This week's numbers for the week card: episodes and minutes watched, day results, shows."""
    from datetime import date, timedelta
    today = today or date.today()
    week = state.week
    start = date.fromisoformat(week.week_start) if week else today - timedelta(days=(today.weekday() + 1) % 7)
    days, shows, eps, minutes = [], [], 0, 0
    for d in range(7):
        on = start + timedelta(days=d)
        items = week.for_day(d) if week else []
        if week and week.day_complete(d):
            days.append("done")
        elif items and on < today:
            days.append("open")
        elif items:
            days.append("today" if on == today else "upcoming")
        else:
            days.append("none")
        for it in items:
            if it.done:
                eps += 1
                a = state.library.get(it.mal_id)
                if a is not None:
                    minutes += a.minutes_per_episode
                    if a not in shows:
                        shows.append(a)
    planned = sum(1 for k in days if k != "none")
    return {"start": start, "end": start + timedelta(days=6), "days": days, "episodes": eps,
            "minutes": minutes, "shows": shows, "complete": days.count("done"), "planned": planned}


def render_week_card(state, today=None) -> QPixmap:
    """A 1200×630 card of your week: the days you completed, episodes and time, and the shows."""
    from ..i18n import _n, strftime, weekday_name
    from .common import fmt_minutes
    w = week_summary(state, today)
    pix = QPixmap(CARD_W, CARD_H)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    bg = QLinearGradient(0, 0, 0, CARD_H)
    bg.setColorAt(0, BG_TOP)
    bg.setColorAt(1, BG_BOTTOM)
    p.fillRect(pix.rect(), bg)
    mark = QPixmap(asset("mark-dark.png"))
    if not mark.isNull():
        p.setOpacity(0.10)
        p.drawPixmap(QRectF(CARD_W - 760 * 0.62, (CARD_H - 760) / 2, 760, 760), mark, QRectF(mark.rect()))
        p.setOpacity(1.0)

    def font(size, weight=QFont.Normal, italic=False):
        f = QFont()
        f.setPixelSize(size)
        f.setWeight(weight)
        f.setItalic(italic)
        return f

    x, y, width = 70, 64, CARD_W - 140
    done_all = w["planned"] and w["complete"] == w["planned"]
    p.setFont(font(54, QFont.Bold))
    p.setPen(TEXT)
    p.drawText(QRectF(x, y, width, 70), Qt.AlignLeft | Qt.AlignVCenter,
               _("Week complete!") if done_all else _("My week in anime"))
    y += 74
    p.setFont(font(26))
    p.setPen(MUTED)
    p.drawText(QRectF(x, y, width, 36), Qt.AlignLeft | Qt.AlignVCenter,
               f"{strftime(w['start'], '%d %B')} – {strftime(w['end'], '%d %B %Y')}".lstrip("0"))
    y += 64

    # The seven days.
    gap, size = 14, 104
    colors = {"done": QColor("#34d399"), "open": QColor("#fbbf24"), "today": GRAD_A}
    for d, kind in enumerate(w["days"]):
        r = QRectF(x + d * (size + gap), y, size, size)
        path = QPainterPath()
        path.addRoundedRect(r, 18, 18)
        p.fillPath(path, QColor(255, 255, 255, 16))
        if kind in colors:
            p.setPen(QPen(colors[kind], 3))
            p.drawPath(path)
        p.setPen(MUTED if kind == "none" else TEXT)
        p.setFont(font(20, QFont.DemiBold))
        p.drawText(QRectF(r.left(), r.top() + 12, size, 28), Qt.AlignCenter, weekday_name((d + 6) % 7, short=True))
        mark_text = {"done": "✓", "open": "!", "today": "•", "upcoming": "·", "none": "–"}[kind]
        p.setPen(colors.get(kind, MUTED))
        p.setFont(font(40, QFont.Bold))
        p.drawText(QRectF(r.left(), r.top() + 38, size, 56), Qt.AlignCenter, mark_text)
    y += size + 30

    # The numbers, in a row.
    cols = [(_n("{n} episode", "{n} episodes", w["episodes"]), TEXT),
            (fmt_minutes(w["minutes"]), SOFT),
            (_("{done} of {planned} days complete").format(done=w["complete"], planned=w["planned"]), MUTED)]
    col_w = width / 3
    for n, (text, color) in enumerate(cols):
        f = font(34, QFont.Bold if n < 2 else QFont.Normal)
        p.setFont(f)
        p.setPen(color)
        p.drawText(QRectF(x + n * col_w, y, col_w - 20, 46), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(f).elidedText(text, Qt.ElideRight, int(col_w - 20)))
    y += 74

    # Posters of the shows watched this week.
    pw, ph_ = 76, 108
    for n, a in enumerate(w["shows"][:12]):
        p.drawPixmap(x + n * (pw + 12), y, cache().cover(a.image_url, a.name, pw, ph_, 10))

    # Footer, as on the show card.
    small = QPixmap(asset("mark-simple-dark.png"))
    fy = CARD_H - 64
    if not small.isNull():
        p.drawPixmap(QRectF(x, fy - 4, 44, 44), small, QRectF(small.rect()))
    p.setFont(font(28, QFont.Bold))
    p.setPen(TEXT)
    p.drawText(QRectF(x + 58, fy, 400, 36), Qt.AlignLeft | Qt.AlignVCenter, DISPLAY_NAME.upper())
    p.setFont(font(22, italic=True))
    p.setPen(MUTED)
    p.drawText(QRectF(x + 180, fy, width - 180, 36), Qt.AlignLeft | Qt.AlignVCenter, _("輪廻 · anime planner"))
    p.end()
    return pix


def week_share_menu(win: MainWindow, parent=None) -> QMenu:
    menu = QMenu(parent or win)

    def copy() -> None:
        QApplication.clipboard().setPixmap(render_week_card(win.state))
        win.toast.show_message(_("Card copied — paste it into Discord or anywhere else"), ms=3500)

    def save() -> None:
        path, _filter = QFileDialog.getSaveFileName(win, _("Save card"), str(Path.home() / "rinne-week.png"),
                                                    _("PNG image (*.png)"))
        if path:
            render_week_card(win.state).save(path, "PNG")
            win.toast.show_message(_("Card saved"), ms=2500)
    menu.addAction(_("Copy as image"), copy)
    menu.addAction(_("Save image…"), save)
    return menu
