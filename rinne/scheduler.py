"""Builds the weekly watch plan and applies progress when episodes are checked off.

Only shows on your Watching list are scheduled. When a show finishes, its replacement is
chosen (see recommender.py) and moved to Watching, and the rest of the week is replanned.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

from .models import (
    COMPLETED,
    CURRENTLY_AIRING,
    EPISODES,
    META_FIELDS,
    ON_HOLD,
    PLAN_TO_WATCH,
    WATCHING,
    Anime,
    ScheduleItem,
    WeekPlan,
)
from .recommender import Suggestion, pick_replacement
from .storage import State


def week_start_of(d: date) -> date:
    """The Sunday that starts d's week (weeks run Sunday–Saturday and restart at 00:00 Sunday)."""
    return d - timedelta(days=(d.weekday() + 1) % 7)


def _rotation_key(a: Anime) -> tuple:
    frac = a.episodes_watched / a.episodes_total if a.episodes_total else 0.0
    return (not a.pinned, -a.priority, -frac, a.started_on or "9999", a.title.lower())


def is_behind(show: Anime, on: date) -> bool:
    """An airing show with at least two aired episodes you haven't watched."""
    if show.airing_status != CURRENTLY_AIRING:
        return False
    available = show.episodes_available(on)
    return available is not None and available - show.episodes_watched >= 2


def current_rotation(library: dict[int, Anime], include_paused: bool = False) -> list[Anime]:
    """Every show on the Watching list (except paused ones), most-urgent first."""
    watching = [a for a in library.values()
                if a.status == WATCHING and not a.excluded and (include_paused or not a.paused)]
    watching.sort(key=_rotation_key)
    return watching


def excluded_airing(library: dict[int, Anime], allow_airing: bool) -> set[int]:
    if allow_airing:
        return set()
    return {a.mal_id for a in library.values() if a.airing_status == CURRENTLY_AIRING}


def preview_next(state: State, show: Anime, today: date | None = None) -> Suggestion | None:
    """What would replace `show` if it finished now (offline — nothing is fetched)."""
    rotation = current_rotation(state.library)
    return pick_replacement(state.library, show, rotation, today,
                            excluded_airing(state.library, state.settings.allow_airing),
                            include_extras=state.settings.follow_extras)


PLAN_DAYS = 7


