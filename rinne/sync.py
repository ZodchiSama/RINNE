"""Account sync: sign-in to MyAnimeList / AniList / Shikimori and pushing progress.

MAL uses OAuth 2 with PKCE (method "plain", as MAL requires) and a one-shot local HTTP server
on the registered redirect URL; Shikimori uses the same local redirect with a client secret.
AniList uses its "pin" flow: the user approves in the browser and pastes the token AniList shows.
Rinne then pushes status, episodes and score for shows that changed since the last successful
sync — nothing else is ever sent.
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

from . import ANILIST_CLIENT_ID, MAL_REDIRECT, SHIKIMORI_REDIRECT, USER_AGENT, anilist
from .models import Anime

MAL_AUTH = "https://myanimelist.net/v1/oauth2/authorize"
MAL_TOKEN = "https://myanimelist.net/v1/oauth2/token"
MAL_API = "https://api.myanimelist.net/v2"
ANILIST_AUTH = "https://anilist.co/api/v2/oauth/authorize?client_id={id}&response_type=token"

ANILIST_STATUS = {"watching": "CURRENT", "completed": "COMPLETED", "on_hold": "PAUSED",
                  "dropped": "DROPPED", "plan_to_watch": "PLANNING"}

SHIKIMORI = "https://shikimori.io"
SHIKIMORI_APP = "Rinne"  # Shikimori asks for the registered application name as the User-Agent
SHIKIMORI_STATUS = {"watching": "watching", "completed": "completed", "on_hold": "on_hold",
                    "dropped": "dropped", "plan_to_watch": "planned"}


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


def after_pull(library: dict[int, Anime], account: list[Anime], previous: dict[int, list]) -> dict[int, list]:
    """The sync baseline after bringing in an account's list: what the account holds now.
    Anything newer in Rinne (a tick not sent yet, progress made offline) still differs, so it's
    still sent. Shows the account doesn't have keep their old baseline, or count as in sync, so
    a pull never pushes a whole other list into the account."""
    base = {a.mal_id: snapshot(a) for a in account}
    for a in library.values():
        if a.mal_id not in base:
            base[a.mal_id] = previous.get(a.mal_id, snapshot(a))
    return base


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
    code = _browser_code(MAL_REDIRECT, lambda state: MAL_AUTH + "?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": client_id, "code_challenge": verifier,
        "code_challenge_method": "plain", "state": state, "redirect_uri": MAL_REDIRECT}),
        "MyAnimeList", timeout, open_browser)
    tokens = _request(MAL_TOKEN, {"client_id": client_id, "grant_type": "authorization_code",
                                  "code": code, "code_verifier": verifier,
                                  "redirect_uri": MAL_REDIRECT}, method="POST")
    return _with_expiry(tokens)


def _browser_code(redirect_url: str, auth_url, service: str, timeout: float, open_browser) -> str:
    """Open `auth_url(state)` in the browser and wait for the service to redirect back to a
    one-shot local server on `redirect_url`; returns the authorization code."""
    state = secrets.token_urlsafe(16)
    redirect = urllib.parse.urlparse(redirect_url)
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
    open_browser(auth_url(state))
    thread.join(timeout + 5)
    server.server_close()
    if "code" not in result:
        raise SyncError(result.get("error") or f"Timed out waiting for {service} sign-in.")
    return result["code"]


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


# --------------------------------------------------------------------------- Shikimori

_shiki_last = 0.0


def _shiki(path: str, data: dict | None = None, method: str = "GET", token: str = "", form: bool = False):
    """A Shikimori request (JSON, or a form for /oauth/token). At most ~4 a second, as Shikimori
    asks; a 429 is retried once after the wait it gives."""
    global _shiki_last
    headers = {"User-Agent": SHIKIMORI_APP, "Accept": "application/json"}
    body = None
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for attempt in range(2):
        gap = time.monotonic() - _shiki_last
        if gap < 0.25:
            time.sleep(0.25 - gap)
        _shiki_last = time.monotonic()
        req = urllib.request.Request(SHIKIMORI + path, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 0:
                time.sleep(min(10, int(e.headers.get("Retry-After") or 2)))
                continue
            if e.code in (401, 403):
                raise AuthExpired("Sign-in expired") from e
            raise SyncError(f"HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise SyncError(f"Network error: {e.reason}") from e
    raise SyncError("Shikimori is busy")


def shikimori_authorize(client_id: str, client_secret: str, timeout: float = 300,
                        open_browser=webbrowser.open) -> dict:
    """Sign in to Shikimori in the browser; returns tokens {access_token, refresh_token, expires_at}."""
    if not (client_id and client_secret):
        raise SyncError("Shikimori sign-in isn't set up in this build.")
    code = _browser_code(SHIKIMORI_REDIRECT, lambda state: SHIKIMORI + "/oauth/authorize?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": SHIKIMORI_REDIRECT, "response_type": "code",
        "scope": "user_rates", "state": state}), "Shikimori", timeout, open_browser)
    tokens = _shiki("/oauth/token", {"grant_type": "authorization_code", "client_id": client_id,
                                     "client_secret": client_secret, "code": code,
                                     "redirect_uri": SHIKIMORI_REDIRECT}, method="POST", form=True)
    return _with_expiry(tokens)


def shikimori_valid_token(client_id: str, client_secret: str, tokens: dict) -> dict:
    """Tokens good for at least a minute; Shikimori's last a day, then they're refreshed."""
    if tokens.get("expires_at", 0) > time.time():
        return tokens
    if not tokens.get("refresh_token"):
        raise AuthExpired("No refresh token")
    try:
        fresh = _shiki("/oauth/token", {"grant_type": "refresh_token", "client_id": client_id,
                                        "client_secret": client_secret,
                                        "refresh_token": tokens["refresh_token"]}, method="POST", form=True)
    except SyncError as e:
        raise AuthExpired(str(e)) from e
    return _with_expiry(fresh)


def shikimori_whoami(tokens: dict) -> tuple[int, str]:
    """(user id, nickname) of the signed-in account."""
    me = _shiki("/api/users/whoami", token=tokens["access_token"]) or {}
    if not me.get("id"):
        raise AuthExpired("Shikimori didn't return the account")
    return int(me["id"]), me.get("nickname", "")


def shikimori_push(tokens: dict, user_id: int, anime: Anime) -> None:
    """Create or update the account's entry for this show (Shikimori ids are MAL ids)."""
    entry = {"status": SHIKIMORI_STATUS.get(anime.status, "watching"), "episodes": anime.episodes_watched,
             "score": anime.user_score or 0}
    token = tokens["access_token"]
    found = _shiki("/api/v2/user_rates?" + urllib.parse.urlencode(
        {"user_id": user_id, "target_id": anime.mal_id, "target_type": "Anime"}), token=token) or []
    if found:
        _shiki(f"/api/v2/user_rates/{found[0]['id']}", {"user_rate": entry}, method="PATCH", token=token)
    else:
        entry.update({"user_id": user_id, "target_id": anime.mal_id, "target_type": "Anime"})
        _shiki("/api/v2/user_rates", {"user_rate": entry}, method="POST", token=token)


