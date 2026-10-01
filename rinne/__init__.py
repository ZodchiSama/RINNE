"""Rinne — a weekly anime schedule built from your MyAnimeList list, that follows each series."""

__version__ = "1.0.0"
APP_NAME = "rinne"  # data/cache folder and desktop-entry name
DISPLAY_NAME = "Rinne"
LEGACY_APP_NAMES = ("smart-watchlist",)  # older folder names, migrated on first run
USER_AGENT = f"Rinne/{__version__} (+linux desktop app)"
# Rinne's own Discord application. Not a secret: it only names the app shown in Rich Presence,
# and lets every install show "Watching Rinne" (with the art uploaded to it) with no setup.
DISCORD_APP_ID = "1553831739510628383"

# Rinne's registered API clients (public identifiers, not secrets). Empty = not set up yet.
MAL_CLIENT_ID = "66e1801e97640f29adf276a76c99eba6"  # myanimelist.net/apiconfig, app type "other", redirect MAL_REDIRECT below
MAL_REDIRECT = "http://localhost:47811/callback"
ANILIST_CLIENT_ID = "52457"  # anilist.co/settings/developer, redirect https://anilist.co/api/v2/oauth/pin

# Project links shown on the About page and used by the feedback dialog.
# Leave a value empty to hide its button.
AUTHOR = "Zodchi"
HOMEPAGE_URL = "https://github.com/ZodchiSama/RINNE"
ISSUES_URL = "https://github.com/ZodchiSama/RINNE/issues"
CONTACT_EMAIL = "zodchi.san@proton.me"
COMMUNITY_URL = ""  # e.g. a Discord server invite
LICENSE = "MIT"
