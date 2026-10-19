"""Release notes shown in What's new and on the About page (newest first).
Notes wrapped in N_ are translated when shown."""

from .i18n import N_

CHANGELOG: list[tuple[str, str, list[str]]] = [
    ("1.1.6", N_("Overtime"), [
        N_("Overtime: if a week ends with unfinished days and you completed at least one, you get all of Sunday to finish and save them, with the new week just below"),
        N_("Build my Watching list: Rinne goes through your whole list and picks the shows to watch now. Choose how many, and how many currently airing"),
        N_("Seasonal picks: the list builder favours what fits the time of year, like horror and the supernatural in October"),
        N_("Today's plan stays put: a sync or a status change no longer reshuffles the episodes planned for today"),
        N_("Opening Rinne while it's already running (e.g. in the tray) brings up its window instead of starting a second copy"),
        N_("Shows AniList doesn't have, such as fan-made OVAs, no longer cause sync errors"),
        N_("Fixed a rare crash while saving, and one after signing in from Settings → Accounts"),
        N_("Halloween theme: buttons stay readable over the moon"),
    ]),
    ("1.1.5", N_("Back in sync"), [
        N_("When a sign-in to MyAnimeList, AniList or Shikimori expires, Rinne says so until you reconnect, and reconnecting sends everything that changed in the meantime"),
        N_("Halloween theme: the moon sits higher, so page descriptions stay readable"),
    ]),
    ("1.1.4", N_("Spooky season"), [
        N_("A Halloween theme for October, switched on for you: a harvest moon, cobwebs, bats and a spider. Your own theme comes back in November"),
        N_("Settings' section list stays readable over the background slideshow"),
        N_("The Reschedule button is gone for now: unfinished days simply wait until the week ends"),
        N_("Planning never puts an episode ahead of one you ticked early on a later day"),
    ]),
    ("1.1.3", N_("Catching up"), [
        N_("Reschedule missed episodes: unfinished earlier days move their episodes into the rest of the week"),
        N_("Ticking an episode no longer reshuffles the days after it"),
    ]),
    ("1.1.2", N_("Shikimori sync and sharing"), [
        N_("Connect Shikimori in Settings → Accounts: your list syncs both ways, like MyAnimeList and AniList"),
        N_("Share a show as a card with your progress and score, or as a link, text or title"),
        N_("Share your week: a card of the days you completed, episodes and time"),
        N_("Select a title or synopsis and press Ctrl C to copy it"),
        N_("Updates install themselves: Rinne downloads, checks and restarts into the new version"),
        N_("Discord shows the Rinne logo again, and a “Get Rinne” button"),
        N_("A stale entry on one account no longer undoes newer progress from another"),
    ]),
    ("1.1.1", N_("A new look"), [
        N_("New logo: the Wheel of Reincarnation, an arrow chasing its own tail"),
        N_("New app icon, clear at every size from the tray to the desktop"),
        N_("The logo follows your theme, light or dark"),
    ]),
    ("1.1.0", N_("Two-way sync and Russian"), [
        N_("Changes you make on MyAnimeList or AniList come back to Rinne too, on startup and every few hours"),
        N_("Russian interface, and show titles in Russian (from Shikimori)"),
        N_("Import a list from Shikimori"),
        N_("Undo for ticked episodes"),
        N_("An offline notice; Rinne catches up when you're back online"),
        N_("Fixes: only the current page is highlighted in the sidebar; narrow windows on Windows"),
    ]),
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