def build_week(state: State, week_start: date, from_day: int = 0) -> WeekPlan:
    """(Re)plan the Sunday–Saturday week starting at `week_start`, from day offset `from_day`.

    Items on earlier days, and items already checked off, are kept: an unfinished earlier day
    waits to be finished, and its episodes aren't planned again. Progress is simulated on copies
    so the real library is untouched.
    """
    settings = state.settings
    by_episodes = settings.plan_by == EPISODES
    iso = week_start.isoformat()
    kept: list[ScheduleItem] = []
    if state.week and state.week.week_start == iso:
        kept = [i for i in state.week.items if i.day < from_day or i.done]

    sim = {k: copy.copy(a) for k, a in state.library.items()}
    for it in kept:  # episodes still waiting on an unfinished earlier day are spoken for
        a = sim.get(it.mal_id)
        if a is not None and not it.done and it.episode > a.episodes_watched:
            a.episodes_watched = it.episode
            if a.is_finished:
                a.status = COMPLETED
    rotation = current_rotation(sim)
    items: list[ScheduleItem] = []

    def cost(a: Anime) -> int:
        return 1 if by_episodes else a.minutes_per_episode

    catch_up = settings.catch_up_airing

    def add(show: Anime, day: int, on: date) -> None:
        show.episodes_watched += 1
        item = ScheduleItem(day, show.mal_id, show.episodes_watched)
        items.append(item)
        if show.is_finished:
            show.status = COMPLETED
            nxt = preview_next(state, state.library[show.mal_id], on)
            item.note = f"Finale — next up: {nxt.anime.name}" if nxt else "Finale"
            rotation.remove(show)

    def can_watch(show: Anime, on: date) -> bool:
        available = show.episodes_available(on)
        return available is None or show.episodes_watched < available

    rr = 0  # round-robin offset carried across days for fairness
    for day in range(from_day, PLAN_DAYS):
        on = week_start + timedelta(days=day)
        on_iso = on.isoformat()
        budget = settings.day_amount(on.weekday())
        per_show: dict[int, int] = {}
        for it in kept:
            if it.day == day and it.done:
                a = sim.get(it.mal_id)
                budget -= cost(a) if a else 0
                per_show[it.mal_id] = per_show.get(it.mal_id, 0) + 1
        scheduled_today = any(it.day == day for it in kept)

        # Manual moves: shows moved away sit this day out; shows moved here get their
        # episodes on top of the day's amount.
        away = {m["mal_id"] for m in state.moves if m.get("from") == on_iso}
        for m in state.moves:
            if m.get("to") != on_iso:
                continue
            show = next((r for r in rotation if r.mal_id == m["mal_id"]), None)
            for _ in range(max(1, int(m.get("count", 1)))):
                if show is None or show not in rotation or not can_watch(show, on):
                    break
                add(show, day, on)
                scheduled_today = True

        def cap(show: Anime, relaxed: bool) -> int:
            if show.pace:
                return show.pace
            if relaxed:
                return 10**6
            base = settings.max_eps_per_show_per_day
            return base + 1 if catch_up and is_behind(show, on) else base

        def turn_order() -> list[Anime]:
            """Pinned shows (and airing shows you're behind on) first, then the rest fairly."""
            first = [s for s in rotation if s.pinned or (catch_up and is_behind(s, on))]
            rest = [s for s in rotation if s not in first]
            if rest:
                k = rr % len(rest)
                rest = rest[k:] + rest[:k]
            return [s for s in first + rest if s.mal_id not in away]

        # Priority first: pinned shows get their daily episode, and airing shows you're behind
        # on fill their (raised) cap, before the rest share the day.
        for show in list(rotation):
            if show.mal_id in away or not (show.pinned or (catch_up and is_behind(show, on))):
                continue
            want = cap(show, False) if (catch_up and is_behind(show, on)) else 1
            while (budget > 0 and show in rotation and per_show.get(show.mal_id, 0) < want
                   and can_watch(show, on) and not (cost(show) > budget and scheduled_today)):
                add(show, day, on)
                budget -= cost(show)
                per_show[show.mal_id] = per_show.get(show.mal_id, 0) + 1
                scheduled_today = True

        # First pass respects the per-show daily cap; if the day still has room (e.g. you
        # asked for 6 episodes but watch only 2 shows), a second pass relaxes it.
        for relaxed in (False, True):
            progressed = True
            while progressed and budget > 0 and rotation:
                progressed = False
                for show in turn_order():
                    if show not in rotation or per_show.get(show.mal_id, 0) >= cap(show, relaxed):
                        continue
                    if not can_watch(show, on):
                        continue
                    c = cost(show)
                    if c > budget and scheduled_today:
                        continue  # doesn't fit; an oversized item only goes on an empty day
                    add(show, day, on)
                    budget -= c
                    per_show[show.mal_id] = per_show.get(show.mal_id, 0) + 1
                    scheduled_today = progressed = True
                    if budget <= 0:
                        break
                rr += 1

    return WeekPlan(iso, order_items(kept + items, state.library, week_start, state.day_order), calendar=True)


def episodes_left(anime: Anime | None) -> int:
    """Episodes still to watch; shows of unknown length count as very long."""
    if anime is None or not anime.episodes_total:
        return 10**6
    return max(0, anime.episodes_total - anime.episodes_watched)


def order_items(items: list[ScheduleItem], library: dict[int, Anime], week_start: date | None = None,
                day_order: dict[str, list[int]] | None = None) -> list[ScheduleItem]:
    """Within each day: an order you set by dragging wins; otherwise the show with the fewest
    episodes left first. A show's episodes always stay together, in order."""
    def manual(i: ScheduleItem) -> int:
        if not week_start or not day_order:
            return 0
        order = day_order.get((week_start + timedelta(days=i.day)).isoformat()) or []
        return order.index(i.mal_id) if i.mal_id in order else len(order)

    return sorted(items, key=lambda i: (i.day, manual(i), episodes_left(library.get(i.mal_id)),
                                        (library[i.mal_id].name.lower() if i.mal_id in library else ""),
                                        i.mal_id, i.episode))


