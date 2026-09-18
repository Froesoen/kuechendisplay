#!/usr/bin/env bash
#
# start_fingerprint_gui.sh
# Aktiviert die vorhandene venv ~/kuechendisplay-venv und startet
# anschliessend die Fingerabdruck-GUI (main.py) aus diesem Verzeichnis.
#
# Vor dem Start wird kuechendisplay-supervisor.service gestoppt, damit
# kein Konflikt um /dev/serial0 entsteht. Nach Beendigung der GUI wird
# der Supervisor per 'trap ... EXIT' zuverlaessig wieder gestartet - auch
# wenn die GUI abstuerzt oder per Strg+C beendet wird.
#
# Benoetigt eine sudoers-Freigabe fuer passwortloses
# 'systemctl stop/start kuechendisplay-supervisor.service', siehe
# sudoers_kuechendisplay_fingerprint.txt.example.
#
# Aufruf:
#   bash start_fingerprint_gui.sh

set -uo pipefail

VENV_DIR="$HOME/kuechendisplay-venv"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
SERVICE_NAME="kuechendisplay-supervisor.service"

if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "FEHLER: venv nicht gefunden unter $VENV_DIR" >&2
    echo "Bitte zuerst anlegen, z.B.:" >&2
    echo "  python3 -m venv \"$VENV_DIR\"" >&2
    echo "  source \"$VENV_DIR/bin/activate\"" >&2
    echo "  pip install pyserial adafruit-circuitpython-fingerprint" >&2
    exit 1
fi

restart_supervisor() {
    echo "Starte $SERVICE_NAME wieder..."
    if sudo -n systemctl start "$SERVICE_NAME"; then
        echo "$SERVICE_NAME laeuft wieder."
    else
        echo "WARNUNG: $SERVICE_NAME konnte nicht automatisch neu gestartet werden." >&2
        echo "Bitte manuell pruefen: sudo systemctl status $SERVICE_NAME" >&2
    fi
}

echo "Stoppe $SERVICE_NAME vor Sensorzugriff..."
if ! sudo -n systemctl stop "$SERVICE_NAME"; then
    echo "FEHLER: $SERVICE_NAME konnte nicht gestoppt werden (sudoers-Freigabe fehlt?)." >&2
    echo "Siehe sudoers_kuechendisplay_fingerprint.txt.example." >&2
    exit 1
fi

trap restart_supervisor EXIT

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

export DISPLAY="${DISPLAY:-:0}"

cd "$SCRIPT_DIR"

echo "Starte Fingerabdruck-Verwaltung (venv: $VENV_DIR)..."
python3 main.py
EXIT_CODE=$?

deactivate

exit "$EXIT_CODE"
