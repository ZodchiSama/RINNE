"""Watch history and the numbers on the Stats page."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

from .i18n import _, _n
from .models import COMPLETED, DROPPED, WATCHING, Anime
from .storage import State


def record(state: State, anime: Anime, old: int, new: int, today: date | None = None) -> None:
    """Keep the watch history in step with a progress change (tick, untick or edit)."""
    today = today or date.today()
    if new > old:
        for ep in range(old + 1, new + 1):
            state.history.append({"d": today.isoformat(), "m": anime.mal_id, "e": ep,
                                  "min": anime.minutes_per_episode})
    elif new < old:
        state.history = [h for h in state.history if not (h["m"] == anime.mal_id and h["e"] > new)]


@dataclass
class Stats:
    week_episodes: int = 0
    week_minutes: int = 0
    streak: int = 0  # consecutive days up to today (or yesterday) with at least one episode
    best_streak: int = 0
    weekly: list[tuple[date, int]] = field(default_factory=list)  # week's Sunday → episodes, last 12 weeks
    daily: list[tuple[date, int]] = field(default_factory=list)  # last 30 days
    genres: list[tuple[str, int]] = field(default_factory=list)  # top genres by episodes watched
    total_episodes: int = 0
    total_minutes: int = 0
    completed: int = 0
    dropped: int = 0
    watching: int = 0
    finished_this_week: list[str] = field(default_factory=list)
    recent: list[dict] = field(default_factory=list)  # latest history entries, newest first
    # Daily goals: a day is complete when everything planned for it is ticked, and failed if the
    # week ended (00:00 Sunday) with something left.
    days_done: int = 0
    days_failed: int = 0
    goal_streak: int = 0  # completed days in a row (days with nothing planned don't count)
    best_goal_streak: int = 0
    # Last 8 weeks, oldest first: (Sunday, 7 states) with states done / failed / open / none / future
    goal_weeks: list[tuple[date, list[str]]] = field(default_factory=list)

    @property
    def goal_rate(self) -> float | None:
        settled = self.days_done + self.days_failed
        return self.days_done / settled if settled else None

    @property
    def completion_rate(self) -> float | None:
        done = self.completed + self.dropped
        return self.completed / done if done else None


def compute(state: State, today: date | None = None) -> Stats:
    today = today or date.today()
    s = Stats()
    per_day: Counter = Counter()
    minutes_per_day: Counter = Counter()
    for h in state.history:
        try:
            d = date.fromisoformat(h["d"])
        except (KeyError, ValueError):
            continue
        per_day[d] += 1
        minutes_per_day[d] += int(h.get("min") or 0)

    week_start = today - timedelta(days=6)
    s.week_episodes = sum(n for d, n in per_day.items() if week_start <= d <= today)
    s.week_minutes = sum(n for d, n in minutes_per_day.items() if week_start <= d <= today)

    # Streaks
    day = today if per_day.get(today) else today - timedelta(days=1)
    while per_day.get(day):
        s.streak += 1
        day -= timedelta(days=1)
    run, prev = 0, None
    for d in sorted(per_day):
        run = run + 1 if prev is not None and d - prev == timedelta(days=1) else 1
        s.best_streak = max(s.best_streak, run)
        prev = d

    first = today - timedelta(days=(today.weekday() + 1) % 7)  # weeks start on Sunday
    for k in range(11, -1, -1):
        start = first - timedelta(weeks=k)
        s.weekly.append((start, sum(per_day.get(start + timedelta(days=i), 0) for i in range(7))))
    s.daily = [(today - timedelta(days=k), per_day.get(today - timedelta(days=k), 0)) for k in range(29, -1, -1)]

    genre_eps: Counter = Counter()
    for a in state.library.values():
        s.total_episodes += a.episodes_watched
        s.total_minutes += a.episodes_watched * a.minutes_per_episode
        if a.status == COMPLETED:
            s.completed += 1
            if a.finished_on and a.finished_on >= week_start.isoformat():
                s.finished_this_week.append(a.name)
        elif a.status == DROPPED:
            s.dropped += 1
        elif a.status == WATCHING:
            s.watching += 1
        for g in a.genres:
            genre_eps[g] += a.episodes_watched
    s.genres = [(g, n) for g, n in genre_eps.most_common(8) if n]
    s.recent = list(reversed(state.history[-12:]))
    _goals(s, state, today, first)
    return s


def _goals(s: Stats, state: State, today: date, first: date) -> None:
    log = state.day_log
    s.days_done = sum(1 for v in log.values() if v == "done")
    s.days_failed = sum(1 for v in log.values() if v == "failed")
    run = 0
    for iso in sorted(log):
        run = run + 1 if log[iso] == "done" else 0
        s.best_goal_streak = max(s.best_goal_streak, run)
    s.goal_streak = run
    week = state.week
    week_start = date.fromisoformat(week.week_start) if week and week.calendar else None
    for k in range(7, -1, -1):
        start = first - timedelta(weeks=k)
        states = []
        for d in range(7):
            on = start + timedelta(days=d)
            if log.get(on.isoformat()) in ("done", "failed"):
                states.append(log[on.isoformat()])
            elif on > today:
                states.append("future")
            elif week_start == start and week.for_day(d):
                states.append("open")  # this week, not finished yet: it can still be
            else:
                states.append("none")
        s.goal_weeks.append((start, states))


def recap_text(s: Stats) -> str:
    hours, mins = divmod(s.week_minutes, 60)
    parts = [_n("{n} episode this week", "{n} episodes this week", s.week_episodes)
             + (" (" + _("{hours}h {mins:02d}m").format(hours=hours, mins=mins) + ")" if s.week_minutes else "")]
    if s.finished_this_week:
        parts.append("finished " + ", ".join(s.finished_this_week[:3]))
    if s.streak >= 2:
        parts.append(_n("{n}-day streak", "{n}-day streak", s.streak))
    return " · ".join(parts)
