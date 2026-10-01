"""Importing from MyAnimeList and enriching entries with metadata.

Two import paths:
  * a MAL list export (Profile -> Export -> Anime List), .xml or .xml.gz — no account setup needed
  * the MAL API v2 by username — needs a free Client ID from https://myanimelist.net/apiconfig

Enrichment (genres, relations, airing info) uses the MAL API when a Client ID is set,
otherwise the public Jikan API. Responses are cached on disk.
"""

from __future__ import annotations

import gzip
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from pathlib import Path

from . import USER_AGENT
from .models import (
    COMPLETED,
    CURRENTLY_AIRING,
    DROPPED,
    FINISHED_AIRING,
    NOT_YET_AIRED,
    ON_HOLD,
    PLAN_TO_WATCH,
    WATCHING,
    WEEKDAYS,
    Anime,
)
from .storage import cache_dir

MAL_API = "https://api.myanimelist.net/v2"
JIKAN_API = "https://api.jikan.moe/v4"

XML_STATUS = {
    "watching": WATCHING,
    "completed": COMPLETED,
    "on-hold": ON_HOLD,
    "dropped": DROPPED,
    "plan to watch": PLAN_TO_WATCH,
    # Numeric codes appear in some older exports.
    "1": WATCHING,
    "2": COMPLETED,
    "3": ON_HOLD,
    "4": DROPPED,
    "6": PLAN_TO_WATCH,
}
XML_PRIORITY = {"low": 0, "medium": 1, "high": 2}

Progress = Callable[[int, int, str], None]


class ImportError_(Exception):
    """Raised when an import cannot be completed (bad file, network, auth)."""


def _text(el: ET.Element, tag: str, default: str = "") -> str:
    child = el.find(tag)
    return (child.text or default).strip() if child is not None and child.text else default


def _int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- XML export


def parse_mal_export(path: str | Path) -> list[Anime]:
    return parse_mal_export_bytes(Path(path).read_bytes())


def parse_mal_export_bytes(raw: bytes) -> list[Anime]:
    """Parse a MAL export (.xml or .xml.gz) already read into memory."""
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        raise ImportError_(f"Not a valid MAL export: {e}") from e
    entries = []
    for el in root.iter("anime"):
        mal_id = _int(_text(el, "series_animedb_id"))
        if not mal_id:
            continue
        status = XML_STATUS.get(_text(el, "my_status").lower(), PLAN_TO_WATCH)
        entries.append(
            Anime(
                mal_id=mal_id,
                title=_text(el, "series_title", f"#{mal_id}"),
                status=status,
                episodes_total=_int(_text(el, "series_episodes")),
                episodes_watched=_int(_text(el, "my_watched_episodes")),
                user_score=_int(_text(el, "my_score")),
                priority=XML_PRIORITY.get(_text(el, "my_priority").lower(), 0),
                media_type=_text(el, "series_type"),
            )
        )
    if not entries and root.tag != "myanimelist":
        raise ImportError_("File does not look like a MyAnimeList export.")
    return entries


# --------------------------------------------------------------------------- HTTP


