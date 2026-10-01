"""Interface translations.

Strings shown in the interface are wrapped in _("English text"), or N_("…") for constants defined
before the language is loaded (translate them with _() when shown). The Settings page helpers
(_header, _group, _row, _switch, _button) translate their text themselves.

A translation is a JSON file in rinne/locale/<code>.json that maps each English string to its
translation, plus "_language" with the language's own name:

    {"_language": "Español", "Your Week": "Tu semana", "Up Next": "A continuación"}

Missing or empty entries fall back to English, so a partial catalog is fine.
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


def _(text: str) -> str:
    return _catalog.get(text) or text


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
    global current, _catalog
    if code in ("", "auto"):
        code = system_language()
    codes = available()
    if code not in codes:
        code = code.split("_")[0]  # pt_BR → pt
    if code not in codes or code == "en":
        current, _catalog = "en", {}
        return current
    try:
        data = json.loads((LOCALE_DIR / f"{code}.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        current, _catalog = "en", {}
        return current
    current = code
    _catalog = {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, str) and v}
    return current
