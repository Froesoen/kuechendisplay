#!/usr/bin/env bash
# Startet die Kontakt-Import-GUI (benoetigt python3-tk).
cd "$(dirname "$0")" || exit 1
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=python3; fi
exec "$PY" -m yuvomi_import
