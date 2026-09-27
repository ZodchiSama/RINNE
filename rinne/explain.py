"""Plain-language explanations of why a show is on your list and in your plan."""

from __future__ import annotations

from datetime import date, timedelta

from . import scheduler
from .models import (
    COMPLETED, CURRENTLY_AIRING, DROPPED, ON_HOLD, PLAN_TO_WATCH, WATCHING, WEEKDAYS, Anime,
)
from .recommender import SERIES, rank
from .storage import State


def _fmt_date(iso: str) -> str:
    try:
        return f"{date.fromisoformat(iso[:10]):%d %b %Y}"
    except ValueError:
        return iso


def _hours(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h}h {m:02d}m" if h else f"{m} min"


def why(state: State, anime: Anime, today: date | None = None) -> list[str]:
    """Reasons, most important first."""
    today = today or date.today()
    out: list[str] = []
    o = anime.origin or {}

    if anime.status == WATCHING:
        if o.get("replaced"):
            how = ("it's the next season" if o.get("kind") == SERIES
                   else "it was the best pick from your Plan to Watch list")
            out.append(f"Took over from {o['replaced']} on {_fmt_date(o.get('date', ''))} — {how}")
        elif o.get("kind") == "manual":
            out.append(f"You started it from Up Next on {_fmt_date(o.get('date', ''))}")
        elif anime.added_by_app:
            out.append("Added by the app as the next season of a show you finished")
        else:
            out.append("It's on your Watching list on MyAnimeList")
        out.extend(r for r in o.get("reasons", []) if not r.startswith("Next in the series"))
        out.extend(_schedule_lines(state, anime, today))
        nxt = scheduler.preview_next(state, anime, today)
        if nxt is not None:
            out.append(f"When it ends, {nxt.anime.name} takes over ({nxt.headline[:1].lower()}"
                       f"{nxt.headline[1:]})")
    elif anime.status == PLAN_TO_WATCH:
        out.append("It's on your Plan to Watch list — it isn't scheduled until it takes over from "
                   "a finished show or you start it")
        rotation = scheduler.current_rotation(state.library)
        excluded = scheduler.excluded_airing(state.library, state.settings.allow_airing)
        ranked = rank(state.library, None, rotation, today, excluded)
        pos = next((n for n, s in enumerate(ranked, 1) if s.anime is anime), None)
        if anime.excluded:
            out.append("You marked it “never suggest”")
        elif pos is not None:
            out.append(f"Ranked #{pos} of {len(ranked)} Plan to Watch picks")
            out.extend(text for points, text in ranked[pos - 1].reasons if points > 0)
    elif anime.status == COMPLETED:
        when = f" on {_fmt_date(anime.finished_on)}" if anime.finished_on else ""
        out.append(f"You completed it{when}")
        if anime.user_score:
            out.append(f"You scored it {anime.user_score}/10")
    elif anime.status == ON_HOLD:
        out.append(f"On hold at episode {anime.episodes_watched} — the app resumes it if the "
                   "season before it finishes")
    elif anime.status == DROPPED:
        out.append("You dropped it, so it's never scheduled or suggested")
    return out


def _schedule_lines(state: State, anime: Anime, today: date) -> list[str]:
    out: list[str] = []
    week = state.week
    start = scheduler.plan_start(state)
    if week and start:
        mine = [i for i in week.items if i.mal_id == anime.mal_id]
        todo = [i for i in mine if not i.done and start + timedelta(days=i.day) >= today]
        if todo:
            first = todo[0]
            on = start + timedelta(days=first.day)
            when = "today" if on == today else ("tomorrow" if on == today + timedelta(days=1)
                                                else WEEKDAYS[on.weekday()])
            out.append(f"{len(mine)} episode{'s' if len(mine) != 1 else ''} planned this week — "
                       f"next is episode {first.episode}, {when}")
        elif mine:
            out.append("All of this week's planned episodes are watched")
        else:
            out.append("Nothing planned this week — no new episodes available or no room in "
                       "your days")
    if anime.episodes_total:
        left = anime.episodes_total - anime.episodes_watched
        if left > 0:
            out.append(f"{left} episode{'s' if left != 1 else ''} left "
                       f"(about {_hours(left * anime.minutes_per_episode)})")
    if anime.airing_status == CURRENTLY_AIRING:
        if anime.next_episode and anime.next_airing:
            out.append(f"Still airing — episode {anime.next_episode} airs "
                       f"{_fmt_date(anime.next_airing)}, then weekly")
        else:
            out.append("Still airing — scheduled as episodes come out")
    if anime.priority >= 2:
        out.append("High priority on MAL, so it gets the first episodes each day")
    return out
