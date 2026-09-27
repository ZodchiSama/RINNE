#!/usr/bin/env bash
# Installs Rinne for the current user: a venv in this folder, the `rinne` command in
# ~/.local/bin, the app icon, and an entry in your application menu.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
bin_dir="${HOME}/.local/bin"
share="${XDG_DATA_HOME:-$HOME/.local/share}"
apps_dir="$share/applications"
icons_dir="$share/icons/hicolor"

if [ ! -d "$here/.venv" ]; then
    python3 -m venv "$here/.venv"
fi
"$here/.venv/bin/pip" install -q --upgrade pip
"$here/.venv/bin/pip" install -q -e "$here"

# Remove the launcher and menu entry from when the app was called Smart Watchlist.
rm -f "$bin_dir/smart-watchlist" "$apps_dir/smart-watchlist.desktop"

mkdir -p "$bin_dir" "$apps_dir"
ln -sf "$here/.venv/bin/rinne" "$bin_dir/rinne"

for size in 16 24 32 48 64 128 256 512; do
    mkdir -p "$icons_dir/${size}x${size}/apps"
    cp "$here/rinne/assets/icon-$size.png" "$icons_dir/${size}x${size}/apps/rinne.png"
done

cat > "$apps_dir/rinne.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Rinne
GenericName=Anime Planner
Comment=Weekly anime schedule that follows each series
Exec="$here/.venv/bin/rinne"
Icon=rinne
Terminal=false
Categories=AudioVideo;Video;
Keywords=anime;mal;myanimelist;anilist;schedule;watchlist;
StartupWMClass=rinne
EOF

update-desktop-database "$apps_dir" 2>/dev/null || true
gtk-update-icon-cache -f -t "$icons_dir" 2>/dev/null || true

echo "Installed. Launch 'Rinne' from your app menu, or run: rinne"
