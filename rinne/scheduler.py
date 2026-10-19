"""Builds the weekly watch plan and applies progress when episodes are checked off.

Only shows on your Watching list are scheduled. When a show finishes, its replacement is
chosen (see recommender.py) and moved to Watching, and the rest of the week is replanned.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

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


def build_week(state: State, week_start: date, from_day: int = 0, keep_day: int | None = None) -> WeekPlan:
    """(Re)plan the Sunday–Saturday week starting at `week_start`, from day offset `from_day`.

    Items on earlier days, and items already checked off, are kept: an unfinished earlier day
    waits to be finished, and its episodes aren't planned again. Progress is simulated on copies
    so the real library is untouched. On `keep_day` (today), episodes already planned stay put
    as long as their show is still being watched; only room they leave is filled again.
    """
    settings = state.settings
    by_episodes = settings.plan_by == EPISODES
    iso = week_start.isoformat()
    kept: list[ScheduleItem] = []
    if state.week and state.week.week_start == iso:
        kept = [i for i in state.week.items if i.day < from_day or i.done]
        if keep_day is not None:
            def still_wanted(i: ScheduleItem) -> bool:
                a = state.library.get(i.mal_id)
                return (a is not None and a.status == WATCHING and not a.paused
                        and i.episode > a.episodes_watched)
            kept += [i for i in state.week.items if i.day == keep_day and not i.done and still_wanted(i)]
    if state.overtime:
        # Last week's overtime episodes belong to overtime only: a copy in this week (planned by
        # Experimental Build v1.1.5.3–5) is dropped, so ticking one never ticks "next Monday" too.
        ot_keys = {(i.mal_id, i.episode) for i in state.overtime.items}
        kept = [i for i in kept if (i.mal_id, i.episode) not in ot_keys]

    sim = {k: copy.copy(a) for k, a in state.library.items()}
    # Episodes still waiting on an unfinished earlier day, or in last week's overtime, are spoken
    # for: the new week comes after them. When overtime ends, unwatched ones are planned again.
    for it in kept + (state.overtime.items if state.overtime else []):
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

    # An episode ticked early on a later day: the show's next episodes go on that day or after,
    # never before it (which would put episode 37 ahead of a watched 36).
    floor: dict[int, int] = {}
    for it in kept:
        if it.done and it.day >= from_day:
            floor[it.mal_id] = max(floor.get(it.mal_id, 0), it.day)

    def can_watch(show: Anime, on: date) -> bool:
        if (on - week_start).days < floor.get(show.mal_id, 0):
            return False
        available = show.episodes_available(on)
        return available is None or show.episodes_watched < available

    rr = 0  # round-robin offset carried across days for fairness
    for day in range(from_day, PLAN_DAYS):
        on = week_start + timedelta(days=day)
        on_iso = on.isoformat()
        budget = settings.day_amount(on.weekday())
        per_show: dict[int, int] = {}
        for it in kept:
            if it.day == day:  # ticked already, or kept on today: it takes its share of the day
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
    replan(state, today, rebuild_today=True)


def reorder_day(state: State, on: date, mal_ids: list[int], today: date | None = None) -> None:
    """Set the order of shows on one day."""
    state.day_order[on.isoformat()] = list(mal_ids)
    replan(state, today, rebuild_today=True)


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
    """Check/uncheck a scheduled episode and update progress. The plan itself stays as it is: a tick
    must not reshuffle other days. (Finishing a show replans, once its replacement is chosen.)"""
    today = today or date.today()
    anime = state.library[item.mal_id]
    item.done = not item.done
    if item.done:
        event = set_progress(state, anime, max(anime.episodes_watched, item.episode), today)
    else:
        event = set_progress(state, anime, min(anime.episodes_watched, item.episode - 1), today)
    mark_watched_items(state)  # earlier episodes of the show, if you skipped ahead
    update_day_log(state)
    settle_overtime(state, _now(today, None))  # a day finished in overtime is saved
    return event


def _day_iso(state: State, day: int) -> str:
    return (date.fromisoformat(state.week.week_start) + timedelta(days=day)).isoformat()


def day_failed(state: State, day: int) -> bool:
    """The day was given up: its episodes were rescheduled (or the week ended with it unfinished)."""
    return bool(state.week) and state.day_log.get(_day_iso(state, day)) == "failed"


def day_done(state: State, day: int) -> bool:
    """Everything planned for the day is ticked, and it wasn't given up first."""
    return bool(state.week) and state.week.day_complete(day) and not day_failed(state, day)


def plan_start(state: State) -> date | None:
    return date.fromisoformat(state.week.week_start) if state.week else None


def mark_watched_items(state: State) -> None:
    """Tick planned episodes you've already watched (on another day, or on MAL / AniList / Shikimori)."""
    for plan in (state.week, state.overtime):
        if not plan:
            continue
        for it in plan.items:
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
        if state.day_log.get(iso) == "failed":
            continue  # rescheduled: it stays failed
        if week.day_complete(day):
            state.day_log[iso] = "done"
        elif state.day_log.get(iso) == "done":
            del state.day_log[iso]


OVERTIME_HOURS = 24  # all of Sunday: 12 hours mostly fell while people were asleep


