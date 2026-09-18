"""
config.py - Zentrale Konfiguration fuer den Kuechendisplay-Supervisor.

Buendelt Konstanten und das Laden der Zugangsdaten (~/.kuechendisplay/secrets.json).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger("supervisor.config")

# --- MQTT ---
MQTT_BROKER_HOST = "mqtt"
MQTT_BROKER_PORT = 1883
MQTT_BASE_TOPIC = "display/kueche/"

# --- Kiosk / Chromium ---
CDP_URL = "http://127.0.0.1:9222"
CDP_WAIT_TIMEOUT_SECONDS = 60
CDP_WAIT_POLL_INTERVAL_SECONDS = 2

# --- Yuvomi ---
YUVOMI_BASE_URL = "http://planer:3000"
YUVOMI_REQUEST_TIMEOUT_SECONDS = 15
YUVOMI_RETRY_DELAY_SECONDS = 3
USER_INACTIVITY_TIMEOUT_SECONDS = 5 * 60

# --- Display / Zustand ---
HEARTBEAT_INTERVAL_SECONDS = 30
SLIDESHOW_INACTIVITY_TIMEOUT_SECONDS = 10 * 60

DEFAULT_APP_URLS = {
    "yuvomi": YUVOMI_BASE_URL,
    "nodered": "http://nodered:1880/dashboard/kuechendisplay",
}

DISPLAY_PREFERENCES = {
    "yuvomi-theme": "dark",
    "yuvomi-lang": "de",
}

# --- Display-Power (wlopm) ---
WLOPM_OUTPUT_NAME = "HDMI-A-1"  # ggf. mit 'wlopm' ohne Argumente pruefen/anpassen

# --- GPIO Pinbelegung (siehe docs/hardware.md) ---
BUTTON_GPIO_PINS = {1: 5, 2: 6, 3: 13, 4: 19}
BUTTON_PHYSICAL_PINS = {1: 29, 2: 31, 3: 33, 4: 35}
FINGERPRINT_WAKEUP_GPIO = 4
LONG_PRESS_THRESHOLD_SECONDS = 1.0

# --- Fingerabdrucksensor (GROW R503) ---
FINGERPRINT_UART_PORT = "/dev/serial0"
FINGERPRINT_UART_BAUDRATE = 57600

AUTOIDENTIFY_SECURITY_LEVEL = 3
AUTOIDENTIFY_START_POS = 0
AUTOIDENTIFY_END_POS = 200
AUTOIDENTIFY_RETURN_KEY_STEPS = 1
AUTOIDENTIFY_SEARCH_ERROR_RETRIES = 3

# --- Dateipfade ---
SECRETS_FILE = Path.home() / ".kuechendisplay" / "secrets.json"
BUTTON_MAP_CACHE_FILE = Path.home() / ".kuechendisplay" / "button_map.json"


def load_secrets() -> dict:
    if SECRETS_FILE.exists():
        try:
            data = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
            log.info("Zugangsdaten aus %s geladen", SECRETS_FILE)
            return data
        except Exception:
            log.exception("Secrets-Datei %s konnte nicht gelesen werden", SECRETS_FILE)
    else:
        log.warning(
            "Secrets-Datei %s fehlt - lege sie an (siehe secrets.json.example)",
            SECRETS_FILE,
        )
    return {}


SECRETS = load_secrets()

FAMILIE_USERNAME = SECRETS.get("familie_username", "familie")
FAMILIE_PASSWORD = SECRETS.get("familie_password", "PLATZHALTER_BITTE_SECRETS_JSON_ANLEGEN")

INDIVIDUAL_USER_CREDENTIALS = {
    "person_c": (SECRETS.get("person_c_username"), SECRETS.get("person_c_password")),
    "person_d": (SECRETS.get("person_d_username"), SECRETS.get("person_d_password")),
}
