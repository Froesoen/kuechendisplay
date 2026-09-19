"""
config.py - Zentrale Konfiguration fuer den Kuechendisplay-Supervisor.

Buendelt Konstanten und das Laden der Zugangsdaten (~/.kuechendisplay/secrets.json).
"""

from __future__ import annotations

import json
import logging
import importlib.util
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
# Inaktivitaets-Timeout fuer individuelle Konten - zaehlt echte Browser-Nutzung
# (Klick/Touch/Tastatur/Scroll, siehe kiosk_controller Activity-Tracker) UND
# MQTT-/Taster-Aktivitaet. Bewusst kurz gehalten (3 Minuten), damit nach
# Nutzungsende zuegig auf Familie zurueckgefallen wird.
USER_INACTIVITY_TIMEOUT_SECONDS = 3 * 60

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

# --- Diashow (NAS-Fotos, siehe docs/diashow.md) ---
# Lokaler Webserver des slideshow-Moduls (slideshow/systemd/kuechendisplay-diashow-web.service).
# Wird von _set_display_mode("slideshow") angesteuert - ausgeloest durch Button 2
# (button_mapper: 2_short -> cmd/mode=slideshow), den Inaktivitaets-Watchdog nach
# SLIDESHOW_INACTIVITY_TIMEOUT_SECONDS oder ein manuelles MQTT-Kommando.
DIASHOW_URL = "http://127.0.0.1:8090/"

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
FINGERPRINT_MAPPING_FILE = Path.home() / ".kuechendisplay" / "fingerprint_mapping.py"


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

# Individuelle Konten fuer per Fingerabdruck ausgeloeste Logins. Wird
# vollstaendig aus secrets.json abgeleitet (Abschnitt "individual_accounts").
# Die Namen/Schluessel entscheidet ausschliesslich die lokale secrets.json -
# config.py enthaelt bewusst KEINE echten Namen, damit das oeffentliche
# Repository frei von personenbezogenen Daten bleibt. Die verwendeten
# Bezeichner muessen mit den Schluesseln in fingerprint_mapping.py
# uebereinstimmen (siehe example-config/).
INDIVIDUAL_USER_CREDENTIALS = {
    name: (creds.get("username"), creds.get("password"))
    for name, creds in SECRETS.get("individual_accounts", {}).items()
}


# --- Fingerprint-Mapping (gemeinsam mit fingerprint-admin/config.py genutzt) ---

def load_fingerprint_mapping():
    if not FINGERPRINT_MAPPING_FILE.exists():
        log.error(
            "Fingerprint-Mapping-Datei %s fehlt - example-config/fingerprint_mapping.py.example "
            "nach ~/.kuechendisplay/fingerprint_mapping.py kopieren und Zuordnung eintragen",
            FINGERPRINT_MAPPING_FILE,
        )
        raise FileNotFoundError(FINGERPRINT_MAPPING_FILE)
    spec = importlib.util.spec_from_file_location("fingerprint_mapping", FINGERPRINT_MAPPING_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FINGERPRINT_MAPPING = load_fingerprint_mapping()
