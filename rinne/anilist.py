"""AniList GraphQL client — the primary metadata source.

AniList is keyless, reliable, and can look up 50 shows per request by their MAL id. It also
provides the three title variants, cover/banner art, accurate airing progress, and the cast
data used by the show profile.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from datetime import date, datetime

from . import USER_AGENT
from .models import (
    CURRENTLY_AIRING, FINISHED_AIRING, META_VERSION, NOT_YET_AIRED, Anime,
)
from .storage import cache_dir

API = "https://graphql.anilist.co"
BATCH = 50

MEDIA_FIELDS = """
  id idMal title { romaji english native } format episodes duration status averageScore genres
  tags { name rank isMediaSpoiler } startDate { year month day }
  nextAiringEpisode { episode airingAt } coverImage { extraLarge large color } bannerImage
  externalLinks { site url type }
  relations { edges { relationType node { id idMal type format status title { romaji english native }
    coverImage { large } } } }
"""

BATCH_QUERY = """query ($ids: [Int], $page: Int) {
  Page(page: $page, perPage: 50) { media(idMal_in: $ids, type: ANIME) { %s } }
}""" % MEDIA_FIELDS

PROFILE_QUERY = """query ($id: Int) { Media(idMal: $id, type: ANIME) {
  %s
  siteUrl description format season seasonYear source popularity favourites
  studios(isMain: true) { nodes { name } }
  rankings { rank type allTime context year season }
  staff(sort: [RELEVANCE], perPage: 8) { edges { role node { name { full native } image { medium } } } }
  characters(sort: [ROLE, RELEVANCE], perPage: 12) { edges { role node { name { full native } image { medium } }
    voiceActors(language: JAPANESE, sort: [RELEVANCE]) { id name { full native } image { medium } favourites
      characterMedia(sort: [POPULARITY_DESC], perPage: 6) { edges { characterRole
        node { idMal title { romaji english native } } characters { name { full } } } } } } }
  recommendations(sort: [RATING_DESC], perPage: 8) { nodes { mediaRecommendation {
    idMal title { romaji english native } coverImage { large } averageScore } } }
} }""" % MEDIA_FIELDS

_STATUS = {
    "FINISHED": FINISHED_AIRING,
    "CANCELLED": FINISHED_AIRING,
    "RELEASING": CURRENTLY_AIRING,
    "HIATUS": CURRENTLY_AIRING,
    "NOT_YET_RELEASED": NOT_YET_AIRED,
}
_RELATION = {
    "SEQUEL": "sequel", "PREQUEL": "prequel", "SIDE_STORY": "side_story", "PARENT": "parent_story",
    "SPIN_OFF": "spin_off", "ALTERNATIVE": "alternative_version", "SUMMARY": "summary",
    "COMPILATION": "summary", "OTHER": "other", "CHARACTER": "character",
}


class AniListError(Exception):
    pass


_last_call = 0.0


def query(q: str, variables: dict, retries: int = 3, token: str = "") -> dict:
    global _last_call
    body = json.dumps({"query": q, "variables": variables}).encode()
    for attempt in range(retries):
        gap = time.monotonic() - _last_call
        if gap < 0.7:  # stay well inside the rate limit
            time.sleep(0.7 - gap)
        _last_call = time.monotonic()
        headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": USER_AGENT}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(API, data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("errors") and not data.get("data"):
                raise AniListError(data["errors"][0].get("message", "AniList error"))
            return data["data"]
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(min(60, int(e.headers.get("Retry-After", "5") or 5)))
                continue
            if e.code == 404:
                return {}
            if e.code >= 500 and attempt < retries - 1:
                time.sleep(1 + attempt)
                continue
            raise AniListError(f"HTTP {e.code} from AniList") from e
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                time.sleep(1 + attempt)
                continue
            raise AniListError(f"Network error: {e.reason}") from e
    raise AniListError("AniList request failed")


# --------------------------------------------------------------------------- caching


def _cache_path(kind: str, mal_id: int):
    return cache_dir() / kind / f"{mal_id}.json"


def _read_cache(kind: str, mal_id: int, max_age_days: float) -> dict | None:
    path = _cache_path(kind, mal_id)
    try:
        if time.time() - path.stat().st_mtime < max_age_days * 86400:
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _write_cache(kind: str, mal_id: int, data: dict) -> None:
    path = _cache_path(kind, mal_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _max_age(anime: Anime) -> float:
    # Airing shows change week to week; finished ones can be cached for a long time.
    return 60 if anime.airing_status == FINISHED_AIRING else 2


# --------------------------------------------------------------------------- applying data


def _iso_date(d: dict | None) -> str:
    if not d or not d.get("year"):
        return ""
    return date(d["year"], d.get("month") or 1, d.get("day") or 1).isoformat()


def apply_media(anime: Anime, m: dict) -> None:
    t = m.get("title") or {}
    anime.title_romaji = t.get("romaji") or ""
    anime.title_english = t.get("english") or ""
    anime.title_native = t.get("native") or ""
    if not anime.title or anime.title.startswith("#") or anime.title.startswith("MAL #"):
        anime.title = anime.title_romaji or anime.title
    anime.anilist_id = m.get("id") or 0
    if m.get("format"):
        anime.media_type = m["format"].replace("_", " ")
    if m.get("averageScore"):
        anime.mean_score = m["averageScore"] / 10
    tags = [x["name"] for x in m.get("tags") or []
            if x.get("rank", 0) >= 75 and not x.get("isMediaSpoiler")][:3]
    anime.genres = list(m.get("genres") or []) + tags
    anime.episode_minutes = m.get("duration") or anime.episode_minutes
    if m.get("episodes"):
        anime.episodes_total = m["episodes"]
    anime.airing_status = _STATUS.get(m.get("status") or "", anime.airing_status)
    anime.aired_from = _iso_date(m.get("startDate")) or anime.aired_from
    nxt = m.get("nextAiringEpisode")
    if nxt:
        when = datetime.fromtimestamp(nxt["airingAt"])  # local time
        anime.next_episode = nxt["episode"]
        anime.next_airing = when.isoformat(timespec="minutes")
        anime.broadcast_day = when.weekday()
    else:
        anime.next_episode, anime.next_airing = 0, ""
    cover = m.get("coverImage") or {}
    anime.image_url = cover.get("extraLarge") or cover.get("large") or anime.image_url
    anime.cover_color = cover.get("color") or ""
    anime.banner_url = m.get("bannerImage") or ""
    rel: dict[str, list[int]] = {}
    titles: dict[str, str] = {}
    for e in (m.get("relations") or {}).get("edges", []):
        node = e.get("node") or {}
        key = _RELATION.get(e.get("relationType") or "")
        if not key or node.get("type") != "ANIME" or not node.get("idMal"):
            continue
        rel.setdefault(key, []).append(node["idMal"])
        titles[str(node["idMal"])] = (node.get("title") or {}).get("romaji") or ""
    anime.relations = rel
    anime.relation_titles = titles
    anime.streaming = [{"site": x["site"], "url": x["url"]} for x in m.get("externalLinks") or []
                       if x.get("type") == "STREAMING" and x.get("url")]
    anime.meta_version = META_VERSION
    anime.enriched = True


# --------------------------------------------------------------------------- public API


def enrich(
    entries: Iterable[Anime],
    progress: Callable[[int, int, str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    force: bool = False,
) -> list[Anime]:
    """Enrich entries in batches. Returns the entries AniList couldn't provide."""
    todo = [a for a in entries if force or a.needs_enrichment]
    missing: list[Anime] = []
    pending: list[Anime] = []
    for a in todo:
        cached = None if force else _read_cache("anilist", a.mal_id, _max_age(a))
        if cached is not None and "externalLinks" not in cached:
            cached = None  # cached before streaming links were fetched
        if cached:
            apply_media(a, cached)
        else:
            pending.append(a)
    for start in range(0, len(pending), BATCH):
        if should_stop and should_stop():
            missing.extend(pending[start:])
            break
        chunk = pending[start:start + BATCH]
        if progress:
            progress(start, len(pending), f"Fetching details from AniList ({start}/{len(pending)})…")
        try:
            data = query(BATCH_QUERY, {"ids": [a.mal_id for a in chunk], "page": 1})
        except AniListError:
            missing.extend(chunk)
            continue
        by_id = {m["idMal"]: m for m in (data.get("Page") or {}).get("media", []) if m.get("idMal")}
        for a in chunk:
            m = by_id.get(a.mal_id)
            if m:
                _write_cache("anilist", a.mal_id, m)
                apply_media(a, m)
            else:
                missing.append(a)
    return missing


