"""The show profile page: why it's on your list, synopsis, cast & voice actors, and more."""

from __future__ import annotations

import html
import re
from datetime import date, datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QMenu, QPushButton, QWidget

from .. import anilist, artwork, explain, models
from ..models import CURRENTLY_AIRING, LIST_STATUSES, STATUS_LABELS, Anime
from . import theme
from .common import (
    Clickable, FlowLayout, badge, button_row, card, clear, hbox, label, page_margin, progress, set_margins,
    vbox, watch_button,
)
from .images import Cover, cache
from .pages import scroll_page

if TYPE_CHECKING:
    from .window import MainWindow

RELATION_LABELS = {
    "SEQUEL": "Sequel", "PREQUEL": "Prequel", "SIDE_STORY": "Side story", "PARENT": "Parent story",
    "SPIN_OFF": "Spin-off", "ALTERNATIVE": "Alternative", "SUMMARY": "Summary",
    "COMPILATION": "Compilation", "OTHER": "Other", "CHARACTER": "Shares characters",
}
RELATION_ORDER = ["PREQUEL", "SEQUEL", "PARENT", "SIDE_STORY", "SPIN_OFF", "ALTERNATIVE",
                  "SUMMARY", "COMPILATION", "CHARACTER", "OTHER"]
SOURCE_LABELS = {"MANGA": "Manga", "LIGHT_NOVEL": "Light novel", "ORIGINAL": "Original",
                 "VISUAL_NOVEL": "Visual novel", "WEB_NOVEL": "Web novel", "NOVEL": "Novel",
                 "VIDEO_GAME": "Video game", "GAME": "Game"}


def pick_title(t: dict | None) -> str:
    t = t or {}
    if models.title_language == models.ENGLISH and t.get("english"):
        return t["english"]
    if models.title_language == models.NATIVE and t.get("native"):
        return t["native"]
    return t.get("romaji") or t.get("english") or t.get("native") or "?"


def when_text(node: dict, today: date | None = None) -> str:
    """Human release timing for an AniList media node."""
    today = today or date.today()
    nxt = node.get("nextAiringEpisode")
    if node.get("status") == "RELEASING" and nxt:
        when = datetime.fromtimestamp(nxt["airingAt"])
        return f"Airing now — episode {nxt['episode']} on {when:%a %d %b}"
    d = node.get("startDate") or {}
    y, m, day = d.get("year"), d.get("month"), d.get("day")
    if y and m and day:
        start = date(y, m, day)
        if start > today:
            n = (start - today).days
            return f"Starts {start:%a %d %B %Y} (in {n} day{'s' if n != 1 else ''})"
        return f"Started {start:%d %B %Y}"
    if y and m:
        return f"Expected {date(y, m, 1):%B %Y}"
    if node.get("season") and node.get("seasonYear"):
        return f"Expected {node['season'].title()} {node['seasonYear']}"
    if y:
        return f"Expected {y}"
    return "Release date not announced yet"