def move_show(state: State, mal_id: int, from_date: date, to_date: date, today: date | None = None) -> None:
    """Move a show's episodes on one day to another day (kept across replans)."""
    week, start = state.week, plan_start(state)
    count = sum(1 for i in week.items if i.mal_id == mal_id and not i.done
                and start + timedelta(days=i.day) == from_date) if week and start else 1
    if from_date == to_date or count == 0:
        return
    state.moves.append({"mal_id": mal_id, "from": from_date.isoformat(), "to": to_date.isoformat(),
                        "count": count})
    replan(state, today)


def reorder_day(state: State, on: date, mal_ids: list[int], today: date | None = None) -> None:
    """Set the order of shows on one day."""
    state.day_order[on.isoformat()] = list(mal_ids)
    replan(state, today)


def prune_overrides(state: State, today: date | None = None) -> None:
    """Forget manual moves and orders for days that have passed."""
    today_iso = (today or date.today()).isoformat()
    state.moves = [m for m in state.moves if max(m.get("from", ""), m.get("to", "")) >= today_iso]
    state.day_order = {d: o for d, o in state.day_order.items() if d >= today_iso}


@dataclass
class ProgressEvent:
    finished: Anime | None = None
    replacement: Suggestion | None = None
    added: list[Anime] = field(default_factory=list)


def set_progress(state: State, anime: Anime, watched: int, today: date | None = None) -> ProgressEvent:
    """Update episodes watched and the list status. Doesn't pick a replacement."""
    today = today or date.today()
    event = ProgressEvent()
    watched = max(0, min(watched, anime.episodes_total) if anime.episodes_total else watched)
    from .stats import record
    record(state, anime, anime.episodes_watched, watched, today)
    anime.episodes_watched = watched

    if watched > 0 and anime.status in (PLAN_TO_WATCH, ON_HOLD):
        anime.status = WATCHING
        anime.started_on = anime.started_on or today.isoformat()
    if anime.is_finished and anime.status != COMPLETED:
        anime.status = COMPLETED
        anime.finished_on = today.isoformat()
        event.finished = anime
    elif not anime.is_finished and anime.status == COMPLETED:
        anime.status = WATCHING
        anime.finished_on = ""
    return event


Fetch = Callable[[int], Anime]


def find_replacement(
    state: State, finished: Anime, fetch: Fetch | None = None, today: date | None = None,
) -> tuple[Suggestion | None, dict[int, Anime]]:
    """Choose what replaces `finished`. Safe to run in a worker thread: the library is only
    read. Metadata fetched along the way is returned separately for `apply_replacement`."""
    today = today or date.today()
    fetched: dict[int, Anime] = {}

    def get(mal_id: int) -> Anime | None:
        if mal_id in fetched:
            return fetched[mal_id]
        known = state.library.get(mal_id)
        if fetch is None or (known is not None and known.enriched):
            return known
        try:
            fresh = fetch(mal_id)
        except Exception:
            return known
        if known is not None:  # keep the user's list entry, take the new metadata
            merged = copy.copy(known)
            for name in META_FIELDS:
                setattr(merged, name, getattr(fresh, name))
            if fresh.episodes_total:
                merged.episodes_total = fresh.episodes_total
            fresh = merged
        else:
            fresh.added_by_app = True
        fetched[mal_id] = fresh
        return fresh

    rotation = [a for a in current_rotation(state.library) if a.mal_id != finished.mal_id]
    excluded = excluded_airing(state.library, state.settings.allow_airing)
    sug = pick_replacement(state.library, finished, rotation, today, excluded, get,
                           include_extras=state.settings.follow_extras)
    return sug, fetched


