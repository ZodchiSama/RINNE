"""Two-way account sync groundwork: sign-in to MyAnimeList / AniList and pushing progress.

MAL uses OAuth 2 with PKCE (method "plain", as MAL requires) and a one-shot local HTTP server
on the registered redirect URL. AniList uses its "pin" flow: the user approves in the browser
and pastes the token AniList shows. Rinne then pushes status, episodes and score for shows that
changed since the last successful sync — nothing else is ever sent.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from . import ANILIST_CLIENT_ID, MAL_REDIRECT, USER_AGENT, anilist
from .models import Anime

MAL_AUTH = "https://myanimelist.net/v1/oauth2/authorize"
MAL_TOKEN = "https://myanimelist.net/v1/oauth2/token"
MAL_API = "https://api.myanimelist.net/v2"
ANILIST_AUTH = "https://anilist.co/api/v2/oauth/authorize?client_id={id}&response_type=token"

ANILIST_STATUS = {"watching": "CURRENT", "completed": "COMPLETED", "on_hold": "PAUSED",
                  "dropped": "DROPPED", "plan_to_watch": "PLANNING"}


class SyncError(Exception):
    pass


class AuthExpired(SyncError):
    """The saved sign-in no longer works; the user needs to connect again."""


# --------------------------------------------------------------------------- what to send


def snapshot(anime: Anime) -> list:
    return [anime.status, anime.episodes_watched, anime.user_score]


def pending_changes(library: dict[int, Anime], synced: dict[int, list]) -> list[Anime]:
    """Shows whose status, episodes or score differ from what was last sent."""
    return [a for a in library.values() if synced.get(a.mal_id) != snapshot(a)]


def baseline(library: dict[int, Anime]) -> dict[int, list]:
    """On first connect, treat everything as already in sync (don't push the whole list)."""
    return {a.mal_id: snapshot(a) for a in library.values()}


# --------------------------------------------------------------------------- HTTP helpers


def _request(url: str, data: dict | None = None, method: str = "GET", token: str = "") -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise AuthExpired("Sign-in expired") from e
        raise SyncError(f"HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise SyncError(f"Network error: {e.reason}") from e


# --------------------------------------------------------------------------- MyAnimeList


def mal_authorize(client_id: str, timeout: float = 300, open_browser=webbrowser.open) -> dict:
    """Sign in to MAL in the browser; returns tokens {access_token, refresh_token, expires_at}."""
    if not client_id:
        raise SyncError("MyAnimeList sign-in isn't set up in this build.")
    verifier = secrets.token_urlsafe(96)[:128]  # PKCE "plain": challenge == verifier
    state = secrets.token_urlsafe(16)
    redirect = urllib.parse.urlparse(MAL_REDIRECT)
    result: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (http.server API)
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            ok = q.get("state", [""])[0] == state and "code" in q
            if ok:
                result["code"] = q["code"][0]
            else:
                result["error"] = q.get("error", ["Sign-in was cancelled"])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Connected! You can close this tab and go back to Rinne." if ok else \
                "Sign-in didn't complete. You can close this tab and try again in Rinne."
            self.wfile.write(f"<html><body style='font-family:sans-serif;background:#0e1016;color:#e9ebf2;"
                             f"display:grid;place-items:center;height:90vh'><h2>{msg}</h2></body></html>".encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", redirect.port or 80), Handler)
    server.timeout = 1
    thread = threading.Thread(target=lambda: _serve_until(server, result, timeout), daemon=True)
    thread.start()
    open_browser(MAL_AUTH + "?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": client_id, "code_challenge": verifier,
        "code_challenge_method": "plain", "state": state, "redirect_uri": MAL_REDIRECT}))
    thread.join(timeout + 5)
    server.server_close()
    if "code" not in result:
        raise SyncError(result.get("error") or "Timed out waiting for MyAnimeList sign-in.")
    tokens = _request(MAL_TOKEN, {"client_id": client_id, "grant_type": "authorization_code",
                                  "code": result["code"], "code_verifier": verifier,
                                  "redirect_uri": MAL_REDIRECT}, method="POST")
    return _with_expiry(tokens)


def _serve_until(server: HTTPServer, result: dict, timeout: float) -> None:
    end = time.time() + timeout
    while not result and time.time() < end:
        server.handle_request()


def _with_expiry(tokens: dict) -> dict:
    tokens["expires_at"] = time.time() + int(tokens.get("expires_in") or 3600) - 60
    return tokens


def mal_refresh(client_id: str, tokens: dict) -> dict:
    if not tokens.get("refresh_token"):
        raise AuthExpired("No refresh token")
    try:
        fresh = _request(MAL_TOKEN, {"client_id": client_id, "grant_type": "refresh_token",
                                     "refresh_token": tokens["refresh_token"]}, method="POST")
    except SyncError as e:
        raise AuthExpired(str(e)) from e
    return _with_expiry(fresh)


def mal_valid_token(client_id: str, tokens: dict) -> dict:
    """Tokens that are good for at least a minute (refreshing them if needed)."""
    if tokens.get("expires_at", 0) > time.time():
        return tokens
    return mal_refresh(client_id, tokens)


def mal_username(tokens: dict) -> str:
    return _request(f"{MAL_API}/users/@me", token=tokens["access_token"]).get("name", "")


def mal_push(tokens: dict, anime: Anime) -> None:
    data = {"status": anime.status, "num_watched_episodes": anime.episodes_watched}
    if anime.user_score:
        data["score"] = anime.user_score
    _request(f"{MAL_API}/anime/{anime.mal_id}/my_list_status", data, method="PATCH",
             token=tokens["access_token"])


# --------------------------------------------------------------------------- AniList


def anilist_open_signin(client_id: str = ANILIST_CLIENT_ID, open_browser=webbrowser.open) -> None:
    if not client_id:
        raise SyncError("AniList sign-in isn't set up in this build.")
    open_browser(ANILIST_AUTH.format(id=client_id))


def anilist_viewer(token: str) -> str:
    try:
        data = anilist.query("query { Viewer { id name } }", {}, token=token)
    except anilist.AniListError as e:
        raise AuthExpired(str(e)) from e
    name = (data.get("Viewer") or {}).get("name")
    if not name:
        raise AuthExpired("That code didn't work — copy the whole token from AniList.")
    return name


SAVE_ENTRY = """mutation ($mediaId: Int, $progress: Int, $status: MediaListStatus, $score: Float) {
  SaveMediaListEntry(mediaId: $mediaId, progress: $progress, status: $status, score: $score) { id } }"""


def anilist_push(token: str, anime: Anime) -> None:
    if not anime.anilist_id:
        raise SyncError(f"{anime.name} has no AniList id yet")
    variables = {"mediaId": anime.anilist_id, "progress": anime.episodes_watched,
                 "status": ANILIST_STATUS.get(anime.status, "CURRENT")}
    if anime.user_score:
        variables["score"] = float(anime.user_score)
    try:
        anilist.query(SAVE_ENTRY, variables, token=token)
    except anilist.AniListError as e:
        if "Invalid token" in str(e) or "Unauthorized" in str(e):
            raise AuthExpired(str(e)) from e
        raise SyncError(str(e)) from e


# --------------------------------------------------------------------------- the sync run


def push_all(changes: list[Anime], mal_client_id: str, mal_tokens: dict | None,
             anilist_token: str | None) -> dict:
    """Send changes to each connected service. Safe in a worker thread.
    Returns {"mal": [ok mal_ids], "anilist": [...], "mal_tokens": refreshed|None,
             "errors": [str], "expired": [service names]}."""
    out = {"mal": [], "anilist": [], "mal_tokens": None, "errors": [], "expired": []}
    if mal_tokens:
        try:
            tokens = mal_valid_token(mal_client_id, mal_tokens)
            if tokens is not mal_tokens:
                out["mal_tokens"] = tokens
            for a in changes:
                try:
                    mal_push(tokens, a)
                    out["mal"].append(a.mal_id)
                except AuthExpired:
                    raise
                except SyncError as e:
                    out["errors"].append(f"MAL · {a.name}: {e}")
        except AuthExpired:
            out["expired"].append("mal")
    if anilist_token:
        try:
            for a in changes:
                try:
                    anilist_push(anilist_token, a)
                    out["anilist"].append(a.mal_id)
                except AuthExpired:
                    raise
                except SyncError as e:
                    out["errors"].append(f"AniList · {a.name}: {e}")
        except AuthExpired:
            out["expired"].append("anilist")
    return out
