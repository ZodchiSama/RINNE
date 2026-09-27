"""Set Rinne's options in the buildozer.spec that Qt's Android deploy tool uses.

    python configure.py buildozer.spec <version>
"""

import re
import sys
from pathlib import Path

spec, version = Path(sys.argv[1]), sys.argv[2]
values = {
    "version": version,
    "orientation": "portrait",
    "fullscreen": "0",
    "android.api": "35",
    "android.minapi": "28",  # Qt 6 for Android needs Android 9+
    "android.accept_sdk_license": "True",
    "android.presplash_color": "#0E1016",
    "android.allow_backup": "True",
    "log_level": "2",
}
lines = spec.read_text().splitlines()
section, seen = None, set()
for i, line in enumerate(lines):
    m = re.match(r"\s*\[(\w+)\]", line)
    if m:
        section = m.group(1)
        continue
    for key, value in values.items():
        target = "buildozer" if key == "log_level" else "app"
        if section == target and re.match(rf"\s*#?\s*{re.escape(key)}\s*=", line) and key not in seen:
            lines[i] = f"{key} = {value}"
            seen.add(key)
missing = [k for k in values if k not in seen]
if missing:  # append anything the template didn't mention to [app]
    idx = lines.index("[app]") + 1
    for key in missing:
        lines.insert(idx, f"{key} = {values[key]}")
spec.write_text("\n".join(lines) + "\n")
print(f"configured {spec}: " + ", ".join(f"{k}={v}" for k, v in values.items()))
