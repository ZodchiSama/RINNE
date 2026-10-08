"""Plain-language explanations of why a show is on your list and in your plan."""

from __future__ import annotations

from datetime import date, timedelta

from . import scheduler
from .i18n import _, _n, weekday_name
from .models import (
    COMPLETED, CURRENTLY_AIRING, DROPPED, ON_HOLD, PLAN_TO_WATCH, WATCHING, Anime,
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
    return _("{h}h {m:02d}m").format(h=h, m=m) if h else _("{m} min").format(m=m)


def why(state: State, anime: Anime, today: date | None = None) -> list[str]:
    """Reasons, most important first."""
    today = today or date.today()
    out: list[str] = []
    o = anime.origin or {}

    if anime.status == WATCHING:
        if o.get("replaced"):
            how = (_("it's the next season") if o.get("kind") == SERIES
                   else _("it was the best pick from your Plan to Watch list"))
            out.append(_("Took over from {replaced} on {value} — {how}").format(replaced=o['replaced'], value=_fmt_date(o.get('date', '')), how=how))
        elif o.get("kind") == "manual":
            out.append(_("You started it from Up Next on {value}").format(value=_fmt_date(o.get('date', ''))))
        elif anime.added_by_app:
            out.append(_("Added by the app as the next season of a show you finished"))
        else:
            out.append(_("It's on your Watching list on MyAnimeList"))
        out.extend(r for r in o.get("reasons", []) if not r.startswith("Next in the series"))
        out.extend(_schedule_lines(state, anime, today))
        nxt = scheduler.preview_next(state, anime, today)
        if nxt is not None:
            out.append(_("When it ends, {name} takes over ({value}{value2})").format(name=nxt.anime.name, value=nxt.headline[:1].lower(), value2=nxt.headline[1:]))
    elif anime.status == PLAN_TO_WATCH:
        out.append(_("It's on your Plan to Watch list — it isn't scheduled until it takes over from "
                   "a finished show or you start it"))
        rotation = scheduler.current_rotation(state.library)
        excluded = scheduler.excluded_airing(state.library, state.settings.allow_airing)
        ranked = rank(state.library, None, rotation, today, excluded)
        pos = next((n for n, s in enumerate(ranked, 1) if s.anime is anime), None)
        if anime.excluded:
            out.append(_("You marked it “never suggest”"))
        elif pos is not None:
            out.append(_("Ranked #{pos} of {n} Plan to Watch picks").format(pos=pos, n=len(ranked)))
            out.extend(text for points, text in ranked[pos - 1].reasons if points > 0)
    elif anime.status == COMPLETED:
        when = f" on {_fmt_date(anime.finished_on)}" if anime.finished_on else ""
        out.append(_("You completed it{when}").format(when=when))
        if anime.user_score:
            out.append(_("You scored it {user_score}/10").format(user_score=anime.user_score))
    elif anime.status == ON_HOLD:
        out.append(_("On hold at episode {episodes_watched} — the app resumes it if the season before it finishes").format(episodes_watched=anime.episodes_watched))
    elif anime.status == DROPPED:
        out.append(_("You dropped it, so it's never scheduled or suggested"))
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
            when = _("today") if on == today else (_("tomorrow") if on == today + timedelta(days=1)
                                                   else weekday_name(on.weekday()))
            out.append(_n("{n} episode planned this week — next is episode {ep}, {when}",
                          "{n} episodes planned this week — next is episode {ep}, {when}",
                          len(mine), ep=first.episode, when=when))
        elif mine:
            out.append(_("All of this week's planned episodes are watched"))
        else:
            out.append(_("Nothing planned this week — no new episodes available or no room in "
                       "your days"))
    if anime.episodes_total:
        left = anime.episodes_total - anime.episodes_watched
        if left > 0:
            out.append(_n("{n} episode left (about {time})", "{n} episodes left (about {time})", left,
                          time=_hours(left * anime.minutes_per_episode)))
    if anime.airing_status == CURRENTLY_AIRING:
        if anime.next_episode and anime.next_airing:
            out.append(_("Still airing — episode {next_episode} airs {value}, then weekly").format(next_episode=anime.next_episode, value=_fmt_date(anime.next_airing)))
        else:
            out.append(_("Still airing — scheduled as episodes come out"))
    if anime.priority >= 2:
        out.append(_("High priority on MAL, so it gets the first episodes each day"))
    return out
