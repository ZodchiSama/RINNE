<p align="center"><img src="rinne/assets/logo-round.png" width="160" alt="Rinne"></p>

# Rinne 輪廻

*The cycle of rebirth.* A desktop app for Linux and Windows that turns your MyAnimeList list into a weekly watch
schedule. When a show ends, its next season is reborn in its place, and the app explains why.

By **Zodchi**.

## Install

**Windows:** download `Rinne-Setup-<version>.exe` (installer) or `Rinne-Portable-<version>.exe`
(no install, runs from anywhere) from the [latest release](https://github.com/ZodchiSama/RINNE/releases/latest).
Windows may warn that the app is from an unknown publisher, because it isn't code-signed yet:
click **More info → Run anyway**.

**Linux (AppImage):** download `Rinne-<version>-x86_64.AppImage` from the
[latest release](https://github.com/ZodchiSama/RINNE/releases/latest), make it executable and run it:

```sh
chmod +x Rinne-*-x86_64.AppImage
./Rinne-*-x86_64.AppImage
```

It runs on most distributions from 2022 on, with nothing to install. AppImage managers such as
Gear Lever or AppImageLauncher can add it to your app menu and update it from GitHub releases.

**Linux (from source):**

```sh
git clone https://github.com/ZodchiSama/RINNE.git
cd RINNE
./install.sh          # venv + `rinne` command + app icon + app-menu entry
```

Or run from source: `python3 -m venv .venv && .venv/bin/pip install -e .[dev] && .venv/bin/rinne`

## Getting your list in

- **Export file (no setup):** on MAL go to *Profile → Export* (`myanimelist.net/panel.php?go=export`),
  export your Anime List, then use **Import → From MAL export file** on the `.xml.gz`.
- **By username:** create a free Client ID at `myanimelist.net/apiconfig` (app type "other"),
  paste it in **Settings → Library & Data**, then use **Import → From MAL username**.

After an import, the app fetches show details from **AniList** (no account needed, 50 shows per
request): covers, English/romaji/Japanese titles, sequel/prequel links, episode length and exact
airing progress. Anything AniList doesn't have is looked up on MAL (with a Client ID) or Jikan.
Responses are cached on disk.

Re-importing is safe. Progress you tracked in the app is never rolled back by an older MAL list,
but if you set a show to On-Hold or Dropped on MAL, that change is applied.

## First launch

A welcome hub introduces Rinne and runs a quick setup: import your list, choose how many episodes
you watch, and pick a theme, titles, the slideshow, Discord and notifications. A guided tour then
shows where everything is. Both can be replayed from Settings → General.

## Using it

- **Your Week:** a 7-day plan with today at the top, and a cover card for each episode. Tick one
  when you've watched it and the rest of the plan is replanned. Use **−** / **+** on a day to
  change how much you watch that day. **Replan from today** (Ctrl R) starts a new 7-day plan
  today and ignores past days.
- **Click any show** (episode card, poster, Up Next row) to open its **profile**:
  - why it's on your list and in your plan
  - synopsis and tags
  - the cast and their Japanese voice actors, with fan counts, "big name" badges, roles you know
    them from in shows you've watched, and their other notable roles
  - related entries, staff, and recommendations
- **Titles:** switch between **Romaji / English / 日本語** in **Settings → General**. Search
  matches all three.
- **Coming up** (on every profile): new seasons, films and spin-offs that are announced or airing
  now, with their start date (or expected season). The app finds these by following the sequel
  chain on AniList, so a Season 3 announcement shows up even on your Season 1 profile.
- **Themes:** Midnight, Dark, Light and Yotsuba (4chan's classic cream-and-maroon), picked in
  **Settings → Appearance**. **Slides** puts a slideshow of today's shows, in full-HD fan art from
  TheTVDB, behind the whole window, and works with any theme.
- **Up Next:** what will replace each show you're watching when it finishes, and why.
- **Library:** your whole list as a poster grid. Filter by status, search, sort. Right-click a show
  to change its status or progress.
- **Zoom:** press **Ctrl +** / **Ctrl −** or use **Ctrl + mouse wheel**. **Ctrl 0** resets it.
  The zoom level is saved.
- Shortcuts: Ctrl 1/2/3 switch pages, Ctrl O imports a file, Ctrl R replans from today, Ctrl , opens Settings.

## How scheduling works

- **Only shows on your Watching list are scheduled.** Plan to Watch shows never appear on their
  own. They join the schedule only when one replaces a finished show, or when you press
  *Start watching*.
- **Settings → Your week:** choose to plan by **episodes per day** or **minutes per day**, and set
  each weekday separately (0 = day off). Quick presets are included.
- Episodes are shared out evenly across your shows. "Max episodes of one show per day" is kept
  when possible. If you watch only a couple of shows, it's exceeded so each day still gets the
  number of episodes you asked for.
- **Airing shows** are paced by release, using AniList's exact next-episode date. An episode is
  only scheduled after it has aired.
- A show's final episode is marked **Finale**, and its tooltip names what comes next.

## What replaces a finished show

When you tick a finale:

1. **Follow the series.** The app walks the sequel chain. It skips seasons you've already
   completed and resumes a season you put On Hold. If the next season **isn't on your MAL list**,
   the app fetches it from MAL/Jikan and adds it.
2. The chain stops at a season that hasn't aired yet, one you dropped, or one you're already
   watching. Only then does the app pick from **Plan to Watch**, scored by:

| Signal | Effect |
|---|---|
| Same franchise (side story, spin-off…) | +25 |
| Its prequel is still unfinished on your list | −80 (no season 2 before season 1) |
| Genre overlap with the finished show | up to +25 |
| Your taste: your average score in its genres compared with your overall average | ± |
| MAL community score | ±, centred on 7.0 |
| Priority set on MAL | +6 / +15 |
| Genres already covered by your other shows | up to −10 (keeps variety) |
| Long shows (> 50 eps) / short (≤ 13) | small − / + |

A pop-up shows what's next and why. You can turn automatic replacement off in Settings.
Right-click a show in Library and choose *Never suggest this* to exclude it.

## Settings

Settings is a full page, and changes apply immediately:

- **General:** which page to open on, starting minimized to the tray, keeping Rinne running in the
  tray when you close the window, checking airing shows on startup, and title language.
- **Appearance:** theme cards (Midnight, Dark, Light, Yotsuba), the slideshow (time per image and
  dimming), and interface size.
- **Schedule:** episodes or minutes per day, presets, the per-show daily cap, starting the next
  season automatically, following the series into movies/OVAs/specials, and airing shows as picks.
- **Notifications:** new-episode alerts and a daily reminder of today's plan.
- **Discord:** Rich Presence shown as "Watching Rinne", with today's next episode, cover art, a
  MyAnimeList button, and a private mode. It works automatically while the Discord desktop app is
  running: Rinne ships with its own Discord application, so there's no setup. A custom
  Application ID can be set under Advanced.
- **Library & Data:** MyAnimeList account, imports, cache sizes and clearing, backup/restore,
  and resetting settings.
- **About:** version, credits, data sources and keyboard shortcuts.

## Data

- State: `~/.local/share/rinne/state.json`
- API and image cache: `~/.cache/rinne/`
- Folders from the old name (`smart-watchlist`) are moved over automatically on first launch.

## Limitations

- Progress stays local. Updating your MAL list would need OAuth login, which isn't implemented yet.
- Only shows already on your list are suggested as Plan to Watch picks. Unlisted sequels are handled (see above).
- A few obscure entries (specials, doujin works) have no data on AniList or MAL/Jikan. They get a
  lettered placeholder cover.

## Development

```sh
.venv/bin/python -m pytest
packaging/linux/build_appimage.sh   # AppImage in dist/ (needs the dev dependencies)
# Windows and AppImage builds are also made by GitHub Actions on each v* tag.
.venv/bin/python tools/make_icons.py   # rebuild icons from assets/source/
```

## Feedback

Found a bug or have an idea? Use **Settings → About → Send feedback** in the app,
[open an issue](https://github.com/ZodchiSama/RINNE/issues), or email **zodchi.san@proton.me**.

## License

[MIT](LICENSE) © 2026 Zodchi
