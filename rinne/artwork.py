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


def fetch(anilist_id: int = 0, mal_id: int = 0) -> dict:
    """{"fanart": url, "logo": url, "banner": url}; empty strings when unavailable."""
    if anilist_id:
        key, query = f"al{anilist_id}", f"anilist_id={anilist_id}"
    elif mal_id:
        key, query = f"mal{mal_id}", f"mal_id={mal_id}"
    else:
        return {}
    path = cache_dir() / "artwork" / f"{key}.json"
    try:
        if time.time() - path.stat().st_mtime < MAX_AGE_DAYS * 86400:
            return json.loads(path.read_text(encoding="utf-8"))
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(art), encoding="utf-8")
    return art


def fetch_many(entries: Iterable[Anime]) -> dict[int, dict]:
    """Artwork for several shows, keyed by MAL id. Safe to run in a worker thread."""
    out = {}
    for a in entries:
        out[a.mal_id] = fetch(a.anilist_id, a.mal_id)
    return out


def apply(anime: Anime, art: dict) -> None:
    anime.fanart_url = art.get("fanart", "") if art else ""
    anime.logo_url = art.get("logo", "") if art else ""
    anime.artwork_checked = bool(art)
