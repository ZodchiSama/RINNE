# Contributing to Rinne

Thanks for helping! Bug reports and ideas are welcome as
[issues](https://github.com/ZodchiSama/RINNE/issues), or from inside the app with
**Settings → About → Send feedback**.

## Running from source

```sh
git clone https://github.com/ZodchiSama/RINNE.git
cd RINNE
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/rinne
```

Run the tests before sending a pull request. They're offscreen and never touch the network:

```sh
.venv/bin/python -m pytest
```

## Code layout

| Path | What's there |
|---|---|
| `rinne/models.py`, `storage.py` | Shows, settings and the saved state |
| `rinne/scheduler.py` | The weekly plan: sharing out episodes, catch-up, moves, finales |
| `rinne/recommender.py` | What replaces a finished show, and why |
| `rinne/anilist.py`, `mal.py`, `artwork.py` | Metadata sources (AniList first, MAL/Jikan as fallbacks) |
| `rinne/sync.py` | Sending progress back to MyAnimeList and AniList |
| `rinne/stats.py`, `calendar_export.py`, `announcements.py` | Stats, the .ics file, new-season checks |
| `rinne/gui/window.py` | The main window; `services.py` has updates, sync and imports |
| `rinne/gui/week.py`, `upnext.py`, `library.py`, `stats_page.py`, `profile.py` | The pages |
| `rinne/gui/settings.py` (+ `settings_data.py`, `settings_about.py`) | The Settings page |
| `tests/test_core.py`, `tests/test_gui.py` | Logic tests and interface tests |

## Translating Rinne

Rinne currently ships in English only. The translation support is built in, so a new language
needs a single JSON file and no code.

1. Copy `rinne/locale/template.json` to `rinne/locale/<code>.json`, using a language code such as
   `es`, `de`, `fr`, `pt_BR` or `ja`.
2. Set `"_language"` to the language's own name (e.g. `"Español"`), then fill in translations:

   ```json
   {
     "_language": "Español",
     "Your Week": "Tu semana",
     "Library": "Biblioteca"
   }
   ```

   Leave a string empty to keep it in English, so a partial translation is fine.
   Keep `&&` (a literal `&` in buttons) and HTML tags such as `<i>` and `<b>` as they are.
3. Pick it in **Settings → General → Interface language** and restart Rinne to check it.
4. Open a pull request with the file.

When strings change in the code, run `python tools/extract_strings.py`. It refreshes
`template.json` and adds new strings (empty) to every catalog. A test fails if the template is out
of date.

For developers: wrap interface text in `_("…")` (`from ..i18n import _`). Use `N_("…")` for
module-level constants and translate them with `_()` where they are shown. The Settings page
helpers (`_header`, `_group`, `_row`, `_switch`, `_button`) translate their text themselves.
Write whole sentences rather than joining pieces, so translators can reorder words.

## Releases

Pushing a `v*` tag builds the Windows installer, the portable exe and the AppImage on GitHub
Actions and attaches them to the release. Packaging for the AUR and Flathub lives in `packaging/`.
