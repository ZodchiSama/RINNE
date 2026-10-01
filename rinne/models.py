"""Core data types shared by the importer, scheduler, recommender and GUI."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

# List statuses (MAL API v2 spelling).
WATCHING = "watching"
COMPLETED = "completed"
ON_HOLD = "on_hold"
DROPPED = "dropped"
PLAN_TO_WATCH = "plan_to_watch"
LIST_STATUSES = [WATCHING, COMPLETED, ON_HOLD, DROPPED, PLAN_TO_WATCH]
STATUS_LABELS = {
    WATCHING: "Watching",
    COMPLETED: "Completed",
    ON_HOLD: "On Hold",
    DROPPED: "Dropped",
    PLAN_TO_WATCH: "Plan to Watch",
}

# Airing statuses.
FINISHED_AIRING = "finished_airing"
CURRENTLY_AIRING = "currently_airing"
NOT_YET_AIRED = "not_yet_aired"

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

DEFAULT_EPISODE_MINUTES = 24
# Bump when AniList data gains new fields, so existing entries are re-fetched once.
# 2: official streaming links.
META_VERSION = 2

ROMAJI = "romaji"
ENGLISH = "english"
NATIVE = "native"
TITLE_LANGUAGES = {ROMAJI: "Romaji", ENGLISH: "English", NATIVE: "日本語"}
# Which title variant `Anime.name` shows; set from Settings.title_language by the GUI.
title_language = ROMAJI


@dataclass
class Anime:
    mal_id: int
    title: str
    status: str = PLAN_TO_WATCH
    episodes_total: int = 0  # 0 = unknown
    episodes_watched: int = 0
    user_score: int = 0  # 0 = unscored
    priority: int = 0  # 0 low, 1 medium, 2 high
    media_type: str = ""
    # Enriched metadata (from MAL API or Jikan).
    mean_score: float = 0.0
    genres: list[str] = field(default_factory=list)
    episode_minutes: int = 0
    airing_status: str = ""
    broadcast_day: int | None = None  # 0 = Monday
    aired_from: str = ""  # ISO date
    relations: dict[str, list[int]] = field(default_factory=dict)  # "sequel" -> [ids]
    relation_titles: dict[str, str] = field(default_factory=dict)  # str(id) -> title
    image_url: str = ""
    banner_url: str = ""
    cover_color: str = ""
    title_romaji: str = ""
    title_english: str = ""
    title_native: str = ""
    anilist_id: int = 0
    next_episode: int = 0  # next episode to air (AniList), 0 = none/unknown
    next_airing: str = ""  # local ISO datetime of next_episode
    enriched: bool = False
    meta_version: int = 0  # which META_VERSION the AniList details were fetched with
    streaming: list[dict] = field(default_factory=list)  # official streams [{"site", "url"}]
    # HD artwork from ani.zip / TheTVDB, fetched on demand (not part of META_FIELDS).
    fanart_url: str = ""  # 1920×1080 background
    logo_url: str = ""  # transparent title logo
    artwork_checked: bool = False
    # Local bookkeeping.
    excluded: bool = False  # user said "never suggest this"
    started_on: str = ""  # ISO date the scheduler promoted it to Watching
    finished_on: str = ""
    added_by_app: bool = False  # e.g. a sequel pulled in that wasn't on the MAL list
    # Per-show planning controls
    paused: bool = False  # stays on Watching but isn't scheduled
    pinned: bool = False  # gets an episode every day, before other shows
    pace: int = 0  # episodes per day for this show (0 = automatic)
    # Why the app put this on the Watching list: {"date", "replaced", "kind", "reasons"}.
    origin: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        """The title in the user's chosen language, falling back to romaji."""
        if title_language == ENGLISH and self.title_english:
            return self.title_english
        if title_language == NATIVE and self.title_native:
            return self.title_native
        return self.title_romaji or self.title

    def all_titles(self) -> list[str]:
        seen, out = set(), []
        for t in (self.name, self.title_romaji, self.title_english, self.title_native, self.title):
            if t and t not in seen:
                seen.add(t)
                out.append(t)
        return out

    @property
    def minutes_per_episode(self) -> int:
        return self.episode_minutes or DEFAULT_EPISODE_MINUTES

    @property
    def needs_enrichment(self) -> bool:
        # Entries enriched before AniList support lack its data (titles, covers): refetch once.
        return (not self.enriched or (bool(self.relations) and not self.relation_titles)
                or not (self.anilist_id or self.title_native)
                or (bool(self.anilist_id) and self.meta_version < META_VERSION))

    @property
    def is_finished(self) -> bool:
        return self.episodes_total > 0 and self.episodes_watched >= self.episodes_total

    def episodes_available(self, on: date) -> int | None:
        """How many episodes exist by `on`; None means no known limit."""
        if self.airing_status == NOT_YET_AIRED:
            return 0
        if self.airing_status == CURRENTLY_AIRING and self.next_episode and self.next_airing:
            # Exact: AniList says which episode airs next and when; later ones follow weekly.
            try:
                nxt = date.fromisoformat(self.next_airing[:10])
            except ValueError:
                nxt = None
            if nxt is not None:
                aired = self.next_episode - 1
                if on >= nxt:
                    aired += (on - nxt).days // 7 + 1
                return min(aired, self.episodes_total) if self.episodes_total else aired
        if self.airing_status == CURRENTLY_AIRING and self.aired_from:
            try:
                start = date.fromisoformat(self.aired_from[:10])
            except ValueError:
                return None
            if on < start:
                return 0
            aired = (on - start).days // 7 + 1
            return min(aired, self.episodes_total) if self.episodes_total else aired
        return self.episodes_total or None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Anime:
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