def _get_json(url: str, headers: dict[str, str] | None = None, retries: int = 3) -> dict:
    # Ask for gzip: besides being smaller, Jikan only serves its cache to compressed
    # requests, which keeps working when MAL itself is slow or down.
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip", **(headers or {})})
    delay = 1.0
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return json.loads(body.decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            if e.code in (401, 403):
                raise ImportError_("MAL rejected the request — check your Client ID.") from e
            if e.code == 404:
                raise ImportError_("Not found (user list private or does not exist?).") from e
            raise ImportError_(f"HTTP {e.code} from {urllib.parse.urlparse(url).netloc}") from e
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise ImportError_(f"Network error: {e.reason}") from e
    raise ImportError_("Request failed")


# --------------------------------------------------------------------------- MAL API


LIST_FIELDS = (
    "list_status,num_episodes,genres,mean,status,average_episode_duration,"
    "broadcast,media_type,start_date,main_picture,alternative_titles"
)


def _apply_mal_node(anime: Anime, node: dict) -> None:
    anime.mean_score = float(node.get("mean") or 0.0)
    anime.genres = [g["name"] for g in node.get("genres", [])]
    if node.get("average_episode_duration"):
        anime.episode_minutes = max(1, round(node["average_episode_duration"] / 60))
    anime.airing_status = node.get("status", anime.airing_status)
    day = (node.get("broadcast") or {}).get("day_of_the_week", "")
    anime.broadcast_day = _weekday_index(day)
    anime.aired_from = node.get("start_date", anime.aired_from) or ""
    alt = node.get("alternative_titles") or {}
    anime.title_english = alt.get("en") or anime.title_english
    anime.title_native = alt.get("ja") or anime.title_native
    pic = node.get("main_picture") or {}
    anime.image_url = pic.get("large") or pic.get("medium") or anime.image_url
    if node.get("num_episodes"):
        anime.episodes_total = node["num_episodes"]
    if "related_anime" in node:
        rel: dict[str, list[int]] = {}
        titles: dict[str, str] = {}
        for r in node["related_anime"]:
            rel.setdefault(r["relation_type"], []).append(r["node"]["id"])
            titles[str(r["node"]["id"])] = r["node"].get("title", "")
        anime.relations = rel
        anime.relation_titles = titles
        anime.enriched = True


def fetch_mal_list(username: str, client_id: str, progress: Progress | None = None,
                   token: str = "") -> list[Anime]:
    """A user's list. With a signed-in `token`, `username` can be "@me" (private lists work too)."""
    if not client_id and not token:
        raise ImportError_("A MAL Client ID is required for username import.")
    headers = {"Authorization": f"Bearer {token}"} if token else {"X-MAL-CLIENT-ID": client_id}
    url = (
        f"{MAL_API}/users/{urllib.parse.quote(username)}/animelist"
        f"?fields={LIST_FIELDS}&limit=1000&nsfw=true"
    )
    entries: list[Anime] = []
    while url:
        data = _get_json(url, headers)
        for item in data.get("data", []):
            node, ls = item["node"], item.get("list_status", {})
            anime = Anime(
                mal_id=node["id"],
                title=node.get("title", f"#{node['id']}"),
                status=ls.get("status", PLAN_TO_WATCH),
                episodes_watched=ls.get("num_episodes_watched", 0),
                user_score=ls.get("score", 0),
                priority=ls.get("priority", 0),
                media_type=(node.get("media_type") or "").upper(),
            )
            _apply_mal_node(anime, node)
            entries.append(anime)
        if progress:
            progress(len(entries), 0, f"Fetched {len(entries)} entries…")
        url = data.get("paging", {}).get("next")
    return entries


# --------------------------------------------------------------------------- Jikan


_JIKAN_STATUS = {
    "finished airing": FINISHED_AIRING,
    "currently airing": CURRENTLY_AIRING,
    "not yet aired": NOT_YET_AIRED,
}


def _weekday_index(name: str | None) -> int | None:
    if not name:
        return None
    name = name.lower().rstrip("s")
    for i, day in enumerate(WEEKDAYS):
        if day.lower() == name:
            return i
    return None


def _parse_duration(text: str) -> int:
    hours = re.search(r"(\d+)\s*hr", text or "")
    mins = re.search(r"(\d+)\s*min", text or "")
    total = (int(hours.group(1)) * 60 if hours else 0) + (int(mins.group(1)) if mins else 0)
    return total


def _relation_key(name: str) -> str:
    return re.sub(r"[^a-z]+", "_", name.lower()).strip("_")


def _apply_jikan(anime: Anime, d: dict) -> None:
    anime.mean_score = float(d.get("score") or anime.mean_score or 0.0)
    names = [g["name"] for key in ("genres", "themes", "demographics") for g in d.get(key) or []]
    anime.genres = names or anime.genres
    anime.episode_minutes = _parse_duration(d.get("duration", "")) or anime.episode_minutes
    anime.airing_status = _JIKAN_STATUS.get((d.get("status") or "").lower(), anime.airing_status)
    anime.broadcast_day = _weekday_index((d.get("broadcast") or {}).get("day"))
    anime.aired_from = ((d.get("aired") or {}).get("from") or "")[:10]
    if d.get("episodes"):
        anime.episodes_total = d["episodes"]
    jpg = (d.get("images") or {}).get("jpg") or {}
    anime.image_url = jpg.get("large_image_url") or jpg.get("image_url") or anime.image_url
    anime.title_romaji = anime.title_romaji or d.get("title") or ""
    anime.title_english = d.get("title_english") or anime.title_english
    anime.title_native = d.get("title_japanese") or anime.title_native
    rel: dict[str, list[int]] = {}
    titles: dict[str, str] = {}
    for r in d.get("relations") or []:
        entries = [e for e in r.get("entry", []) if e.get("type") == "anime"]
        if entries:
            rel.setdefault(_relation_key(r["relation"]), []).extend(e["mal_id"] for e in entries)
            titles.update({str(e["mal_id"]): e.get("name", "") for e in entries})
    anime.relations = rel
    anime.relation_titles = titles
    anime.enriched = True


class _Throttle:
    def __init__(self, interval: float):
        self.interval = interval
        self._last = 0.0

    def wait(self) -> None:
        gap = time.monotonic() - self._last
        if gap < self.interval:
            time.sleep(self.interval - gap)
        self._last = time.monotonic()


def _cached(kind: str, mal_id: int, fetch: Callable[[], dict], max_age_days: float) -> dict:
    path = cache_dir() / kind / f"{mal_id}.json"
    if path.exists() and time.time() - path.stat().st_mtime < max_age_days * 86400:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    data = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


DETAIL_FIELDS = LIST_FIELDS.replace("list_status,", "") + ",related_anime"


def enrich(
    entries: Iterable[Anime],
    client_id: str = "",
    progress: Progress | None = None,
    should_stop: Callable[[], bool] | None = None,
    force: bool = False,
) -> int:
    """Fill metadata for entries that lack it: AniList first (50 per request), then MAL/Jikan
    for anything AniList doesn't have. Returns how many entries now have metadata."""
    from . import anilist

    entries = list(entries)
    todo = [a for a in entries if force or a.needs_enrichment]
    missing = anilist.enrich(todo, progress, should_stop, force)
    return len(todo) - len(missing) + _enrich_fallback(missing, client_id, progress, should_stop)


def _enrich_fallback(
    entries: Iterable[Anime],
    client_id: str = "",
    progress: Progress | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> int:
    todo = [a for a in entries if a.needs_enrichment]
    throttle = _Throttle(0.35 if client_id else 1.1)  # Jikan allows ~60 req/min
    done = 0
    for n, anime in enumerate(todo, 1):
        if should_stop and should_stop():
            break
        if progress:
            progress(n, len(todo), f"Looking up {anime.title}")
        # Airing shows change week to week; finished ones can be cached for a long time.
        max_age = 3 if anime.airing_status in ("", CURRENTLY_AIRING, NOT_YET_AIRED) else 60
        try:
            if client_id:
                url = f"{MAL_API}/anime/{anime.mal_id}?fields={DETAIL_FIELDS}"

                def fetch(url=url):
                    throttle.wait()
                    return _get_json(url, {"X-MAL-CLIENT-ID": client_id})

                _apply_mal_node(anime, _cached("mal", anime.mal_id, fetch, max_age))
            else:
                url = f"{JIKAN_API}/anime/{anime.mal_id}/full"

                def fetch(url=url):
                    throttle.wait()
                    return _get_json(url)["data"]

                _apply_jikan(anime, _cached("jikan", anime.mal_id, fetch, max_age))
            done += 1
        except ImportError_:
            continue  # leave un-enriched; the scheduler copes with missing metadata
    return done


def lookup(mal_id: int, client_id: str = "") -> Anime:
    """Fetch one anime's metadata (e.g. a sequel that isn't on the user's list).

    Returns a fresh Anime with default list fields; raises ImportError_ on failure.
    """
    from . import anilist

    try:
        found = anilist.lookup(mal_id)
        if found is not None:
            return found
    except anilist.AniListError:
        pass
    anime = Anime(mal_id=mal_id, title=f"#{mal_id}")
    if client_id:
        url = f"{MAL_API}/anime/{mal_id}?fields={DETAIL_FIELDS}"
        data = _cached("mal", mal_id, lambda: _get_json(url, {"X-MAL-CLIENT-ID": client_id}), 3)
        anime.title = data.get("title", anime.title)
        anime.media_type = (data.get("media_type") or "").upper()
        _apply_mal_node(anime, data)
    else:
        url = f"{JIKAN_API}/anime/{mal_id}/full"
        data = _cached("jikan", mal_id, lambda: _get_json(url)["data"], 3)
        anime.title = data.get("title", anime.title)
        anime.media_type = data.get("type") or ""
        _apply_jikan(anime, data)
    return anime


# --------------------------------------------------------------------------- merge


LIST_FIELDS_OWNED_BY_MAL = ("title", "user_score", "priority", "media_type")
_PROGRESSION = {PLAN_TO_WATCH: 0, WATCHING: 1, COMPLETED: 2}


def merge_import(library: dict[int, Anime], imported: list[Anime]) -> tuple[int, int]:
    """Merge imported entries into the library. Returns (added, updated).

    Progress tracked locally is never rolled back by an older MAL list; an explicit
    On-Hold/Dropped on MAL always wins.
    """
    added = updated = 0
    for new in imported:
        old = library.get(new.mal_id)
        if old is None:
            library[new.mal_id] = new
            added += 1
            continue
        for name in LIST_FIELDS_OWNED_BY_MAL:
            setattr(old, name, getattr(new, name))
        old.episodes_watched = max(old.episodes_watched, new.episodes_watched)
        if new.status in (ON_HOLD, DROPPED) or old.status in (ON_HOLD, DROPPED):
            old.status = new.status
        elif _PROGRESSION.get(new.status, 0) > _PROGRESSION.get(old.status, 0):
            old.status = new.status
        if new.episodes_total:
            old.episodes_total = new.episodes_total
        if new.genres:  # API import carries metadata; keep relations from enrichment
            for name in ("mean_score", "genres", "episode_minutes", "airing_status",
                         "broadcast_day", "aired_from", "image_url"):
                setattr(old, name, getattr(new, name))
        updated += 1
    return added, updated
