"""Interface translations.

Strings shown in the interface are wrapped in _("English text"), or N_("…") for constants defined
before the language is loaded (translate them with _() when shown). The Settings page helpers
(_header, _group, _row, _switch, _button) translate their text themselves.

A translation is a JSON file in rinne/locale/<code>.json that maps each English string to its
translation, plus "_language" with the language's own name:

    {"_language": "Español", "Your Week": "Tu semana", "Up Next": "A continuación"}

Missing or empty entries fall back to English, so a partial catalog is fine.

Counts use _n("{n} episode", "{n} episodes", n). In a catalog, its entry (keyed by the singular)
is a list of forms in the language's plural order, e.g. Russian one / few / many:

    "{n} episode": ["{n} эпизод", "{n} эпизода", "{n} эпизодов"]

Dates go through strftime() below, so month and weekday names are translated too.
`python tools/extract_strings.py` lists every wrapped string in rinne/locale/template.json and adds
new ones to existing catalogs. The language is picked in Settings → General (needs a restart).
"""

from __future__ import annotations

import json
import locale
import os
from pathlib import Path

LOCALE_DIR = Path(__file__).resolve().parent / "locale"

current = "en"
_catalog: dict[str, str] = {}
_plurals: dict[str, list[str]] = {}

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _(text: str) -> str:
    return _catalog.get(text) or text


def _plural_index(n: int) -> int:
    """Which plural form n takes in the current language."""
    n = abs(int(n))
    if current.split("_")[0] in ("ru", "uk", "be"):  # one / few / many
        if n % 10 == 1 and n % 100 != 11:
            return 0
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return 1
        return 2
    return 0 if n == 1 else 1


def _n(singular: str, plural: str, n: int, **values) -> str:
    """A count, in the right plural form, with {n} (and any other placeholders) filled in."""
    forms = _plurals.get(singular)
    if forms:
        text = forms[min(_plural_index(n), len(forms) - 1)]
    else:
        text = singular if n == 1 else plural
    return text.format(n=n, **values)


def month_name(month: int, short: bool = False, in_date: bool = False) -> str:
    """`in_date`: written with a day ("7 October"), which some languages inflect (7 октября)."""
    name = MONTHS[month - 1]
    if short:
        return _(name[:3])
    return (_(f"{name} (in a date)") if in_date and _catalog.get(f"{name} (in a date)") else _(name))


def weekday_name(weekday: int, short: bool = False) -> str:
    name = WEEKDAYS[weekday]
    return _(name[:3]) if short else _(name)


def strftime(d, fmt: str) -> str:
    """date.strftime, with month and weekday names (%b %B %a %A) in the interface language."""
    fmt = (fmt.replace("%B", "\x00B").replace("%b", "\x00b").replace("%A", "\x00A").replace("%a", "\x00a"))
    out = d.strftime(fmt.replace("\x00", "%%\x00"))
    in_date = "%d" in fmt or "%-d" in fmt or "%e" in fmt
    return (out.replace("%\x00B", month_name(d.month, in_date=in_date)).replace("%\x00b", month_name(d.month, True))
               .replace("%\x00A", weekday_name(d.weekday())).replace("%\x00a", weekday_name(d.weekday(), True)))


SEASONS = {"WINTER": "Winter", "SPRING": "Spring", "SUMMER": "Summer", "FALL": "Fall"}


def season_name(season: str) -> str:
    """An anime season (AniList's WINTER / SPRING / SUMMER / FALL) in the interface language."""
    name = SEASONS.get((season or "").upper())
    return _(name) if name else (season or "").title()


def date_keys() -> list[str]:
    """Catalog keys used by dates (for tools/extract_strings.py)."""
    keys = []
    for m in MONTHS:
        keys += [m, m[:3], f"{m} (in a date)"]
    for w in WEEKDAYS:
        keys += [w, w[:3]]
    return keys + list(SEASONS.values())


def N_(text: str) -> str:
    """Marks a string for translation without translating it yet (for module-level constants)."""
    return text


def available() -> dict[str, str]:
    """{code: language name} for English and every catalog found."""
    out = {"en": "English"}
    for path in sorted(LOCALE_DIR.glob("*.json")):
        if path.stem == "template":
            continue
        try:
            out[path.stem] = json.loads(path.read_text(encoding="utf-8")).get("_language") or path.stem
        except (OSError, json.JSONDecodeError):
            continue
    return out


def system_language() -> str:
    """The system's language code, e.g. "es" or "pt_BR"; "en" if unknown."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value and value not in ("C", "POSIX"):
            return value.split(".")[0]
    try:
        return (locale.getlocale()[0] or "en").split(".")[0]
    except ValueError:
        return "en"


def set_language(code: str) -> str:
    """Load a catalog ("auto" = the system language). Returns the code actually used."""
    global current, _catalog, _plurals
    if code in ("", "auto"):
        code = system_language()
    codes = available()
    if code not in codes:
        code = code.split("_")[0]  # pt_BR → pt
    current, _catalog, _plurals = "en", {}, {}
    if code not in codes or code == "en":
        return current
    try:
        data = json.loads((LOCALE_DIR / f"{code}.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return current
    current = code
    _catalog = {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, str) and v}
    _plurals = {k: v for k, v in data.items()
                if not k.startswith("_") and isinstance(v, list) and v and all(isinstance(f, str) and f for f in v)}
    return current
