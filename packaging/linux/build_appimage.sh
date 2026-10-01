#!/usr/bin/env bash
# Builds dist/Rinne-<version>-x86_64.AppImage: PyInstaller freezes the app, then appimagetool
# packs it with a desktop entry, icons and AppStream metadata.
# Run from the repository root in an environment with Rinne's dev dependencies installed.
set -euo pipefail

root="$(pwd)"
version="$(python -c 'import rinne; print(rinne.__version__)')"
arch="x86_64"
build="$root/build/appimage"
appdir="$build/Rinne.AppDir"
out="$root/dist/Rinne-$version-$arch.AppImage"
tool="$build/appimagetool-$arch.AppImage"

rm -rf "$build" && mkdir -p "$build" "$root/dist"

# 1) Freeze. --paths . : the package is installed in editable mode, which PyInstaller can't follow.
pyinstaller --noconfirm --log-level WARN --windowed --name Rinne --paths "$root" \
  --add-data "$root/rinne/assets:rinne/assets" \
  --add-data "$root/rinne/locale:rinne/locale" \
  --distpath "$build/dist" --workpath "$build/work" --specpath "$build" \
  "$root/packaging/windows/launcher.py"

# 2) Trim Qt parts Rinne never uses (on-screen keyboard, QML/Quick, PDF), which PyInstaller pulls
#    in through plugins. Saves a lot of space; the self-test below checks nothing needed went.
qt="$build/dist/Rinne/_internal/PySide6/Qt"
rm -rf "$qt/plugins/platforminputcontexts/libqtvirtualkeyboardplugin.so" \
       "$qt/plugins/imageformats/libqpdf.so" "$qt/qml" "$qt/translations"
rm -f "$qt"/lib/libQt6{VirtualKeyboard,Quick,QuickTemplates2,QuickControls2,QuickControls2Impl,QuickLayouts,QmlModels,QmlWorkerScript,QmlMeta,Qml,Pdf}.so.6

# 3) AppDir layout
mkdir -p "$appdir/usr/lib" "$appdir/usr/share/applications" "$appdir/usr/share/metainfo"
cp -r "$build/dist/Rinne" "$appdir/usr/lib/rinne"
cat > "$appdir/AppRun" <<'RUN'
#!/bin/sh
here="$(dirname "$(readlink -f "$0")")"
exec "$here/usr/lib/rinne/Rinne" "$@"
RUN
chmod +x "$appdir/AppRun"
cat > "$appdir/rinne.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Rinne
GenericName=Anime Planner
Comment=Weekly anime schedule that follows each series
Exec=Rinne
Icon=rinne
Terminal=false
Categories=AudioVideo;Video;
Keywords=anime;mal;myanimelist;anilist;schedule;watchlist;
StartupWMClass=rinne
X-AppImage-Version=$version
DESK
cp "$appdir/rinne.desktop" "$appdir/usr/share/applications/rinne.desktop"
for size in 16 24 32 48 64 128 256 512; do
  mkdir -p "$appdir/usr/share/icons/hicolor/${size}x${size}/apps"
  cp "$root/rinne/assets/icon-$size.png" "$appdir/usr/share/icons/hicolor/${size}x${size}/apps/rinne.png"
done
cp "$root/rinne/assets/icon-256.png" "$appdir/rinne.png"
ln -sf rinne.png "$appdir/.DirIcon"
sed -e "s/@VERSION@/$version/" -e "s/@DATE@/$(date -u +%F)/" "$root/packaging/linux/rinne.appdata.xml" \
  > "$appdir/usr/share/metainfo/io.github.zodchisama.rinne.appdata.xml"

# 4) Pack (with update info so AppImage updaters can fetch new releases from GitHub)
if [ ! -x "$tool" ]; then
  curl -fsSL -o "$tool" \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$arch.AppImage"
  chmod +x "$tool"
fi
rm -f "$out" "$out.zsync"
ARCH="$arch" APPIMAGE_EXTRACT_AND_RUN=1 "$tool" --no-appstream \
  -u "gh-releases-zsync|ZodchiSama|RINNE|latest|Rinne-*-$arch.AppImage.zsync" \
  "$appdir" "$out"
[ -f "$(basename "$out").zsync" ] && mv "$(basename "$out").zsync" "$out.zsync"
echo "Built $out ($(du -h "$out" | cut -f1))"
