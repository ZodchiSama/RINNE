"""Release notes shown on the About page (newest first)."""

CHANGELOG: list[tuple[str, str, list[str]]] = [
    ("1.0.0", "Rinne 1.0", [
        "Connect MyAnimeList or AniList: your list comes in and stays in sync as you tick episodes",
        "Weekly goals: weeks run Sunday to Saturday; finish a day to see it celebrated, and Stats keeps "
        "your completed and failed days",
        "Episode titles and thumbnails in your week, and “Where to watch” links",
        "Pause, pin or pace a show, drag shows between days, and catch up on airing shows",
        "New seasons of shows you watched are announced, and can be added automatically",
        "Stats page and a weekly recap",
        "Calendar file (.ics) of your plan for Google Calendar, Thunderbird and others",
        "Update check, a log file for bug reports, and much faster with big libraries",
        "Translations can now be added",
    ]),
    ("0.5.2", "Tidier days & Windows", [
        "Each day's episodes are stacked by show: one card per show, its episodes listed in order",
        "Shows with the fewest episodes left come first each day (and in “Up next today”)",
        "Windows version: installer and portable exe, with a dark title bar in dark themes",
    ]),
    ("0.5.0", "First public release", [
        "Welcome hub on first launch with a quick setup, and a guided tour of the app",
        "Cleaner sidebar with custom icons, today's episode count and an “Up next” card",
        "About page: feedback, contact, version & system info, what's new and privacy",
    ]),
    ("0.4.0", "Rinne", [
        "New name and logo",
        "Discord Rich Presence that works with no setup",
        "A full Settings page: startup, tray, notifications, backups, caches and more",
        "Desktop notifications for new episodes and a daily reminder",
    ]),
    ("0.3.0", "Themes & what's coming", [
        "Midnight, Dark, Light and Yotsuba themes",
        "Background slideshow of today's shows in full-HD fan art",
        "“Coming up” on profiles: announced seasons, films and spin-offs with dates",
    ]),
    ("0.2.0", "Profiles", [
        "Show details from AniList: covers, English/romaji/Japanese titles, exact airing dates",
        "Show profiles with cast, voice actors and why each show is on your list",
        "Rolling 7-day plan with “Replan from today”",
    ]),
    ("0.1.0", "Smart Watchlist", [
        "Weekly schedule from your MyAnimeList list",
        "Finished shows are replaced by their next season automatically",
    ]),
]
