"""Shikimori (shikimori.io): importing a list by nickname, and Russian titles.

Shikimori's anime ids are MyAnimeList ids, so its entries map straight onto the library, and
Russian titles can be looked up for any library, not only one imported from Shikimori.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable

from . import USER_AGENT
from .mal import ImportError_
from .models import (
    COMPLETED, CURRENTLY_AIRING, DROPPED, FINISHED_AIRING, NOT_YET_AIRED, ON_HOLD, PLAN_TO_WATCH, WATCHING,
    Anime,
)
from .storage import cache_dir

API = "https://shikimori.io/api"
PAGE = 5000  # list entries per request; a page with one extra entry means there are more
BATCH = 50  # anime per request when looking up titles

STATUS = {"planned": PLAN_TO_WATCH, "watching": WATCHING, "rewatching": WATCHING,
          "completed": COMPLETED, "on_hold": ON_HOLD, "dropped": DROPPED}
_KIND = {"tv": "TV", "movie": "MOVIE", "ova": "OVA", "ona": "ONA", "special": "SPECIAL",
         "tv_special": "TV_SPECIAL", "music": "MUSIC"}
_AIRING = {"released": FINISHED_AIRING, "ongoing": CURRENTLY_AIRING, "anons": NOT_YET_AIRED}

_last_call = 0.0


def _get(path: str, params: dict, retries: int = 3):
    """GET from the API. Shikimori asks for at most 5 requests a second and a User-Agent naming
    the app; 429s are retried after the delay it asks for."""
    global _last_call
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    for attempt in range(retries):
        gap = time.monotonic() - _last_call
        if gap < 0.25:
            time.sleep(0.25 - gap)
        _last_call = time.monotonic()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(min(10, int(e.headers.get("Retry-After") or 2)))
                continue
            raise
    raise ImportError_("Shikimori is busy right now. Try again in a minute.")


def fetch_user_list(nickname: str, progress=None) -> list[Anime]:
    """A user's anime list. Russian titles come along (title_ru)."""
    nickname = nickname.strip()
    if progress:
        progress(0, 0, f"Fetching {nickname}'s Shikimori list…")
    rates, page = [], 1
    while True:
        try:
            batch = _get(f"users/{urllib.parse.quote(nickname)}/anime_rates", {"limit": PAGE, "page": page})
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise ImportError_(f"There's no Shikimori user called “{nickname}”.") from e
            if e.code == 403:
                raise ImportError_(f"{nickname}'s Shikimori list is private. Make it public in "
                                   "Shikimori's settings to import it.") from e
            raise ImportError_(f"Shikimori answered with an error ({e.code}). Try again later.") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise ImportError_(f"Couldn't reach Shikimori: {getattr(e, 'reason', e)}") from e
        rates += batch[:PAGE]
        if progress:
            progress(len(rates), 0, f"Fetched {len(rates)} entries…")
        if len(batch) <= PAGE:
            break
        page += 1

    entries, seen = [], set()
    for r in rates:
        a = r.get("anime") or {}
        if not a.get("id") or a["id"] in seen:
            continue
        seen.add(a["id"])
        entries.append(Anime(
            mal_id=a["id"],
            title=a.get("name") or f"#{a['id']}",
            title_ru=a.get("russian") or "",
            status=STATUS.get(r.get("status"), PLAN_TO_WATCH),
            episodes_watched=int(r.get("episodes") or 0),
            episodes_total=int(a.get("episodes") or 0),
            user_score=int(r.get("score") or 0),
            media_type=_KIND.get(a.get("kind") or "", (a.get("kind") or "").upper()),
            airing_status=_AIRING.get(a.get("status") or "", ""),
            aired_from=a.get("aired_on") or "",
        ))
    if progress:
        progress(len(entries), len(entries), f"{len(entries)} shows from Shikimori")
    return entries


# --------------------------------------------------------------------------- Russian titles


def _cache_file():
    return cache_dir() / "shikimori_ru.json"


def _load_cache() -> dict[str, str]:
    try:
        return json.loads(_cache_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def cached_title(mal_id: int | None) -> str:
    """A Russian title already fetched (no network)."""
    if not mal_id:
        return ""
    return _load_cache().get(str(mal_id), "")


def russian_titles(mal_ids: Iterable[int], progress=None) -> dict[int, str]:
    """Russian titles for these MyAnimeList ids, from the cache or Shikimori (50 per request).
    Ids Shikimori doesn't know get "" and aren't asked for again."""
    cache = _load_cache()
    ids = sorted({int(i) for i in mal_ids if i})
    todo = [i for i in ids if str(i) not in cache]
    for n in range(0, len(todo), BATCH):
        chunk = todo[n:n + BATCH]
        if progress:
            progress(n, len(todo), "Fetching Russian titles from Shikimori…")
        try:
            found = _get("animes", {"ids": ",".join(map(str, chunk)), "limit": BATCH})
        except (urllib.error.URLError, TimeoutError, ConnectionError, ImportError_):
            break  # offline or busy: keep what we have, try the rest next time
        for a in found:
            cache[str(a["id"])] = a.get("russian") or ""
        for i in chunk:
            cache.setdefault(str(i), "")
        _cache_file().parent.mkdir(parents=True, exist_ok=True)
        _cache_file().write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return {i: cache.get(str(i), "") for i in ids}


def apply_russian(library: dict[int, Anime], titles: dict[int, str]) -> int:
    """Store fetched Russian titles on the library's shows. Returns how many changed."""
    changed = 0
    for mal_id, title in titles.items():
        a = library.get(mal_id)
        if a is not None and title and a.title_ru != title:
            a.title_ru = title
            changed += 1
    return changed