def lookup(mal_id: int) -> Anime | None:
    """Fetch one show by MAL id (e.g. a sequel that isn't on the user's list)."""
    m = _read_cache("anilist", mal_id, 2)
    if m is None:
        data = query(BATCH_QUERY, {"ids": [mal_id], "page": 1})
        media = [x for x in (data.get("Page") or {}).get("media", []) if x.get("idMal") == mal_id]
        if not media:
            return None
        m = media[0]
        _write_cache("anilist", mal_id, m)
    anime = Anime(mal_id=mal_id, title=(m.get("title") or {}).get("romaji") or f"#{mal_id}")
    apply_media(anime, m)
    return anime


LIST_QUERY = """query ($name: String) { MediaListCollection(userName: $name, type: ANIME) {
  lists { entries { status progress score(format: POINT_10) priority media { %s } } } } }""" % MEDIA_FIELDS

_LIST_STATUS = {"CURRENT": "watching", "REPEATING": "watching", "COMPLETED": "completed",
                "PAUSED": "on_hold", "DROPPED": "dropped", "PLANNING": "plan_to_watch"}


def fetch_user_list(username: str, progress=None) -> tuple[list[Anime], int]:
    """A public AniList list by username, with full show details.
    Returns (entries, skipped) — entries without a MyAnimeList id can't be tracked and are skipped."""
    from .mal import ImportError_
    if progress:
        progress(0, 0, f"Fetching {username}'s AniList list…")
    try:
        data = query(LIST_QUERY, {"name": username.strip()})
    except AniListError as e:
        msg = str(e)
        if "Private" in msg:
            raise ImportError_(f"{username}'s AniList list is private. Make it public in AniList's "
                               "settings, or connect your AniList account in Rinne.") from e
        if "not found" in msg.lower() or "404" in msg:
            raise ImportError_(f"There's no AniList user called “{username}”.") from e
        raise ImportError_(msg) from e
    entries, skipped, seen = [], 0, set()
    for lst in (data.get("MediaListCollection") or {}).get("lists") or []:
        for e in lst.get("entries") or []:
            m = e.get("media") or {}
            if not m.get("idMal"):
                skipped += 1
                continue
            if m["idMal"] in seen:  # custom lists repeat entries
                continue
            seen.add(m["idMal"])
            a = Anime(mal_id=m["idMal"], title=(m.get("title") or {}).get("romaji") or f"#{m['idMal']}")
            apply_media(a, m)
            _write_cache("anilist", a.mal_id, m)
            a.status = _LIST_STATUS.get(e.get("status") or "", "plan_to_watch")
            a.episodes_watched = int(e.get("progress") or 0)
            if a.status == "completed" and a.episodes_total:
                a.episodes_watched = a.episodes_total
            a.user_score = int(e.get("score") or 0)
            a.priority = min(2, int(e.get("priority") or 0))
            entries.append(a)
    return entries, skipped


