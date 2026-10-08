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
# Sensor-Versorgung (Kuechendisplay): Die Haupt-VCC des R503 wird ueber einen
# BC327-Transistor geschaltet (GPIO27, aktiv LOW) und vom Supervisor nur bei
# Beruehrung eingeschaltet. Da der Supervisor hier gestoppt ist, schaltet
# dieses Skript die Versorgung waehrend der gesamten GUI-Nutzung dauerhaft ein
# (per 'pinctrl') und danach wieder aus. Die Python-GUI selbst bleibt davon
# unberuehrt und kann auch mit anderen R503-Aufbauten genutzt werden.
#
# Aufruf:
#   bash start_fingerprint_gui.sh
#   SENSOR_POWER_GPIO=none bash start_fingerprint_gui.sh   # Sensor dauerhaft versorgt

set -uo pipefail

VENV_DIR="$HOME/kuechendisplay-venv"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
SERVICE_NAME="kuechendisplay-supervisor.service"

# GPIO-Nummer (BCM) des BC327-Schalters; "none" = Versorgung nicht schalten.
SENSOR_POWER_GPIO="${SENSOR_POWER_GPIO:-27}"
# R503-Datenblatt: ca. 50 ms bis zur Kommandobereitschaft, 0,5 s als Marge.
SENSOR_POWER_ON_DELAY_SECONDS="${SENSOR_POWER_ON_DELAY_SECONDS:-0.5}"
# R503-Datenblatt: nach dem Abschalten mind. 2 s aus, 2,5 s als Marge.
SENSOR_POWER_MIN_OFF_SECONDS="${SENSOR_POWER_MIN_OFF_SECONDS:-2.5}"
SENSOR_POWER_IS_ON=0

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

sensor_power_on() {
    [ "$SENSOR_POWER_GPIO" = "none" ] && return 0
    if ! command -v pinctrl >/dev/null 2>&1; then
        echo "WARNUNG: 'pinctrl' nicht gefunden - Sensor-Versorgung (GPIO$SENSOR_POWER_GPIO) wird nicht geschaltet." >&2
        return 0
    fi
    echo "Schalte Sensor-Versorgung ein (GPIO$SENSOR_POWER_GPIO = LOW)..."
    if pinctrl set "$SENSOR_POWER_GPIO" op dl; then
        SENSOR_POWER_IS_ON=1
        sleep "$SENSOR_POWER_ON_DELAY_SECONDS"
    else
        echo "WARNUNG: GPIO$SENSOR_POWER_GPIO konnte nicht gesetzt werden - Sensor evtl. stromlos." >&2
    fi
}

sensor_power_off() {
    [ "$SENSOR_POWER_IS_ON" = "1" ] || return 0
    echo "Schalte Sensor-Versorgung aus (GPIO$SENSOR_POWER_GPIO = HIGH)..."
    pinctrl set "$SENSOR_POWER_GPIO" op dh
    SENSOR_POWER_IS_ON=0
    # Mindestpause, bevor der Supervisor den Sensor ggf. wieder einschaltet.
    sleep "$SENSOR_POWER_MIN_OFF_SECONDS"
}

cleanup() {
    sensor_power_off
    restart_supervisor
}

echo "Stoppe $SERVICE_NAME vor Sensorzugriff..."
if ! sudo -n systemctl stop "$SERVICE_NAME"; then
    echo "FEHLER: $SERVICE_NAME konnte nicht gestoppt werden (sudoers-Freigabe fehlt?)." >&2
    echo "Siehe sudoers_kuechendisplay_fingerprint.txt.example." >&2
    exit 1
fi

trap cleanup EXIT

sensor_power_on

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

export DISPLAY="${DISPLAY:-:0}"

cd "$SCRIPT_DIR"

echo "Starte Fingerabdruck-Verwaltung (venv: $VENV_DIR)..."
python3 main.py
EXIT_CODE=$?

deactivate

exit "$EXIT_CODE"
