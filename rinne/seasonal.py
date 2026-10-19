"""What fits the time of year you're watching in, not the season a show aired.

Each month has a mood: a name and the genres (and AniList tags) that suit it. October is
Halloween, so horror and the supernatural rise to the top; December is cosy and festive;
summer favours sports and adventure. The lineup builder gives matching shows a bonus.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .i18n import N_, _


@dataclass(frozen=True)
class Mood:
    name: str  # untranslated (N_); show with _()
    genres: frozenset[str]


_WINTER = frozenset({"Slice of Life", "Romance", "Drama", "Iyashikei", "Comedy"})
_SPRING = frozenset({"Romance", "Slice of Life", "School", "Coming of Age", "Music", "Comedy"})
_SUMMER = frozenset({"Sports", "Adventure", "Comedy", "Beach", "Fantasy", "Isekai"})
_AUTUMN = frozenset({"Mystery", "Drama", "Psychological", "Suspense", "Thriller", "Detective"})
_HALLOWEEN = frozenset({
    "Horror", "Supernatural", "Mystery", "Thriller", "Psychological", "Suspense",
    "Ghost", "Vampire", "Zombie", "Gore", "Body Horror", "Youkai", "Yokai", "Witch",
    "Survival", "Monster Girl",
})
_FESTIVE = frozenset({"Slice of Life", "Romance", "Comedy", "Christmas", "Iyashikei", "Family Life"})

MOODS: dict[int, Mood] = {
    1: Mood(N_("Winter"), _WINTER),
    2: Mood(N_("Winter"), _WINTER | {"Romance"}),
    3: Mood(N_("Spring"), _SPRING),
    4: Mood(N_("Spring"), _SPRING),
    5: Mood(N_("Spring"), _SPRING),
    6: Mood(N_("Summer"), _SUMMER),
    7: Mood(N_("Summer"), _SUMMER),
    8: Mood(N_("Summer"), _SUMMER),
    9: Mood(N_("Autumn"), _AUTUMN),
    10: Mood(N_("Halloween"), _HALLOWEEN),
    11: Mood(N_("Autumn"), _AUTUMN),
    12: Mood(N_("Winter holidays"), _FESTIVE),
}


def mood(today: date | None = None) -> Mood:
    return MOODS[(today or date.today()).month]


def matches(genres: list[str], today: date | None = None) -> list[str]:
    """The show's genres that fit this month's mood, in the show's own order."""
    m = mood(today)
    return [g for g in genres if g in m.genres]


def bonus(genres: list[str], today: date | None = None) -> tuple[float, str]:
    """Points (0–14) and a reason for how well a show fits the time of year."""
    hits = matches(genres, today)
    if not hits:
        return 0.0, ""
    points = min(1.0, len(hits) / 2) * 14
    return points, _("Fits the season ({mood}): {genres}").format(
        mood=_(mood(today).name), genres=", ".join(hits[:3]))
