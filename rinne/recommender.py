"""Decides what takes over when a show you're watching finishes.

1. **Follow the series.** Walk the sequel chain from the finished show: seasons you've
   already completed are skipped, an On-Hold season is resumed, and a sequel that isn't on
   your MAL list at all is still chosen (the app fetches and adds it). The chain stops at a
   season that hasn't aired yet, one you dropped, or one already in your rotation.

2. **Otherwise, pick from Plan to Watch.** Each candidate is scored from independent
   signals, each giving a human-readable reason:
     * franchise    — related to the finished show (side story, spin-off…)
     * prequels     — pushed down if you haven't finished its prequel
     * similarity   — genre overlap with the finished show
     * taste        — how you've scored completed shows in the same genres
     * quality      — MAL community mean score
     * priority     — the priority you set on MAL
     * variety      — avoid stacking the rotation with the same genres
     * fit          — mild preference for shorter shows
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from .models import (
    COMPLETED, CURRENTLY_AIRING, DROPPED, NOT_YET_AIRED, ON_HOLD, PLAN_TO_WATCH, WATCHING, Anime,
)

PREQUEL_KEYS = ("prequel",)
FAMILY_KEYS = ("parent_story", "side_story", "spin_off", "alternative_version", "full_story")

SERIES = "series"  # continuation of the finished show
PICK = "pick"  # chosen from Plan to Watch

Getter = Callable[[int], Anime | None]


@dataclass
class Suggestion:
    anime: Anime
    score: float
    kind: str = PICK
    # (points, text); points are 0 for series reasons, which aren't scored.
    reasons: list[tuple[float, str]] = field(default_factory=list)

    @property
    def headline(self) -> str:
        return self.reasons[0][1] if self.reasons else ""


# --------------------------------------------------------------------------- follow the series


EXTRA_FORMATS = {"MOVIE", "OVA", "SPECIAL", "MUSIC", "TV SHORT"}


def follow_series(finished: Anime, get: Getter, today: date,
                  include_extras: bool = True) -> tuple[Anime | None, list[str]]:
    """Return the next watchable entry in `finished`'s sequel chain, plus explanation lines.

    `get` returns the best-known Anime for an id (possibly fetching it) or None if unknown;
    an unknown sequel comes back as a placeholder built from the relation title.
    """
    node = get(finished.mal_id) or finished
    seen = {finished.mal_id}
    skipped: list[str] = []
    notes: list[str] = []
    for _ in range(10):
        ids = [i for i in node.relations.get("sequel", []) if i not in seen]
        if not ids:
            break
        sid = ids[0]
        seen.add(sid)
        cand = get(sid)
        if cand is None:
            title = node.relation_titles.get(str(sid)) or f"MAL #{sid}"
            placeholder = Anime(mal_id=sid, title=title, added_by_app=True)
            return placeholder, [f"Next in the series after {finished.name}",
                                 "Not on your MAL list yet — it will be added"]
        if cand.status == COMPLETED:
            skipped.append(cand.name)
            node = cand
            continue
        if not include_extras and cand.media_type.upper() in EXTRA_FORMATS:
            skipped.append(f"{cand.name} ({cand.media_type.title()})")
            node = cand
            continue
        if cand.status == DROPPED or cand.excluded:
            notes.append(f"You dropped the next season, {cand.name}")
            break
        if cand.status == WATCHING:
            notes.append(f"The next season, {cand.name}, is already in your rotation")
            break
        if cand.airing_status == NOT_YET_AIRED or cand.episodes_available(today) == 0:
            notes.append(f"The next season, {cand.name}, hasn't aired yet")
            break
        reasons = [f"Next in the series after {finished.name}"]
        if skipped:
            reasons.append("Skipped: " + ", ".join(skipped))
        if cand.status == ON_HOLD:
            reasons.append(f"Resumes from episode {cand.episodes_watched + 1} (was On Hold)")
        if cand.airing_status == CURRENTLY_AIRING:
            reasons.append("Currently airing — paced as episodes release")
        return cand, reasons
    return None, notes


# --------------------------------------------------------------------------- plan-to-watch ranking


def genre_affinity(library: dict[int, Anime]) -> dict[str, float]:
    """Per-genre deviation of your scores from your overall average score."""
    scored = [a for a in library.values() if a.status == COMPLETED and a.user_score and a.genres]
    if not scored:
        return {}
    overall = sum(a.user_score for a in scored) / len(scored)
    per_genre: dict[str, list[int]] = defaultdict(list)
    for a in scored:
        for g in a.genres:
            per_genre[g].append(a.user_score)
    # Shrink toward 0 for genres with few samples so one outlier doesn't dominate.
    return {
        g: (sum(s) / len(s) - overall) * len(s) / (len(s) + 2)
        for g, s in per_genre.items()
    }


def _prequels(a: Anime) -> list[int]:
    return [i for k in PREQUEL_KEYS for i in a.relations.get(k, [])]


def score_candidate(
    cand: Anime,
    finished: Anime | None,
    library: dict[int, Anime],
    active: list[Anime],
    affinity: dict[str, float],
    today: date,
) -> Suggestion | None:
    if cand.excluded or cand.status != PLAN_TO_WATCH:
        return None
    if cand.airing_status == NOT_YET_AIRED:
        return None
    available = cand.episodes_available(today)
    if cand.airing_status == CURRENTLY_AIRING and available is not None and available < 1:
        return None

    s = Suggestion(cand, 0.0)

    def add(points: float, reason: str) -> None:
        s.score += points
        if reason and abs(points) >= 0.5:
            s.reasons.append((points, reason))

    if finished is not None and cand.mal_id in [
            i for k in FAMILY_KEYS for i in finished.relations.get(k, [])]:
        add(25, f"Same franchise as {finished.name}")

    # The show being replaced counts as finished even if it's only about to be.
    done_id = finished.mal_id if finished is not None else None
    unwatched_prequels = [
        library[i] for i in _prequels(cand)
        if i in library and library[i].status != COMPLETED and i != done_id
    ]
    missing_prequels = [i for i in _prequels(cand) if i not in library]
    if unwatched_prequels:
        add(-80, f"Watch {unwatched_prequels[0].name} first")
    elif missing_prequels:
        add(-30, "Has a prequel that isn't on your list")
    elif _prequels(cand):
        add(15, "You've finished its prequel")

    if finished is not None and finished.genres and cand.genres:
        a, b = set(finished.genres), set(cand.genres)
        overlap = len(a & b) / len(a | b)
        if overlap:
            shared = ", ".join(sorted(a & b)[:3])
            add(overlap * 25, f"Like {finished.name}: {shared}")

    if affinity and cand.genres:
        vals = [affinity[g] for g in cand.genres if g in affinity]
        if vals:
            taste = sum(vals) / len(vals) * 8
            best = max(cand.genres, key=lambda g: affinity.get(g, -99))
            add(taste, f"You rate {best} highly" if taste > 0 else "Genres you usually rate lower")

    if cand.mean_score:
        add((cand.mean_score - 7.0) * 8, f"MAL score {cand.mean_score:.2f}")

    add({0: 0, 1: 6, 2: 15}.get(cand.priority, 0), "Marked as priority on MAL")

    others = [a for a in active if a is not finished and a.genres]
    if others and cand.genres:
        rotation = {g for a in others for g in a.genres}
        crowd = len(set(cand.genres) & rotation) / len(set(cand.genres))
        add(-crowd * 10, "Similar to what you're already watching" if crowd > 0.5 else "")
        if crowd <= 0.25:
            add(5, "Adds variety to your rotation")

    total = cand.episodes_total
    if total and total > 50:
        add(-min(20, (total - 50) / 10), f"Long commitment ({total} episodes)")
    elif total and total <= 13:
        add(3, "Short (≤13 episodes)")
    if cand.airing_status == CURRENTLY_AIRING:
        add(-5, "Still airing")

    return s


def rank(
    library: dict[int, Anime],
    finished: Anime | None = None,
    active: list[Anime] | None = None,
    today: date | None = None,
    exclude: set[int] | None = None,
) -> list[Suggestion]:
    today = today or date.today()
    active = active if active is not None else [a for a in library.values() if a.status == WATCHING]
    exclude = exclude or set()
    affinity = genre_affinity(library)
    out = []
    for cand in library.values():
        if cand.mal_id in exclude:
            continue
        sug = score_candidate(cand, finished, library, active, affinity, today)
        if sug:
            out.append(sug)
    out.sort(key=lambda s: (-s.score, s.anime.title))
    return out


# --------------------------------------------------------------------------- the decision


def pick_replacement(
    library: dict[int, Anime],
    finished: Anime,
    active: list[Anime],
    today: date | None = None,
    exclude: set[int] | None = None,
    get: Getter | None = None,
    include_extras: bool = True,
) -> Suggestion | None:
    """The series continuation if there is one, else the best Plan-to-Watch pick."""
    today = today or date.today()
    nxt, notes = follow_series(finished, get or library.get, today, include_extras)
    if nxt is not None:
        return Suggestion(nxt, 1000.0, SERIES, [(0.0, r) for r in notes])
    ranked = rank(library, finished, active, today, exclude)
    if not ranked:
        return None
    best = ranked[0]
    if not notes:
        known = (get or library.get)(finished.mal_id) or finished
        notes = [f"No further seasons after {finished.name}" if known.enriched
                 else f"Series info for {finished.name} isn't loaded yet — it's re-checked when it finishes"]
    best.reasons[:0] = [(0.0, n) for n in notes]
    return best
