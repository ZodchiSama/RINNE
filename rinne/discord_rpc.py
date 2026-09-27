"""Minimal Discord Rich Presence client over Discord's local IPC socket (no dependencies).

Protocol: frames of <opcode:uint32 LE><length:uint32 LE><JSON>. Opcode 0 is the handshake
{"v": 1, "client_id": …}; opcode 1 carries commands such as SET_ACTIVITY.
"""

from __future__ import annotations

import json
import os
import socket
import struct
import time
import uuid
from pathlib import Path

OP_HANDSHAKE, OP_FRAME, OP_CLOSE = 0, 1, 2
ACTIVITY_WATCHING = 3


def socket_paths() -> list[Path]:
    """Where Discord (native, Flatpak or Snap) puts its IPC socket."""
    bases = []
    for var in ("XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP"):
        if os.environ.get(var):
            bases.append(Path(os.environ[var]))
    bases.append(Path("/tmp"))
    subdirs = ["", "app/com.discordapp.Discord", "app/com.discordapp.DiscordCanary",
               "snap.discord", "snap.discord-canary", ".flatpak/dev.vencord.Vesktop/xdg-run"]
    paths = []
    for base in bases:
        for sub in subdirs:
            for i in range(10):
                paths.append(base / sub / f"discord-ipc-{i}")
    return paths


class DiscordRPC:
    def __init__(self, client_id: str):
        self.client_id = client_id.strip()
        self.sock: socket.socket | None = None
        self.last_error = ""

    @property
    def connected(self) -> bool:
        return self.sock is not None

    def connect(self) -> bool:
        if self.sock is not None:
            return True
        if not self.client_id.isdigit():
            self.last_error = "Set a Discord Application ID first."
            return False
        for path in socket_paths():
            if not path.exists():
                continue
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(2)
            try:
                s.connect(str(path))
                self.sock = s
                self._send(OP_HANDSHAKE, {"v": 1, "client_id": self.client_id})
                op, data = self._recv()
                if op == OP_CLOSE or data.get("evt") == "ERROR":
                    raise ConnectionError(data.get("message") or data.get("data", {}).get("message")
                                          or "Discord rejected the Application ID")
                self.last_error = ""
                return True
            except (OSError, ConnectionError, ValueError) as e:
                self.last_error = str(e) or type(e).__name__
                self._drop()
        if not self.last_error:
            self.last_error = "Discord isn't running (no IPC socket found)."
        return False

    def set_activity(self, activity: dict | None) -> bool:
        """Show `activity` (None clears it). Returns False if Discord isn't reachable."""
        if not self.connect():
            return False
        payload = {"cmd": "SET_ACTIVITY", "args": {"pid": os.getpid(), "activity": activity},
                   "nonce": str(uuid.uuid4())}
        try:
            self._send(OP_FRAME, payload)
            _, reply = self._recv()
            if reply.get("evt") == "ERROR":
                self.last_error = reply.get("data", {}).get("message", "Discord returned an error")
                return False
            return True
        except (OSError, ValueError) as e:
            self.last_error = str(e) or type(e).__name__
            self._drop()
            return False

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.set_activity(None)
                self._send(OP_CLOSE, {})
            except OSError:
                pass
        self._drop()

    # ------------------------------------------------------------------ framing

    def _send(self, op: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.sock.sendall(struct.pack("<II", op, len(data)) + data)

    def _recv(self) -> tuple[int, dict]:
        header = self._read_exact(8)
        op, length = struct.unpack("<II", header)
        body = self._read_exact(length)
        return op, json.loads(body.decode() or "{}")

    def _read_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Discord closed the connection")
            buf += chunk
        return buf

    def _drop(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None


def build_activity(show_title: str | None, details: str, state: str, cover_url: str = "",
                   mal_id: int = 0, buttons: bool = True, started: float | None = None,
                   logo_key: str = "rinne") -> dict:
    """A "Watching" activity. Discord accepts https image URLs as asset keys."""
    act: dict = {"type": ACTIVITY_WATCHING, "details": details[:128] or "Rinne", "state": state[:128] or None,
                 "assets": {}, "timestamps": {"start": int(started or time.time())}}
    if cover_url.startswith("https://"):
        act["assets"]["large_image"] = cover_url
        act["assets"]["large_text"] = (show_title or "Rinne")[:128]
        act["assets"]["small_image"] = logo_key
        act["assets"]["small_text"] = "Rinne — weekly anime planner"
    else:
        act["assets"]["large_image"] = logo_key
        act["assets"]["large_text"] = "Rinne — weekly anime planner"
    if buttons and mal_id:
        act["buttons"] = [{"label": "View on MyAnimeList", "url": f"https://myanimelist.net/anime/{mal_id}"}]
    if act["state"] is None:
        del act["state"]
    return act
