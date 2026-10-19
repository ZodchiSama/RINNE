"""Builds a whole Watching list at once: "Build my Watching list".

Every show you could be watching (Watching, On Hold, Plan to Watch) is scored with the same
signals as a replacement pick (see recommender.py), plus:
  * momentum — shows you're already watching, and how far into them you are
  * resume   — On Hold shows you've started
  * season   — genres that fit the time of year (seasonal.py), when turned on

Shows are picked one at a time, so variety is judged against what's already been picked.
Airing shows are capped automatically (at most about 40%, since an airing show only gives an
episode or so a week), or get the number you choose.

Pinned shows always stay. Paused shows, and finished ones still marked Watching, are left
as they are and don't take a slot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from . import seasonal
from .i18n import _
from .models import COMPLETED, CURRENTLY_AIRING, ON_HOLD, PLAN_TO_WATCH, WATCHING, Anime
from .recommender import Suggestion, genre_affinity, score_candidate

AUTO = -1  # Settings.lineup_airing: share airing slots automatically
AUTO_AIRING_SHARE = 0.4
CANDIDATE_STATUSES = (WATCHING, ON_HOLD, PLAN_TO_WATCH)


@dataclass
class Lineup:
    picks: list[Suggestion] = field(default_factory=list)  # the new Watching list, best first
    start: list[Anime] = field(default_factory=list)  # picked, not on Watching now
    hold: list[Anime] = field(default_factory=list)  # on Watching now, moves to On Hold
    untouched: list[Anime] = field(default_factory=list)  # paused or finished: left alone
    airing_slots: int = 0
    mood: str = ""  # this month's mood name (untranslated) if seasonal picks were on

    @property
    def changes(self) -> int:
        return len(self.start) + len(self.hold)


def is_airing(a: Anime) -> bool:
    return a.airing_status == CURRENTLY_AIRING


def _finished(a: Anime) -> bool:
    return bool(a.episodes_total) and a.episodes_watched >= a.episodes_total


def _waits_on_prequel(a: Anime, library: dict[int, Anime]) -> bool:
    """An earlier season is on your list and not finished: season 2 never starts before season 1."""
    return any(i in library and library[i].status != COMPLETED for i in a.relations.get("prequel", []))


def airing_quota(size: int, airing: int) -> int:
    if airing == AUTO:
        return max(1, round(size * AUTO_AIRING_SHARE)) if size else 0
    return max(0, min(size, airing))


def _score(a: Anime, library: dict[int, Anime], picked: list[Anime],
           affinity: dict[str, float], today: date, season: bool) -> Suggestion | None:
    s = score_candidate(a, None, library, picked, affinity, today, CANDIDATE_STATUSES)
    if s is None:
        return None

    def add(points: float, reason: str) -> None:
        s.score += points
        if reason:
            s.reasons.append((points, reason))

    # A show you're partway through beats one you haven't started: momentum counts for a lot.
    if a.status == WATCHING:
        add(30, _("Already on your Watching list"))
        if a.episodes_watched:
            share = a.episodes_watched / a.episodes_total if a.episodes_total else 0.3
            add(25 + share * 15, _("Episode {watched} of {total}").format(
                watched=a.episodes_watched, total=a.episodes_total or "?"))
    elif a.status == ON_HOLD and a.episodes_watched:
        add(15, _("Pick up from episode {n}").format(n=a.episodes_watched + 1))
    if a.pinned:
        add(1000, _("Pinned"))
    if season:
        points, reason = seasonal.bonus(a.genres, today)
        if points:
            add(points, reason)
    s.reasons.sort(key=lambda r: -r[0])
    return s


def build(library: dict[int, Anime], size: int, airing: int = AUTO,
          season: bool = True, today: date | None = None,
          exclude: set[int] | None = None) -> Lineup:
    """Choose `size` shows for Watching. Nothing is changed until apply()."""
    today = today or date.today()
    out = Lineup(mood=seasonal.mood(today).name if season else "")
    pool: list[Anime] = []
    for a in library.values():
        if a.status == WATCHING and (a.paused or _finished(a)):
            out.untouched.append(a)
        elif (a.status in CANDIDATE_STATUSES and not a.excluded and not _finished(a)
              and (a.status == WATCHING or (a.mal_id not in (exclude or ())
                                            and not _waits_on_prequel(a, library)))):
            pool.append(a)
    pinned = [a for a in pool if a.status == WATCHING and a.pinned]
    size = max(size, len(pinned))
    quota = {True: airing_quota(size, airing)}
    quota[False] = size - quota[True]
    out.airing_slots = quota[True]

    affinity = genre_affinity(library)
    picked: list[Anime] = []
    left = {a.mal_id: a for a in pool}
    while len(picked) < size and left:
        scored = [s for a in left.values()
                  if (s := _score(a, library, picked, affinity, today, season)) is not None]
        if not scored:
            break
        open_kinds = {k for k, n in quota.items() if n > 0}
        if airing == AUTO:
            # Automatic: the best shows win; airing ones are only capped (they're slow to watch).
            fits = [s for s in scored if not is_airing(s.anime) or True in open_kinds] or scored
        else:
            # Your number is a target, not a must: a slot nothing good fits goes to the other kind
            # rather than to a show that scored badly.
            good = [s for s in scored if s.score > 0]
            fits = [s for s in good if is_airing(s.anime) in open_kinds] or good or scored
        best = max(fits, key=lambda s: (s.score, -s.anime.mal_id))
        kind = is_airing(best.anime)
        quota[kind] = max(0, quota[kind] - 1)
        picked.append(best.anime)
        out.picks.append(best)
        del left[best.anime.mal_id]

    chosen = {a.mal_id for a in picked}
    out.start = [a for a in picked if a.status != WATCHING]
    out.hold = sorted((a for a in pool if a.status == WATCHING and a.mal_id not in chosen),
                      key=lambda a: a.name.lower())
    return out


def apply(lineup: Lineup, today: date | None = None) -> None:
    """Move the shows: picks to Watching, the rest of Watching to On Hold."""
    today = today or date.today()
    for a in lineup.hold:
        a.status = ON_HOLD
        a.pinned = False
    for s in lineup.picks:
        a = s.anime
        if a.status == WATCHING:
            continue
        a.status = WATCHING
        a.started_on = today.isoformat()
        a.origin = {"date": today.isoformat(), "kind": "lineup",
                    "reasons": [t for p, t in s.reasons if p > 0][:4]}


def auto_split(size: int) -> tuple[int, int]:
    """(airing, backlog) slots the automatic split would use, for the settings hint."""
    airing = airing_quota(size, AUTO)
    return airing, size - airing
