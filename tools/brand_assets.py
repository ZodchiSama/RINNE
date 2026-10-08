"""Build the app's icons and logos in rinne/assets/ from the brand kit in brand/.

    python tools/brand_assets.py

Needs Pillow (a dev dependency). Run it again whenever the brand kit changes.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "brand"
OUT = ROOT / "rinne" / "assets"


def fit(src: Path, dest: Path, size: int, by: str = "max") -> None:
    """Copy a PNG, scaled down so its largest side (or its width) is at most `size`."""
    im = Image.open(src).convert("RGBA")
    scale = size / (max(im.size) if by == "max" else im.width)
    if scale < 1:
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    im.save(dest, optimize=True)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    icons = BRAND / "app-icon"
    # App icon: window, taskbar, tray, notifications, desktop entry, AppImage, Windows exe.
    for size in (16, 24, 32, 48, 64, 128, 256, 512, 1024):
        shutil.copyfile(icons / f"rinne-icon-{size}.png", OUT / f"icon-{size}.png")
    shutil.copyfile(icons / "rinne-icon-512.png", OUT / "icon.png")
    shutil.copyfile(icons / "rinne-icon.ico", OUT / "icon.ico")
    # The wheel, for inside the app; the simple one is for small sizes (48 px and under).
    for mode in ("dark", "light"):
        fit(BRAND / "mark" / f"rinne-mark-{mode}-mode.png", OUT / f"mark-{mode}.png", 512)
        fit(BRAND / "mark" / f"rinne-mark-simple-{mode}-mode.png", OUT / f"mark-simple-{mode}.png", 192)
        fit(BRAND / "title" / f"rinne-title-kanji-{mode}-mode.png", OUT / f"title-{mode}.png", 960, by="width")
    for old in ("logo-round.png",):  # replaced by the mark
        (OUT / old).unlink(missing_ok=True)
    print("\n".join(sorted(f"{p.name:24s} {p.stat().st_size // 1024:5d} KB" for p in OUT.iterdir())))


if __name__ == "__main__":
    main()
