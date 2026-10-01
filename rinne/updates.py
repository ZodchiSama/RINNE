"""Checking GitHub for a newer Rinne release."""

from __future__ import annotations

import json
import re
import urllib.request

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
            "name": data.get("name") or ""}


def check() -> dict | None:
    """The newest release if it's newer than this one, else None."""
    rel = latest_release()
    return rel if rel["version"] and is_newer(rel["version"]) else None
