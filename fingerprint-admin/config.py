"""config.py
Zentrale Konfiguration fuer die Fingerabdruck-Verwaltung.
Enthaelt Pfade, UART-Einstellungen und die Verwaltung des Sensor-Passworts
(wird NICHT im Code, sondern in einer separaten JSON-Datei gespeichert)."""

import json
import os
import importlib.util
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "sensor_config.json")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
LOG_FILE = os.path.join(BASE_DIR, "fingerprint_admin.log")

UART_PORT = "/dev/serial0"
UART_BAUDRATE = 57600

MIN_TEMPLATE_ID = 0
MAX_TEMPLATE_ID = 199

_DEFAULT_CONFIG = {"password": 0}

# Gemeinsam mit dem Supervisor genutzte Fingerprint-Zuordnung
FINGERPRINT_MAPPING_FILE = Path.home() / ".kuechendisplay" / "fingerprint_mapping.py"


def _load_config():
    if not os.path.exists(CONFIG_FILE):
        return dict(_DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if "password" not in data:
            data["password"] = 0
        return data
    except (json.JSONDecodeError, OSError):
        return dict(_DEFAULT_CONFIG)


def _save_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except OSError:
        pass


def get_sensor_password() -> int:
    return int(_load_config().get("password", 0))


def set_sensor_password(new_password: int) -> None:
    data = _load_config()
    data["password"] = int(new_password)
    _save_config(data)


def load_fingerprint_mapping():
    if not FINGERPRINT_MAPPING_FILE.exists():
        raise FileNotFoundError(
            f"{FINGERPRINT_MAPPING_FILE} fehlt - example-config/fingerprint_mapping.py.example "
            "nach ~/.kuechendisplay/fingerprint_mapping.py kopieren und Zuordnung eintragen"
        )
    spec = importlib.util.spec_from_file_location("fingerprint_mapping", FINGERPRINT_MAPPING_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


os.makedirs(BACKUP_DIR, exist_ok=True)

FINGERPRINT_MAPPING = load_fingerprint_mapping()