UPCOMING_NODE = """id idMal type format status title { romaji english native } season seasonYear
  startDate { year month day } nextAiringEpisode { episode airingAt } coverImage { large }"""
CHAIN_QUERY = """query ($id: Int) { Media(id: $id) { %s
  relations { edges { relationType node { %s } } } } }""" % (UPCOMING_NODE, UPCOMING_NODE)

# Relations worth announcing as "coming up" (not e.g. recaps or cameo appearances).
UPCOMING_RELATIONS = {"SEQUEL", "PREQUEL", "SIDE_STORY", "PARENT", "SPIN_OFF", "ALTERNATIVE", "OTHER"}
LIVE = {"NOT_YET_RELEASED", "RELEASING"}


def _chain_media(anilist_id: int) -> dict:
    cached = _read_cache("anilist_chain", anilist_id, 1)
    if cached is not None:
        return cached
    data = query(CHAIN_QUERY, {"id": anilist_id}).get("Media") or {}
    if data:
        _write_cache("anilist_chain", anilist_id, data)
    return data


def upcoming(anilist_id: int, max_hops: int = 8) -> list[dict]:
    """Announced or airing entries in this show's franchise, found by walking the sequel chain.

    Each result: {node: <AniList media>, relation: "SEQUEL", via: <title dict or None>}.
    The show itself is included (relation "SELF") if it's still airing or unreleased.
    """
    found: dict[int, dict] = {}
    seen: set[int] = set()
    media = _chain_media(anilist_id)
    if not media:
        return []
    if media.get("status") in LIVE:
        found[media["id"]] = {"node": media, "relation": "SELF", "via": None}
    via = None
    for _ in range(max_hops):
        seen.add(media["id"])
        sequels = []
        for e in (media.get("relations") or {}).get("edges", []):
            node, rel = e.get("node") or {}, e.get("relationType")
            if node.get("type") != "ANIME" or node.get("id") in seen:
                continue
            if node.get("status") in LIVE and rel in UPCOMING_RELATIONS and node["id"] not in found:
                found[node["id"]] = {"node": node, "relation": rel, "via": via}
            if rel == "SEQUEL":
                sequels.append(node)
        # Keep walking through finished sequels (S2 done → maybe S3 is announced).
        nxt = next((n for n in sequels if n.get("status") not in LIVE), None)
        if nxt is None:
            break
        via = nxt.get("title")
        media = _chain_media(nxt["id"])
        if not media:
            break

    def sort_key(entry: dict):
        node = entry["node"]
        d = node.get("startDate") or {}
        return (entry["relation"] != "SELF", d.get("year") or node.get("seasonYear") or 9999,
                d.get("month") or 13, d.get("day") or 32)

    return sorted(found.values(), key=sort_key)


def profile(mal_id: int) -> dict:
    """Full profile data (synopsis, cast, staff, recommendations) for the show page."""
    cached = _read_cache("anilist_profile", mal_id, 7)
    if cached is not None:
        return cached
    data = query(PROFILE_QUERY, {"id": mal_id}).get("Media") or {}
    if data:
        _write_cache("anilist_profile", mal_id, data)
    return data
