#!/usr/bin/env bash
# Install and launch the APK on a running emulator; save a screenshot, the log and a status.
# (Used by CI. The emulator action runs each script line in a new shell, hence a file.)
set -uo pipefail
adb install -r apk/*.apk
pkg=$(adb shell pm list packages | grep -i rinne | head -1 | sed 's/package://' | tr -d '\r')
echo "package: $pkg"
adb logcat -c
adb shell monkey -p "$pkg" -c android.intent.category.LAUNCHER 1
for t in 20 45 75; do
  sleep $(( t - ${prev:-0} )); prev=$t
  adb exec-out screencap -p > "screen-${t}s.png"
done
adb logcat -d > logcat.txt
grep -iE "python|rinne|Traceback|Error|qt\b|libc.*fatal" logcat.txt | tail -300 > logcat-app.txt || true
if adb shell pidof "$pkg" >/dev/null; then echo "RUNNING" > status.txt; else echo "NOT RUNNING" > status.txt; fi
cat status.txt
