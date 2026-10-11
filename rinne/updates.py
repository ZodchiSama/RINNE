"""Checking GitHub for a newer Rinne release."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from . import USER_AGENT, __version__

LATEST_URL = "https://api.github.com/repos/ZodchiSama/RINNE/releases/latest"


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.2.3' / '1.2' → (1, 2, 3) / (1, 2, 0); anything non-numeric after the digits is ignored."""
    nums = [int(n) for n in re.findall(r"\d+", text.split("-")[0])[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def is_newer(candidate: str, current: str = __version__) -> bool:
    return parse_version(candidate) > parse_version(current)


def latest_release(timeout: float = 15) -> dict:
    """{"version": "1.0.1", "url": <release page>, "name": ...} for the newest published release."""
    req = urllib.request.Request(LATEST_URL, headers={"User-Agent": USER_AGENT,
                                                      "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return {"version": (data.get("tag_name") or "").lstrip("v"), "url": data.get("html_url", ""),
            "name": data.get("name") or "", "notes": (data.get("body") or "")[:4000],
            "assets": [{"name": a.get("name", ""), "url": a.get("browser_download_url", ""),
                        "size": a.get("size") or 0, "digest": a.get("digest") or ""}
                       for a in data.get("assets") or []]}


def managed_by() -> str:
    """Who updates this copy of Rinne, if not Rinne itself: "Flatpak", "your package manager"
    (AUR and other distro packages), or "" for the AppImage, Windows builds and source installs."""
    if os.environ.get("FLATPAK_ID") or Path("/.flatpak-info").exists():
        return "Flatpak"
    if getattr(sys, "frozen", False) or sys.platform == "win32":
        return ""
    if sys.prefix == sys.base_prefix and Path(__file__).resolve().is_relative_to("/usr"):
        return "your package manager"
    return ""


def check() -> dict | None:
    """The newest release if it's newer than this one, else None."""
    rel = latest_release()
    return rel if rel["version"] and is_newer(rel["version"]) else None


# --------------------------------------------------------------------------- updating in place


def install_kind() -> str:
    """How this copy can update itself: "appimage", "windows-installer", "windows-portable", or ""
    (source installs and package-managed copies, which update another way)."""
    if managed_by():
        return ""
    if os.environ.get("APPIMAGE") and Path(os.environ["APPIMAGE"]).is_file():
        return "appimage"
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        return "windows-portable" if Path(sys.executable).name.lower().startswith("rinne-portable") \
            else "windows-installer"
    return ""


def pick_asset(release: dict, kind: str) -> dict | None:
    """The release file for this kind of install."""
    want = {"appimage": lambda n: n.endswith("-x86_64.AppImage"),
            "windows-installer": lambda n: n.startswith("Rinne-Setup-") and n.endswith(".exe"),
            "windows-portable": lambda n: n.startswith("Rinne-Portable-") and n.endswith(".exe")}.get(kind)
    return next((a for a in release.get("assets") or [] if want and want(a["name"])), None)


def download(asset: dict, progress=None, should_stop=None) -> Path:
    """Download a release file to a temporary folder, checking its size and SHA-256 (GitHub's
    digest). Returns the path; raises on any mismatch, so a broken download is never installed."""
    folder = Path(tempfile.mkdtemp(prefix="rinne-update-"))
    dest = folder / asset["name"]
    req = urllib.request.Request(asset["url"], headers={"User-Agent": USER_AGENT})
    sha = hashlib.sha256()
    done = 0
    with urllib.request.urlopen(req, timeout=60) as resp, dest.open("wb") as out:
        total = int(resp.headers.get("Content-Length") or asset.get("size") or 0)
        while chunk := resp.read(1 << 16):
            if should_stop and should_stop():
                raise InterruptedError("Update cancelled")
            out.write(chunk)
            sha.update(chunk)
            done += len(chunk)
            if progress:
                progress(done // 1024, max(1, total // 1024), f"Downloading {asset['name']}…")
    if asset.get("size") and done != asset["size"]:
        raise OSError(f"Download incomplete ({done} of {asset['size']} bytes)")
    digest = asset.get("digest") or ""
    if digest.startswith("sha256:") and sha.hexdigest() != digest.split(":", 1)[1]:
        raise OSError("The download doesn't match the release (checksum mismatch)")
    return dest


def apply_update(kind: str, downloaded: Path) -> list[str]:
    """Put the downloaded update in place. Returns the command that starts the new version (the
    caller runs it and quits)."""
    if kind == "appimage":
        current = Path(os.environ["APPIMAGE"])
        staged = current.with_name(current.name + ".new")
        shutil.copyfile(downloaded, staged)
        staged.chmod(0o755)
        os.replace(staged, current)  # same path, so app-menu entries keep working
        return [str(current)]
    if kind == "windows-portable":
        current = Path(sys.executable)
        old = current.with_name(current.name + ".old")
        old.unlink(missing_ok=True)
        os.replace(current, old)  # Windows lets a running exe be renamed, not overwritten
        shutil.copyfile(downloaded, current)
        return [str(current)]
    if kind == "windows-installer":
        # Inno Setup, quietly; it closes this copy and starts the new one when done.
        return [str(downloaded), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]
    raise ValueError(f"Can't update a {kind or 'source'} install in place")


def cleanup_old_portable() -> None:
    """Remove the previous portable exe left beside the new one after an update."""
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        Path(sys.executable + ".old").unlink(missing_ok=True)


def launch(command: list[str]) -> None:
    """Start the new version (or the installer), detached from this process."""
    kwargs = {"close_fds": True}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(command, **kwargs)
