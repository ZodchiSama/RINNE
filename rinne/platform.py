"""Which platform Rinne is running on, for the few places that differ."""

from __future__ import annotations

import os
import sys


def is_android() -> bool:
    # Python 3.13+ reports "android"; python-for-android's 3.11 reports "linux" but sets these.
    return sys.platform == "android" or "ANDROID_ARGUMENT" in os.environ or "ANDROID_PRIVATE" in os.environ


def is_windows() -> bool:
    return sys.platform == "win32"


def android_private_dir() -> str | None:
    """The app's private storage folder on Android (python-for-android sets this)."""
    return os.environ.get("ANDROID_PRIVATE") or os.environ.get("ANDROID_APP_PATH")