# --------------------------------------------------------------------------- the sync run


def push_all(changes: list[Anime], mal_client_id: str, mal_tokens: dict | None,
             anilist_token: str | None, shikimori: dict | None = None) -> dict:
    """Send changes to each connected service. Safe in a worker thread.
    `shikimori`: {"client_id", "client_secret", "tokens", "user_id"} when connected.
    Returns {"mal": [ok mal_ids], "anilist": [...], "shikimori": [...], "mal_tokens": refreshed|None,
             "shikimori_tokens": refreshed|None, "errors": [str], "expired": [service names]}."""
    out = {"mal": [], "anilist": [], "shikimori": [], "mal_tokens": None, "shikimori_tokens": None,
           "errors": [], "expired": []}
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
    if shikimori and shikimori.get("tokens"):
        try:
            tokens = shikimori_valid_token(shikimori["client_id"], shikimori["client_secret"], shikimori["tokens"])
            if tokens is not shikimori["tokens"]:
                out["shikimori_tokens"] = tokens
            for a in changes:
                try:
                    shikimori_push(tokens, shikimori["user_id"], a)
                    out["shikimori"].append(a.mal_id)
                except AuthExpired:
                    raise
                except SyncError as e:
                    out["errors"].append(f"Shikimori · {a.name}: {e}")
        except AuthExpired:
            out["expired"].append("shikimori")
    return out
