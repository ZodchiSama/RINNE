"""Embed certifi's CA bundle as a Python module for the Android build.

Android's Python has no system certificate store it can read, and the Qt deploy tool only
installs PySide6, so the trusted-roots list ships inside Rinne as rinne/_cacerts.py.

    python packaging/android/make_cacerts.py build/android/rinne/_cacerts.py
"""

import sys
from pathlib import Path

import certifi

pem = Path(certifi.where()).read_text(encoding="ascii")
out = Path(sys.argv[1])
out.write_text(f'"""Mozilla CA bundle from certifi {certifi.__version__} (generated)."""\n\n'
               f"PEM = {pem!r}\n", encoding="ascii")
print(f"wrote {out} ({len(pem) // 1024} KB of certificates)")