def _now(today: date | None, now: datetime | None) -> datetime:
    """The current time, or the start of `today` when planning for another day (tests)."""
    if now:
        return now
    return datetime.now() if today in (None, date.today()) else datetime.combine(today, time())


def roll_week(state: State, today: date | None = None, now: datetime | None = None) -> bool:
    """If a new week has begun, settle the old one: every day that had episodes counts as
    completed or, if anything was left unticked, failed. Returns True if a week ended.

    Overtime: if you completed at least one day of it, unfinished days get all of Sunday (to 00:00 Monday) to
    be finished (and saved) instead of failing at midnight; the new week is planned meanwhile."""
    now = _now(today, now)
    today = today or date.today()
    week = state.week
    if not week or not week.calendar:
        return False
    start = date.fromisoformat(week.week_start)
    if week_start_of(today) <= start:
        return False
    settle_overtime(state, now, force=True)  # an older overtime never overlaps a new one
    new_start = start + timedelta(days=PLAN_DAYS)
    deadline = datetime.combine(new_start, time()) + timedelta(hours=OVERTIME_HOURS)
    unfinished = []
    for day in range(PLAN_DAYS):
        items = week.for_day(day)
        iso = (start + timedelta(days=day)).isoformat()
        if not items or state.day_log.get(iso) == "failed":
            continue
        if all(i.done for i in items):
            state.day_log[iso] = "done"
        else:
            unfinished.append(day)
    earned = any(state.day_log.get((start + timedelta(days=d)).isoformat()) == "done" for d in range(PLAN_DAYS))
    if unfinished and earned and week_start_of(today) == new_start and now < deadline:
        # The whole week, as it was at midnight (finished days too), so it looks the same.
        state.overtime = WeekPlan(week.week_start, [copy.copy(i) for i in week.items], calendar=True)
        state.overtime_until = deadline.isoformat(timespec="minutes")
    else:
        for day in unfinished:
            state.day_log[(start + timedelta(days=day)).isoformat()] = "failed"
    return True


def extend_overtime(state: State) -> None:
    """Overtime that started under the old 12-hour rule gets the full 24 hours."""
    if not state.overtime or not state.overtime_until:
        return
    begun = datetime.combine(date.fromisoformat(state.overtime.week_start) + timedelta(days=PLAN_DAYS), time())
    if datetime.fromisoformat(state.overtime_until) < begun + timedelta(hours=OVERTIME_HOURS):
        state.overtime_until = (begun + timedelta(hours=OVERTIME_HOURS)).isoformat(timespec="minutes")


def overtime_days(state: State) -> list[int]:
    """Days of last week still open in overtime (not yet saved)."""
    ot = state.overtime
    if not ot:
        return []
    start = date.fromisoformat(ot.week_start)
    return sorted({i.day for i in ot.items if not ot.day_complete(i.day)
                   and state.day_log.get((start + timedelta(days=i.day)).isoformat()) != "failed"})


def settle_overtime(state: State, now: datetime | None = None, force: bool = False) -> bool:
    """Days finished in overtime are saved; once time is up (or everything is saved), the rest
    fail and overtime ends. Returns True if overtime ended."""
    ot = state.overtime
    if not ot:
        return False
    now = now or datetime.now()
    start = date.fromisoformat(ot.week_start)
    for day in sorted({i.day for i in ot.items}):
        iso = (start + timedelta(days=day)).isoformat()
        if ot.day_complete(day) and state.day_log.get(iso) not in ("done", "failed"):
            state.day_log[iso] = "saved"  # finished in overtime (days done in time stay "done")
    open_days = overtime_days(state)
    expired = force or not state.overtime_until or now >= datetime.fromisoformat(state.overtime_until)
    if open_days and not expired:
        return False
    for day in open_days:
        state.day_log[(start + timedelta(days=day)).isoformat()] = "failed"
    state.overtime, state.overtime_until = None, ""
    return True


def replan(state: State, today: date | None = None, keep_today: bool = False,
           now: datetime | None = None, rebuild_today: bool = False) -> None:
    """Rebuild this week (Sunday–Saturday) from today onward. Earlier days keep their episodes,
    finished or not. When a new week starts, the old one is settled and a fresh week planned.

    Today's planned episodes stay put (a day you've seen shouldn't reshuffle because a status
    changed or a sync came in); a show that left your Watching list gives up its place, and the
    room is filled again. `rebuild_today` plans today from scratch: for changes you make to the
    plan itself (the day's amount, moving or reordering shows, planning settings).
    `keep_today` leaves today's episodes exactly as they are and replans only the days after it."""
    now = _now(today, now)
    today = today or date.today()
    roll_week(state, today, now)
    if settle_overtime(state, now):  # time up: its unwatched episodes go back into the plan
        rebuild_today = True
    prune_overrides(state, today)
    mark_watched_items(state)
    first = week_start_of(today)
    if not (state.week and state.week.calendar and state.week.week_start == first.isoformat()):
        state.week = None  # a new week, or a rolling plan from before 1.0
        keep_today = False
    offset = (today - first).days
    keep_day = None if keep_today or rebuild_today else offset
    state.week = build_week(state, first, offset + (1 if keep_today else 0), keep_day)
    update_day_log(state)


def plan_expired(state: State, today: date | None = None) -> bool:
    today = today or date.today()
    week = state.week
    return week is None or not week.calendar or week.week_start != week_start_of(today).isoformat()
