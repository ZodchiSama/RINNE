#!/usr/bin/env bash
# Builds the Rinne APK with Qt's pyside6-android-deploy (python-for-android + buildozer).
# Run from the repository root with Python 3.11, Java 17 and the Android wheels in $WHEELS.
set -euo pipefail

root="$(pwd)"
version="$(python -c 'import rinne; print(rinne.__version__)')"
stage="$root/build/android"
ndk_dir="$HOME/.pyside6_android_deploy/android-ndk/android-ndk-r27c"
wheel_pyside="$(ls "$WHEELS"/PySide6-*android_aarch64.whl)"
wheel_shiboken="$(ls "$WHEELS"/shiboken6-*android_aarch64.whl)"

# A clean source folder: only the app, not tests/tools/artwork sources.
rm -rf "$stage"
mkdir -p "$stage"
cp main.py "$stage/"
cp -r rinne "$stage/"
find "$stage" -name "__pycache__" -prune -exec rm -rf {} +
rm -f "$stage/rinne/assets/icon.ico"
python packaging/android/make_cacerts.py "$stage/rinne/_cacerts.py"

cd "$stage"
# 1) Let Qt's tool prepare everything (NDK, PySide6 recipes, jars, Qt libs, permissions) and
#    write buildozer.spec. --init stops before building; the tool wipes buildozer.spec at the
#    start of every run, so the build itself is run with buildozer directly (step 3).
pyside6-android-deploy --init --name Rinne --wheel-pyside "$wheel_pyside" --wheel-shiboken "$wheel_shiboken" \
  --keep-deployment-files -f
# 2) Rinne's own settings on top
python "$root/packaging/android/configure.py" buildozer.spec "$version" "$stage/rinne/assets/icon-512.png"
echo "--- buildozer settings used:"
grep -E "^(version|title|package\.(name|domain)|icon\.filename|android\.(api|minapi|archs|accept_sdk_license|permissions|ndk_path)|requirements|p4a\.(bootstrap|extra_args)) =" buildozer.spec
# 3) build
python -m buildozer android debug
apk="$(find "$stage" -maxdepth 2 -name '*.apk' | head -1)"
mkdir -p "$root/dist"
cp "$apk" "$root/dist/Rinne-$version-android-arm64.apk"
echo "Built dist/Rinne-$version-android-arm64.apk"