def _fans(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def clean_description(text: str) -> str:
    text = re.sub(r"<br\s*/?>\s*(<br\s*/?>\s*)*", "<br><br>", text or "")
    text = re.sub(r"\(Source:[^)]*\)", "", text)
    text = re.sub(r"<(?!/?(i|b|em|strong|br)\b)[^>]+>", "", text)
    return text.strip() or "No synopsis available."


class Banner(QWidget):
    """Wide banner art that fades into the page background."""

    def __init__(self, url: str, fallback: str, color: str, parent=None):
        super().__init__(parent)
        self.url, self.fallback = url, fallback
        self.color = QColor(color or theme.ACCENT_SOFT)
        self.setMinimumHeight(theme.px(300))
        cache().loaded.connect(self._on_loaded)  # bound method: disconnects when deleted

    def _on_loaded(self, url: str) -> None:
        if url in (self.url, self.fallback):
            self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = self.rect()
        path = QPainterPath()
        path.addRoundedRect(QRectF(r), theme.px(16), theme.px(16))
        p.setClipPath(path)
        p.fillRect(r, self.color.darker(260))
        pix = cache().raw(self.url) or cache().raw(self.fallback)
        if pix:
            scaled = pix.scaled(r.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.setOpacity(1.0 if cache().raw(self.url) else 0.35)
            p.drawPixmap((r.width() - scaled.width()) // 2, (r.height() - scaled.height()) // 3, scaled)
            p.setOpacity(1.0)
        fade = QLinearGradient(0, 0, 0, r.height())
        fade.setColorAt(0.0, theme.qcolor(theme.BG, 60))
        fade.setColorAt(0.55, theme.qcolor(theme.BG, 175))
        fade.setColorAt(1.0, theme.qcolor(theme.BG, 250))
        p.fillRect(r, fade)
        side = QLinearGradient(0, 0, r.width(), 0)
        side.setColorAt(0.0, theme.qcolor(theme.BG, 200))
        side.setColorAt(0.6, theme.qcolor(theme.BG, 0))
        p.fillRect(r, side)


class ProfilePage(QWidget):
    def __init__(self, win: MainWindow):
        super().__init__()
        self.win = win
        self.anime: Anime | None = None
        self.data: dict | None = None
        self.error = ""
        self.upcoming: list[dict] | None = None
        self._upcoming_for: int | None = None
        outer = vbox(self)
        self.area, inner = scroll_page()
        outer.addWidget(self.area)
        self.body = vbox(inner, 18, 28)

    # ------------------------------------------------------------------ loading

    def show_anime(self, anime: Anime) -> None:
        self.anime, self.data, self.error = anime, None, ""
        self.upcoming, self._upcoming_for = None, None
        self.refresh()
        self.area.verticalScrollBar().setValue(0)
        mal_id = anime.mal_id
        if anime.anilist_id:
            self._load_upcoming(mal_id, anime.anilist_id)
        if anime.mal_id in self.win.state.library:
            self.win.fetch_artwork([anime])  # 1080p fan art for the hero banner
        self.win._run(anilist.profile, (mal_id,), lambda d, m=mal_id: self._loaded(m, d),
                      with_progress=False, exclusive=False,
                      on_error=lambda msg, m=mal_id: self._failed(m, msg))

    def _load_upcoming(self, mal_id: int, anilist_id: int) -> None:
        if self._upcoming_for == mal_id:
            return
        self._upcoming_for = mal_id

        def done(result, m=mal_id):
            if self.anime and self.anime.mal_id == m:
                self.upcoming = result
                self.refresh()

        def failed(_msg, m=mal_id):
            if self.anime and self.anime.mal_id == m:
                self.upcoming = []
                self.refresh()

        self.win._run(anilist.upcoming, (anilist_id,), done, with_progress=False,
                      exclusive=False, on_error=failed)

    def _loaded(self, mal_id: int, data: dict) -> None:
        if self.anime and self.anime.mal_id == mal_id:
            if data and data.get("id"):
                self._load_upcoming(mal_id, data["id"])
            self.data = data or {}
            if not data:
                self.error = "AniList has no entry for this show."
            self.refresh()

    def _failed(self, mal_id: int, message: str) -> None:
        if self.anime and self.anime.mal_id == mal_id:
            self.error = f"Couldn't load details: {message}"
            self.refresh()

    # ------------------------------------------------------------------ building

    def refresh(self) -> None:
        if self.anime is None:
            return
        scroll = self.area.verticalScrollBar().value()
        clear(self.body)
        set_margins(self.body, page_margin())
        a = self.anime = self.win.state.library.get(self.anime.mal_id, self.anime)
        d = self.data or {}

        back = QPushButton("←  Back")
        back.setObjectName("ghost")
        back.clicked.connect(self.win.go_back)
        self.body.addWidget(back, alignment=Qt.AlignLeft)
        self.body.addWidget(self._hero(a, d))

        why_frame, why = card(margins=18, spacing=8)
        why_frame.setProperty("accent", True)
        why.addWidget(label("Why it's on your list", "h2"))
        for line in explain.why(self.win.state, a):
            why.addWidget(label(f"•  {line}", "", wrap=True))
        self.body.addWidget(why_frame)
        self.body.addWidget(self._coming_up())
        if eps := self._episodes(a):
            self.body.addWidget(eps)

        if self.data is None and not self.error:
            self.body.addWidget(label("Loading details from AniList…", "muted"))
        elif self.error:
            self.body.addWidget(label(self.error, "muted", wrap=True))
        if d:
            self.body.addWidget(self._synopsis(d))
            if cast := self._cast(d):
                self.body.addWidget(cast)
            if rel := self._relations(d):
                self.body.addWidget(rel)
            if staff := self._staff(d):
                self.body.addWidget(staff)
            if recs := self._recommendations(d):
                self.body.addWidget(recs)
        self.body.addStretch()
        self.area.verticalScrollBar().setValue(scroll)

    def _hero(self, a: Anime, d: dict) -> QWidget:
        banner = Banner(a.fanart_url or d.get("bannerImage") or a.banner_url, a.image_url,
                        (d.get("coverImage") or {}).get("color") or a.cover_color)
        compact = theme.COMPACT
        # Phones: cover above the details so the title and buttons get the full width.
        row = (vbox if compact else hbox)(banner, 12 if compact else 24, 16 if compact else 26)
        row.addWidget(Cover(a.image_url, a.name, *((96, 136, 10) if compact else (170, 242, 14))),
                      alignment=Qt.AlignLeft if compact else Qt.AlignBottom)
        info = vbox(spacing=8)
        info.addStretch()
        title = label(a.name, "h1", wrap=True)
        info.addWidget(title)
        others = [t for t in a.all_titles() if t != a.name]
        if others:
            info.addWidget(label("  ·  ".join(others[:3]), "muted", wrap=True))

        chips = FlowLayout(spacing=6)
        facts = [a.media_type or None]
        if a.episodes_total:
            facts.append(f"{a.episodes_total} episodes")
        if a.episode_minutes:
            facts.append(f"{a.episode_minutes} min")
        if d.get("season") and d.get("seasonYear"):
            facts.append(f"{d['season'].title()} {d['seasonYear']}")
        studios = [s["name"] for s in (d.get("studios") or {}).get("nodes", [])]
        if studios:
            facts.append(", ".join(studios[:2]))
        if d.get("source"):
            facts.append(SOURCE_LABELS.get(d["source"], d["source"].replace("_", " ").title()))
        for f in facts:
            if f:
                chips.addWidget(badge(f, "chipLabel"))
        if a.mean_score:
            chips.addWidget(badge(f"★ {a.mean_score:.1f}", "badgeAmber"))
        if a.airing_status == CURRENTLY_AIRING:
            chips.addWidget(badge("Airing", "badgeGreen"))
        rank = next((r for r in d.get("rankings") or [] if r.get("allTime")), None)
        if rank:
            chips.addWidget(badge(f"#{rank['rank']} {rank['context'].replace('all time', 'all-time')}", "badge"))
        chip_host = QWidget()
        chip_host.setLayout(chips)
        info.addWidget(chip_host)

        status_row = hbox(spacing=10)
        color = theme.STATUS_COLORS.get(a.status, theme.MUTED)
        st = label(f"<span style='color:{color}'>●</span>  {STATUS_LABELS.get(a.status, a.status)}"
                   f"  ·  Ep {a.episodes_watched} / {a.episodes_total or '?'}", "", rich=True)
        status_row.addWidget(st)
        bar = progress(a)
        if theme.COMPACT:
            bar.setMinimumWidth(theme.px(60))
        else:
            bar.setFixedWidth(theme.px(180))
        status_row.addWidget(bar)
        status_row.addStretch()
        info.addLayout(status_row)

        actions = FlowLayout(spacing=8) if compact else hbox(spacing=8)  # buttons wrap on phones
        in_lib = a.mal_id in self.win.state.library
        if in_lib:
            status_btn = QPushButton("Status ▾")
            status_btn.setObjectName("primary")
            menu = QMenu(status_btn)
            for s in LIST_STATUSES:
                act = menu.addAction(STATUS_LABELS[s])
                act.setCheckable(True)
                act.setChecked(a.status == s)
                act.triggered.connect(lambda _=False, s=s: self.win.set_status(a, s))
            status_btn.setMenu(menu)
            actions.addWidget(status_btn)
            prog = QPushButton("Set progress")
            prog.setObjectName("ghost")
            prog.clicked.connect(lambda: self.win.edit_progress(a))
            actions.addWidget(prog)
        if watch := watch_button(a):
            actions.addWidget(watch)
        mal_btn = QPushButton("MyAnimeList ↗")
        mal_btn.setObjectName("ghost")
        mal_btn.clicked.connect(lambda: self.win.open_mal(a))
        actions.addWidget(mal_btn)
        if d.get("siteUrl"):
            al = QPushButton("AniList ↗")
            al.setObjectName("ghost")
            al.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(d["siteUrl"])))
            actions.addWidget(al)
        if compact:
            host = QWidget()
            host.setLayout(actions)
            info.addWidget(host)
        else:
            actions.addStretch()
            info.addLayout(actions)
        row.addLayout(info, 1)
        return banner

    def _coming_up(self) -> QFrame:
        frame, lay = card(margins=18, spacing=12)
        head = hbox()
        head.addWidget(label("Coming up", "h2"))
        head.addStretch()
        head.addWidget(label("New seasons, films and spin-offs in this franchise", "faint"))
        lay.addLayout(head)
        if self.upcoming is None:
            lay.addWidget(label("Checking for announced seasons…", "muted"))
            return frame
        if not self.upcoming:
            lay.addWidget(label("Nothing new announced for this franchise yet.", "muted"))
            return frame
        for entry in self.upcoming:
            lay.addWidget(self._upcoming_row(entry))
        return frame

    def _upcoming_row(self, entry: dict) -> QWidget:
        node = entry["node"]
        mal_id = node.get("idMal")
        in_lib = self.win.state.library.get(mal_id) if mal_id else None
        row_w = QFrame()
        row_w.setObjectName("episode")
        row = hbox(row_w, 14, 10)
        title = in_lib.name if in_lib else pick_title(node.get("title"))
        row.addWidget(Cover((node.get("coverImage") or {}).get("large", ""), title, 58, 82, 8))
        col = vbox(spacing=4)
        rel = entry["relation"]
        tags = [badge("This show" if rel == "SELF" else RELATION_LABELS.get(rel, rel.title()), "badge"),
                badge("Airing now", "badgeGreen") if node.get("status") == "RELEASING"
                else badge("Announced", "badgeAmber")]
        if node.get("format"):
            tags.append(badge(node["format"].replace("_", " "), "chipLabel"))
        col.addWidget(button_row(*tags, spacing=6))
        col.addWidget(label(title, "bigTitle", wrap=True))
        col.addWidget(label(when_text(node), "", wrap=True))
        extra = []
        if entry.get("via"):
            extra.append(f"Follows {pick_title(entry['via'])}")
        if in_lib:
            extra.append(f"On your list: {STATUS_LABELS.get(in_lib.status, in_lib.status)}")
        if extra:
            col.addWidget(label("  ·  ".join(extra), "small", wrap=True))
        row.addLayout(col, 1)
        if in_lib:
            Clickable(row_w).clicked.connect(lambda: self.win.open_profile(in_lib))
            row_w.setToolTip("Open its profile")
        elif mal_id:
            Clickable(row_w).clicked.connect(
                lambda: QDesktopServices.openUrl(QUrl(f"https://myanimelist.net/anime/{mal_id}")))
            row_w.setToolTip("Open on MyAnimeList")
        return row_w

    def _episodes(self, a: Anime) -> QFrame | None:
        """Every episode with its screenshot, title and air date; watched ones dimmed."""
        details = artwork.episodes(a)
        if not details:
            return None
        nums = sorted(int(n) for n in details)
        if len(nums) > 60:  # long-running shows: the stretch around your progress
            start = max(1, a.episodes_watched - 2)
            nums = [n for n in nums if start <= n < start + 36]
        frame, lay = card(margins=18, spacing=12)
        head = hbox()
        head.addWidget(label("Episodes", "h2"))
        head.addStretch()
        head.addWidget(label(f"{a.episodes_watched} of {a.episodes_total or len(details)} watched", "faint"))
        lay.addLayout(head)
        flow = vbox(spacing=8) if theme.COMPACT else FlowLayout(spacing=12, uniform_rows=True)
        for n in nums:
            ep = details[str(n)]
            box = QFrame()
            box.setObjectName("episode")
            if not theme.COMPACT:
                box.setFixedWidth(theme.px(204))
            col = (hbox if theme.COMPACT else vbox)(box, 8, 8)
            col.addWidget(Cover(ep.get("image", ""), str(n), *((96, 54, 6) if theme.COMPACT else (188, 106, 8))))
            text = vbox(spacing=2)
            top = hbox(spacing=6)
            top.addWidget(label(f"Episode {n}", "small"))
            if n <= a.episodes_watched:
                top.addWidget(badge("✓ Watched", "badgeGreen"))
            elif n == a.episodes_watched + 1:
                top.addWidget(badge("Up next"))
            top.addStretch()
            text.addLayout(top)
            text.addWidget(label(artwork.episode_title(ep, models.title_language) or f"Episode {n}",
                                 "epTitle", wrap=True))
            if ep.get("airdate"):
                text.addWidget(label(ep["airdate"], "faint"))
            text.addStretch()
            col.addLayout(text, 1)
            if ep.get("overview"):
                box.setToolTip(ep["overview"])
            if n <= a.episodes_watched:
                fx = QGraphicsOpacityEffect(box)
                fx.setOpacity(0.55)
                box.setGraphicsEffect(fx)
            flow.addWidget(box)
        host = QWidget()
        host.setLayout(flow)
        lay.addWidget(host)
        return frame

    def _synopsis(self, d: dict) -> QFrame:
        frame, lay = card(margins=18, spacing=10)
        lay.addWidget(label("Synopsis", "h2"))
        lay.addWidget(label(clean_description(d.get("description") or ""), "body", wrap=True, rich=True))
        tags = list(d.get("genres") or []) + [t["name"] for t in d.get("tags") or []
                                              if t.get("rank", 0) >= 70 and not t.get("isMediaSpoiler")][:8]
        if tags:
            flow = FlowLayout(spacing=6)
            for t in tags:
                flow.addWidget(badge(t, "chipLabel"))
            host = QWidget()
            host.setLayout(flow)
            lay.addWidget(host)
        return frame

    def _cast(self, d: dict) -> QFrame | None:
        edges = (d.get("characters") or {}).get("edges") or []
        edges = [e for e in edges if e.get("voiceActors")]
        if not edges:
            return None
        frame, lay = card(margins=18, spacing=12)
        head = hbox()
        head.addWidget(label("Cast & voice actors", "h2"))
        head.addStretch()
        head.addWidget(label("Japanese cast · ★ = fans on AniList", "faint"))
        lay.addLayout(head)
        top_fans = max((e["voiceActors"][0].get("favourites") or 0) for e in edges)
        # Phones: one full-width card per row; desktop: a grid of equal-height cards.
        flow = vbox(spacing=10) if theme.COMPACT else FlowLayout(spacing=12, uniform_rows=True)
        for e in edges:
            flow.addWidget(self._cast_card(e, top_fans))
        host = QWidget()
        host.setLayout(flow)
        lay.addWidget(host)
        return frame

    def _cast_card(self, e: dict, top_fans: int) -> QFrame:
        char, va = e["node"], e["voiceActors"][0]
        frame = QFrame()
        frame.setObjectName("cast")
        if not theme.COMPACT:
            frame.setFixedWidth(theme.px(372))
        lay = vbox(frame, 8, 12)

        # Character on the left, voice actor on the right, facing each other.
        top = hbox(spacing=12)
        top.addWidget(Cover((char.get("image") or {}).get("medium", ""), char["name"]["full"], 56, 78, 8),
                      alignment=Qt.AlignTop)
        who = vbox(spacing=4)
        who.addWidget(label(char["name"]["full"], "cardTitle", wrap=True))
        main = e.get("role") == "MAIN"
        who.addWidget(badge("Main character" if main else "Supporting", "badge" if main else "chipLabel"),
                      alignment=Qt.AlignLeft)
        who.addStretch()
        top.addLayout(who, 1)
        top.addWidget(Cover((va.get("image") or {}).get("medium", ""), va["name"]["full"], 56, 78, 8),
                      alignment=Qt.AlignTop)
        lay.addLayout(top)

        line = QFrame()
        line.setObjectName("divider")
        lay.addWidget(line)

        name_row = hbox(spacing=8)
        name_row.addWidget(label(va["name"]["full"], "vaName", wrap=True), 1)
        fans = va.get("favourites") or 0
        if fans >= 5000 or (fans and fans == top_fans and fans >= 1500):
            name_row.addWidget(badge("Big name", "badgeAmber"), alignment=Qt.AlignTop)
        lay.addLayout(name_row)
        native = va["name"].get("native")
        lay.addWidget(label(f"{native}  ·  ★ {_fans(fans)} fans" if native else f"★ {_fans(fans)} fans",
                            "small", wrap=True))

        # Other roles, highlighting ones from shows on your list.
        lib = self.win.state.library
        own_id = self.anime.mal_id if self.anime else 0
        known, other = [], []
        for ce in (va.get("characterMedia") or {}).get("edges", []):
            node = ce.get("node") or {}
            if node.get("idMal") == own_id or not ce.get("characters"):
                continue
            role = f"{ce['characters'][0]['name']['full']} in {pick_title(node.get('title'))}"
            entry = lib.get(node.get("idMal"))
            (known if entry and entry.status in ("completed", "watching") else other).append(role)
        if known:
            lay.addWidget(label("You know them as " + "; ".join(known[:2]), "knownRole", wrap=True))
        if other:
            lay.addWidget(label("Also " + "; ".join(other[:2]), "small", wrap=True))
        lay.addStretch()
        return frame

    def _relations(self, d: dict) -> QFrame | None:
        edges = [e for e in (d.get("relations") or {}).get("edges", [])
                 if (e.get("node") or {}).get("type") == "ANIME"]
        if not edges:
            return None
        edges.sort(key=lambda e: RELATION_ORDER.index(e["relationType"])
                   if e["relationType"] in RELATION_ORDER else 99)
        frame, lay = card(margins=18, spacing=12)
        lay.addWidget(label("Related", "h2"))
        flow = FlowLayout(spacing=12)
        for e in edges[:12]:
            node = e["node"]
            flow.addWidget(self._mini(node.get("idMal"), pick_title(node.get("title")),
                                      (node.get("coverImage") or {}).get("large", ""),
                                      RELATION_LABELS.get(e["relationType"], e["relationType"].title())))
        host = QWidget()
        host.setLayout(flow)
        lay.addWidget(host)
        return frame

    def _recommendations(self, d: dict) -> QFrame | None:
        nodes = [n["mediaRecommendation"] for n in (d.get("recommendations") or {}).get("nodes", [])
                 if n.get("mediaRecommendation")]
        if not nodes:
            return None
        frame, lay = card(margins=18, spacing=12)
        lay.addWidget(label("If you like this", "h2"))
        flow = FlowLayout(spacing=12)
        for m in nodes:
            score = f"★ {m['averageScore'] / 10:.1f}" if m.get("averageScore") else ""
            flow.addWidget(self._mini(m.get("idMal"), pick_title(m.get("title")),
                                      (m.get("coverImage") or {}).get("large", ""), score))
        host = QWidget()
        host.setLayout(flow)
        lay.addWidget(host)
        return frame

    def _mini(self, mal_id: int | None, title: str, cover: str, caption: str) -> QWidget:
        entry = self.win.state.library.get(mal_id) if mal_id else None
        w = QFrame()
        w.setObjectName("mini")
        w.setFixedWidth(theme.px(124))
        lay = vbox(w, 5)
        lay.addWidget(Cover(cover or (entry.image_url if entry else ""), title, 124, 176, 10))
        if caption:
            lay.addWidget(label(caption, "faint"))
        t = label(entry.name if entry else title, "cardTitle", wrap=True)
        lay.addWidget(t)
        if entry:
            color = theme.STATUS_COLORS.get(entry.status, theme.MUTED)
            lay.addWidget(label(f"<span style='color:{color}'>●</span> {html.escape(STATUS_LABELS.get(entry.status, ''))}",
                                "small", rich=True))
            click = Clickable(w)
            click.clicked.connect(lambda e=entry: self.win.open_profile(e))
            w.setToolTip("Open its profile")
        elif mal_id:
            lay.addWidget(label("Not on your list", "faint"))
            click = Clickable(w)
            click.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(f"https://myanimelist.net/anime/{mal_id}")))
            w.setToolTip("Open on MyAnimeList")
        lay.addStretch()
        return w

    def _staff(self, d: dict) -> QFrame | None:
        edges = (d.get("staff") or {}).get("edges") or []
        if not edges:
            return None
        frame, lay = card(margins=18, spacing=10)
        lay.addWidget(label("Staff", "h2"))
        flow = vbox(spacing=8) if theme.COMPACT else FlowLayout(spacing=10)
        for e in edges[:8]:
            box, bl = card("episode", 8, 10, horizontal=True)
            if not theme.COMPACT:
                box.setFixedWidth(theme.px(290))
            node = e["node"]
            bl.addWidget(Cover((node.get("image") or {}).get("medium", ""), node["name"]["full"], 40, 56, 6))
            col = vbox(spacing=2)
            col.addWidget(label(node["name"]["full"], "cardTitle", wrap=True))
            col.addWidget(label(e.get("role", ""), "small", wrap=True))
            bl.addLayout(col, 1)
            flow.addWidget(box)
        host = QWidget()
        host.setLayout(flow)
        lay.addWidget(host)
        return frame