def apply_replacement(
    state: State, sug: Suggestion, fetched: dict[int, Anime], today: date | None = None,
    finished: Anime | None = None,
) -> ProgressEvent:
    """Merge fetched metadata into the library and move the chosen show to Watching."""
    today = today or date.today()
    event = ProgressEvent(replacement=sug)
    for mal_id, fresh in fetched.items():
        known = state.library.get(mal_id)
        if known is None:
            state.library[mal_id] = fresh
            event.added.append(fresh)
        else:
            for name in META_FIELDS:
                setattr(known, name, getattr(fresh, name))
            if fresh.episodes_total:
                known.episodes_total = fresh.episodes_total
    chosen = state.library.get(sug.anime.mal_id)
    if chosen is None:  # placeholder for an unlisted sequel we couldn't fetch
        chosen = sug.anime
        state.library[chosen.mal_id] = chosen
        event.added.append(chosen)
    chosen.status = WATCHING
    chosen.started_on = today.isoformat()
    chosen.origin = {
        "date": today.isoformat(),
        "replaced": finished.name if finished else "",
        "replaced_id": finished.mal_id if finished else 0,
        "kind": sug.kind,
        "reasons": [text for points, text in sug.reasons if points >= 0][:5],
    }
    sug.anime = chosen
    return event


def toggle_item(state: State, item: ScheduleItem, today: date | None = None) -> ProgressEvent:
    """Check/uncheck a scheduled episode, update progress, and replan the rest of the week."""
    today = today or date.today()
    anime = state.library[item.mal_id]
    item.done = not item.done
    if item.done:
        event = set_progress(state, anime, max(anime.episodes_watched, item.episode), today)
    else:
        event = set_progress(state, anime, min(anime.episodes_watched, item.episode - 1), today)
    replan(state, today, keep_today=True)  # today's list stays put while you work through it
    return event


def plan_start(state: State) -> date | None:
    return date.fromisoformat(state.week.week_start) if state.week else None


def mark_watched_items(state: State) -> None:
    """Tick planned episodes you've already watched (on another day, in MAL/AniList, …)."""
    if state.week:
        for it in state.week.items:
            a = state.library.get(it.mal_id)
            if not it.done and a is not None and it.episode <= a.episodes_watched:
                it.done = True


def update_day_log(state: State) -> None:
    """Record each day of this week that's complete (and forget it again if it's unticked)."""
    week = state.week
    if not week or not week.calendar:
        return
    start = date.fromisoformat(week.week_start)
    for day in range(PLAN_DAYS):
        iso = (start + timedelta(days=day)).isoformat()
        if week.day_complete(day):
            state.day_log[iso] = "done"
        elif state.day_log.get(iso) == "done":
            del state.day_log[iso]


def roll_week(state: State, today: date | None = None) -> bool:
    """If a new week has begun, settle the old one: every day that had episodes counts as
    completed or, if anything was left unticked, failed. Returns True if a week ended."""
    today = today or date.today()
    week = state.week
    if not week or not week.calendar:
        return False
    start = date.fromisoformat(week.week_start)
    if week_start_of(today) <= start:
        return False
    for day in range(PLAN_DAYS):
        items = week.for_day(day)
        if items:
            iso = (start + timedelta(days=day)).isoformat()
            state.day_log[iso] = "done" if all(i.done for i in items) else "failed"
    return True


def replan(state: State, today: date | None = None, keep_today: bool = False) -> None:
    """Rebuild this week (Sunday–Saturday) from today onward. Earlier days keep their episodes,
    finished or not. When a new week starts, the old one is settled and a fresh week planned.
    `keep_today` leaves today's episodes as they are and replans only the days after it."""
    today = today or date.today()
    roll_week(state, today)
    prune_overrides(state, today)
    mark_watched_items(state)
    first = week_start_of(today)
    if not (state.week and state.week.calendar and state.week.week_start == first.isoformat()):
        state.week = None  # a new week, or a rolling plan from before 1.0
        keep_today = False
    state.week = build_week(state, first, (today - first).days + (1 if keep_today else 0))
    update_day_log(state)


def fresh_plan(state: State, today: date | None = None) -> None:
    """Replan the rest of the week from today (earlier days are kept)."""
    replan(state, today)


def plan_expired(state: State, today: date | None = None) -> bool:
    today = today or date.today()
    week = state.week
    return week is None or not week.calendar or week.week_start != week_start_of(today).isoformat()
