"""Exporting the plan as an iCalendar (.ics) file for calendar apps."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import artwork, models, scheduler
from .storage import State, data_dir

PRODID = "-//Zodchi//Rinne//EN"


def _escape(text: str) -> str:
    """Escape text for an iCalendar property value (RFC 5545 §3.3.11)."""
    backslash = chr(92)
    for ch in (backslash, ";", ","):
        text = text.replace(ch, backslash + ch)
    return text.replace("\r\n", backslash + "n").replace("\n", backslash + "n")


def _fold(line: str) -> list[str]:
    """RFC 5545: lines longer than 75 octets continue on the next line after a space."""
    out, raw = [], line.encode("utf-8")
    while len(raw) > 75:
        cut = 75 if not out else 74
        while cut > 0 and (raw[cut] & 0xC0) == 0x80:  # don't split a UTF-8 character
            cut -= 1
        out.append(raw[:cut].decode("utf-8"))
        raw = raw[cut:]
    out.append(raw.decode("utf-8"))
    return [out[0]] + [" " + part for part in out[1:]]


def build_ics(state: State, now: datetime | None = None) -> str:
    """One all-day event per show per day of the current plan."""
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:Rinne — anime plan"]
    week, start = state.week, scheduler.plan_start(state)
    if week and start:
        groups: dict[tuple[int, int], list] = {}
        for it in week.items:
            groups.setdefault((it.day, it.mal_id), []).append(it)
        for (day, mal_id), its in groups.items():
            anime = state.library.get(mal_id)
            if anime is None:
                continue
            on = start + timedelta(days=day)
            eps = [i.episode for i in its]
            span = f"Ep {eps[0]}" if len(eps) == 1 else f"Ep {eps[0]}–{eps[-1]}"
            details = artwork.episodes(anime)
            desc = []
            for i in its:
                title = artwork.episode_title(details.get(str(i.episode)) or {}, models.title_language)
                desc.append(f"{'✓' if i.done else '•'} Episode {i.episode}" + (f": {title}" if title else ""))
            if anime.streaming:
                desc.append(f"Watch on {anime.streaming[0]['site']}: {anime.streaming[0]['url']}")
            desc.append(f"https://myanimelist.net/anime/{mal_id}")
            lines += [
                "BEGIN:VEVENT",
                f"UID:{on.isoformat()}-{mal_id}@rinne",
                f"DTSTAMP:{stamp}",
                f"DTSTART;VALUE=DATE:{on:%Y%m%d}",
                f"DTEND;VALUE=DATE:{on + timedelta(days=1):%Y%m%d}",
                f"SUMMARY:{_escape(f'{anime.name} — {span}')}",
                f"DESCRIPTION:{_escape(chr(10).join(desc))}",
                "TRANSP:TRANSPARENT",
                "END:VEVENT",
            ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(part for line in lines for part in _fold(line)) + "\r\n"


def calendar_path() -> Path:
    return data_dir() / "rinne-plan.ics"


def write(state: State, path: Path | None = None) -> Path:
    path = path or calendar_path()
    path.write_text(build_ics(state), encoding="utf-8", newline="")
    return path
