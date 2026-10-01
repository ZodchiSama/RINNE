"""Announced and airing sequels of shows you've watched that aren't on your list yet."""

from __future__ import annotations

import time

from . import anilist
from .models import COMPLETED, ON_HOLD, WATCHING, Anime

QUERY = """query ($ids: [Int]) { Page(perPage: 50) { media(idMal_in: $ids, type: ANIME) {
  idMal status format season seasonYear startDate { year month day }
  nextAiringEpisode { episode airingAt } title { romaji english native } coverImage { large } } } }"""
LIVE = {"NOT_YET_RELEASED", "RELEASING"}


def sequel_candidates(library: dict[int, Anime]) -> dict[int, Anime]:
    """MAL id of each sequel that isn't on your list → the show it follows."""
    out: dict[int, Anime] = {}
    for a in library.values():
        if a.status not in (WATCHING, COMPLETED, ON_HOLD):
            continue
        for sid in a.relations.get("sequel", []):
            if sid not in library:
                out.setdefault(sid, a)
    return out


def check(library: dict[int, Anime]) -> list[dict]:
    """Sequels that are announced or airing: [{mal_id, node (AniList media), after (Anime)}].
    One request per 50 sequels; cached for a day."""
    cands = sequel_candidates(library)
    ids = sorted(cands)
    results = []
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        key = abs(hash(tuple(chunk))) % 10**9
        data = anilist._read_cache("announcements", key, 1)
        if data is None:
            data = anilist.query(QUERY, {"ids": chunk})
            anilist._write_cache("announcements", key, data)
            time.sleep(0.3)
        for m in (data.get("Page") or {}).get("media", []):
            if m.get("idMal") in cands and m.get("status") in LIVE:
                results.append({"mal_id": m["idMal"], "node": m, "after": cands[m["idMal"]]})
    results.sort(key=lambda r: (r["node"]["status"] != "RELEASING",
                                (r["node"].get("startDate") or {}).get("year") or 9999))
    return results


def premiered(results: list[dict], seen: dict[int, str]) -> list[dict]:
    """Entries that started airing since the last check (status changed to RELEASING)."""
    return [r for r in results if r["node"]["status"] == "RELEASING" and seen.get(r["mal_id"]) != "RELEASING"]
