"""Collect every _("…") string in the app into rinne/locale/template.json, and add new strings
to the existing catalogs (with an empty translation, which falls back to English).

    python tools/extract_strings.py          # update template.json and the catalogs
    python tools/extract_strings.py --check  # exit 1 if template.json is out of date (for CI)
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "rinne"
LOCALE = SRC / "locale"


# Settings page helpers that translate their own text: method name → how many leading args are text.
HELPERS = {"_header": 2, "_group": 1, "_row": 2, "_switch": 2, "_button": 1}


def _text_args(node: ast.Call) -> list[ast.expr]:
    f = node.func
    if isinstance(f, ast.Name) and f.id in ("_", "N_"):
        return node.args[:1]
    if isinstance(f, ast.Attribute) and f.attr in HELPERS:
        return node.args[:HELPERS[f.attr]]
    return []


def _constant(node: ast.expr) -> str | None:
    """A literal string, including implicitly concatenated ones ("a" "b") and "a" + "b"."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _constant(node.left), _constant(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def strings() -> list[str]:
    found: set[str] = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for arg in _text_args(node):
                    text = _constant(arg)
                    if text:
                        found.add(text)
    return sorted(found, key=str.lower)


def write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    found = strings()
    template = {"_language": "", **{s: "" for s in found}}
    tpath = LOCALE / "template.json"
    if "--check" in sys.argv:
        current = json.loads(tpath.read_text(encoding="utf-8")) if tpath.exists() else {}
        if current != template:
            print("rinne/locale/template.json is out of date: run python tools/extract_strings.py")
            return 1
        return 0
    LOCALE.mkdir(exist_ok=True)
    write(tpath, template)
    print(f"{len(found)} strings → {tpath.relative_to(ROOT)}")
    for path in sorted(LOCALE.glob("*.json")):
        if path.name == "template.json":
            continue
        catalog = json.loads(path.read_text(encoding="utf-8"))
        merged = {"_language": catalog.get("_language", "")}
        merged.update({s: catalog.get(s, "") for s in found})
        unused = [k for k in catalog if not k.startswith("_") and k not in merged]
        done = sum(1 for s in found if merged[s])
        write(path, merged)
        print(f"{path.name}: {done}/{len(found)} translated" + (f", dropped {len(unused)} unused" if unused else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
