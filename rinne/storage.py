"""JSON persistence under the XDG data/cache directories."""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import APP_NAME, LEGACY_APP_NAMES
from .models import Anime, Settings, WeekPlan


def _app_dir(base: Path) -> Path:
    """<base>/rinne, moving a folder from an older app name into place on first use."""
    path = base / APP_NAME
    if not path.exists():
        for legacy in LEGACY_APP_NAMES:
            old = base / legacy
            if old.is_dir():
                try:
                    shutil.move(str(old), str(path))
                except OSError:
                    shutil.copytree(old, path, dirs_exist_ok=True)
                break
    path.mkdir(parents=True, exist_ok=True)
    return path


def _base(xdg_var: str, windows_var: str, linux_default: Path) -> Path:
    """XDG variables win everywhere (tests rely on this); otherwise the platform's usual place:
    %APPDATA% / %LOCALAPPDATA% on Windows, ~/.local/share and ~/.cache on Linux."""
    if os.environ.get(xdg_var):
        return Path(os.environ[xdg_var])
    if sys.platform == "win32" and os.environ.get(windows_var):
        return Path(os.environ[windows_var])
    return linux_default


def data_dir() -> Path:
    return _app_dir(_base("XDG_DATA_HOME", "APPDATA", Path.home() / ".local" / "share"))


def cache_dir() -> Path:
    return _app_dir(_base("XDG_CACHE_HOME", "LOCALAPPDATA", Path.home() / ".cache"))


@dataclass
class State:
    library: dict[int, Anime] = field(default_factory=dict)
    settings: Settings = field(default_factory=Settings)
    week: WeekPlan | None = None
    notified: dict[int, int] = field(default_factory=dict)  # mal_id -> last episode announced
    last_reminder: str = ""  # ISO date of the last daily reminder
    onboarded: bool = False  # has seen the welcome hub

    def to_dict(self) -> dict:
        return {
            "library": [a.to_dict() for a in self.library.values()],
            "settings": self.settings.to_dict(),
            "week": self.week.to_dict() if self.week else None,
            "notified": {str(k): v for k, v in self.notified.items()},
            "last_reminder": self.last_reminder,
            "onboarded": self.onboarded,
        }

    @classmethod
    def from_dict(cls, d: dict) -> State:
        library = {a["mal_id"]: Anime.from_dict(a) for a in d.get("library", [])}
        settings = Settings.from_dict(d.get("settings", {}))
        week = WeekPlan.from_dict(d["week"]) if d.get("week") else None
        notified = {int(k): v for k, v in (d.get("notified") or {}).items()}
        return cls(library, settings, week, notified, d.get("last_reminder", ""),
                   bool(d.get("onboarded", False)))


def state_path() -> Path:
    return data_dir() / "state.json"


def load_state(path: Path | None = None) -> State:
    path = path or state_path()
    if not path.exists():
        return State()
    with path.open(encoding="utf-8") as f:
        return State.from_dict(json.load(f))


def save_state(state: State, path: Path | None = None) -> None:
    path = path or state_path()
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, indent=1)
    tmp.replace(path)
