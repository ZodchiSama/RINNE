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
python -m buildozer init
python "$root/packaging/android/configure.py" buildozer.spec "$version"

# 1) create pysidedeploy.spec (also downloads the NDK the tool expects)
pyside6-android-deploy --init --name Rinne --wheel-pyside "$wheel_pyside" --wheel-shiboken "$wheel_shiboken" -f
python - <<PY
import configparser
c = configparser.ConfigParser(comment_prefixes="#", allow_no_value=True)
c.read("pysidedeploy.spec")
c["app"]["icon"] = "$stage/rinne/assets/icon-512.png"
c["buildozer"]["arch"] = "aarch64"
c["buildozer"]["mode"] = "debug"
with open("pysidedeploy.spec", "w") as f:
    c.write(f)
PY
# 2) build the APK
pyside6-android-deploy -c pysidedeploy.spec --ndk-path "$ndk_dir" -f
apk="$(find "$stage" -maxdepth 2 -name '*.apk' | head -1)"
mkdir -p "$root/dist"
cp "$apk" "$root/dist/Rinne-$version-android-arm64.apk"
echo "Built dist/Rinne-$version-android-arm64.apk"