# Metadata fields that come from MAL/Jikan (as opposed to the user's list entry).
META_FIELDS = (
    "mean_score", "genres", "episode_minutes", "airing_status", "broadcast_day", "aired_from",
    "relations", "relation_titles", "image_url", "banner_url", "cover_color", "title_romaji",
    "title_english", "title_native", "anilist_id", "next_episode", "next_airing", "streaming",
    "enriched", "meta_version",
)

EPISODES = "episodes"
MINUTES = "minutes"


@dataclass
class Settings:
    plan_by: str = EPISODES  # what the per-day amounts mean
    daily_episodes: list[int] = field(default_factory=lambda: [2, 2, 2, 2, 2, 4, 4])
    daily_minutes: list[int] = field(default_factory=lambda: [60, 60, 60, 60, 60, 120, 120])
    max_eps_per_show_per_day: int = 2  # soft: exceeded only to fill the day's amount
    catch_up_airing: bool = True  # airing shows you're behind on get priority
    calendar_file: bool = False  # keep <data>/rinne-plan.ics up to date
    notify_premieres: bool = True  # a sequel of a show you watched starts airing
    auto_add_sequels: bool = False  # …and add it to Plan to Watch automatically
    auto_replace: bool = True
    allow_airing: bool = True
    mal_username: str = ""
    mal_client_id: str = ""
    zoom: float = 1.0
    title_language: str = ROMAJI
    theme: str = "midnight"
    backdrop: bool = False  # slideshow of today's shows behind the window
    slide_seconds: int = 9
    backdrop_dim: int = 1  # 0 light, 1 medium, 2 strong
    # General
    start_page: str = "week"  # week | next | library
    close_to_tray: bool = False
    start_minimized: bool = False
    refresh_on_startup: bool = True  # re-check airing shows for new episodes
    # Series following
    follow_extras: bool = True  # follow sequels into movies, OVAs and specials
    # Notifications
    notify_new_episodes: bool = True
    daily_reminder: bool = False
    reminder_time: str = "19:00"
    # Discord Rich Presence
    discord_enabled: bool = True
    discord_app_id: str = ""  # optional override; empty = Rinne's built-in application

    def discord_client_id(self) -> str:
        from . import DISCORD_APP_ID
        return self.discord_app_id.strip() or DISCORD_APP_ID
    discord_show_cover: bool = True
    discord_buttons: bool = True
    discord_private: bool = False
    # Updates
    check_updates: bool = True
    last_update_check: str = ""  # ISO date

    def day_amount(self, day: int) -> int:
        return (self.daily_episodes if self.plan_by == EPISODES else self.daily_minutes)[day]

    def set_day_amount(self, day: int, value: int) -> None:
        (self.daily_episodes if self.plan_by == EPISODES else self.daily_minutes)[day] = value

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Settings:
        from . import DISCORD_APP_ID
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        if known.get("discord_app_id", "").strip() == DISCORD_APP_ID:
            known["discord_app_id"] = ""  # same as the built-in app
        return cls(**known)


@dataclass
class ScheduleItem:
    day: int  # 0 = Monday
    mal_id: int
    episode: int
    done: bool = False
    note: str = ""  # e.g. "New: replaces X"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ScheduleItem:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class WeekPlan:
    week_start: str  # ISO date of the Monday
    items: list[ScheduleItem] = field(default_factory=list)

    def for_day(self, day: int) -> list[ScheduleItem]:
        return [i for i in self.items if i.day == day]

    def to_dict(self) -> dict:
        return {"week_start": self.week_start, "items": [i.to_dict() for i in self.items]}

    @classmethod
    def from_dict(cls, d: dict) -> WeekPlan:
        return cls(d["week_start"], [ScheduleItem.from_dict(i) for i in d.get("items", [])])
