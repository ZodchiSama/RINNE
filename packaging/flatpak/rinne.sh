#!/bin/sh
# Flatpak launcher: Rinne lives in /app/share/rinne, PySide6 comes from the PySide BaseApp.
export PYTHONPATH="/app/share/rinne${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m rinne "$@"
