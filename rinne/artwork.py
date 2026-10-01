"""HD artwork (1920×1080 fan art and title logos) via the ani.zip mapping API.

ani.zip maps AniList/MAL ids to TheTVDB and returns its artwork: "Fanart" backgrounds are
full HD, far better for a full-window backdrop than AniList's ~1900×400 banners.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Iterable

from . import USER_AGENT
from .models import Anime
from .storage import cache_dir

API = "https://api.ani.zip/mappings"
MAX_AGE_DAYS = 30


def _cache_path(anilist_id: int, mal_id: int):
    key = f"al{anilist_id}" if anilist_id else f"mal{mal_id}"
    return cache_dir() / "artwork" / f"{key}.json"


def fetch(anilist_id: int = 0, mal_id: int = 0, max_age_days: float = MAX_AGE_DAYS) -> dict:
    """{"fanart", "logo", "banner": url, "episodes": {"1": {...}}}; empty when unavailable.

    Episodes come from TheTVDB via ani.zip: title (en/ja/x-jat), screenshot, air date, overview.
    """
    if anilist_id:
        query = f"anilist_id={anilist_id}"
    elif mal_id:
        query = f"mal_id={mal_id}"
    else:
        return {}
    path = _cache_path(anilist_id, mal_id)
    try:
        if time.time() - path.stat().st_mtime < max_age_days * 86400:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if "episodes" in cached:  # files from before episode data are refetched once
                return cached
    except (OSError, json.JSONDecodeError):
        pass
    req = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code != 404:
            return {}  # transient; try again next time
        data = {}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return {}
    art = {"fanart": "", "logo": "", "banner": ""}
    for img in data.get("images") or []:
        kind = {"Fanart": "fanart", "Clearlogo": "logo", "Banner": "banner"}.get(img.get("coverType"))
        if kind and not art[kind] and img.get("url"):
            art[kind] = img["url"]
    art["episodes"] = {
        str(num): {
            "title": {k: v for k, v in (ep.get("title") or {}).items() if k in ("en", "ja", "x-jat") and v},
            "image": ep.get("image") or "",
            "airdate": ep.get("airdate") or "",
            "overview": (ep.get("overview") or "")[:600],
            "runtime": ep.get("runtime") or ep.get("length") or 0,
        }
        for num, ep in (data.get("episodes") or {}).items()
        if str(num).isdigit()
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(art), encoding="utf-8")
    return art


def fetch_many(entries: Iterable[Anime]) -> dict[int, dict]:
    """Artwork for several shows, keyed by MAL id. Safe to run in a worker thread.
    Airing shows are refreshed after 2 days so new episode titles show up."""
    out = {}
    for a in entries:
        out[a.mal_id] = fetch(a.anilist_id, a.mal_id, 2 if a.airing_status == "currently_airing" else MAX_AGE_DAYS)
    return out


def episodes(anime: Anime) -> dict[str, dict]:
    """Cached episode details for a show (no network): {"9": {"title": {...}, "image": ...}}."""
    try:
        data = json.loads(_cache_path(anime.anilist_id, anime.mal_id).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data.get("episodes") or {}


def episode_title(ep: dict, language: str) -> str:
    """The episode title in the chosen language (romaji/english/native), falling back sensibly."""
    titles = ep.get("title") or {}
    order = {"english": ("en", "x-jat", "ja"), "native": ("ja", "en", "x-jat")}.get(language, ("x-jat", "en", "ja"))
    for key in order:
        if titles.get(key):
            return titles[key]
    return ""


def apply(anime: Anime, art: dict) -> None:
    anime.fanart_url = art.get("fanart", "") if art else ""
    anime.logo_url = art.get("logo", "") if art else ""
    anime.artwork_checked = bool(art)
