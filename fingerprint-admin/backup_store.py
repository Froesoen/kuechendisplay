"""backup_store.py
Lesen/Schreiben von Backup-Dateien mit allen (oder ausgewaehlten)
Fingerprint-Templates eines Sensors.

Format: JSON mit Base64-kodierten Rohdaten pro Template-ID plus
SHA-256-Pruefsumme, damit ein beschaedigtes Backup beim Restore erkannt wird."""

import base64
import hashlib
import json
import time

from config import FINGERPRINT_MAPPING

BACKUP_FORMAT_VERSION = 1


def build_backup(sensor, ids: list = None) -> dict:
    if ids is None:
        ids = sensor.used_ids()

    status = sensor.status()
    entries = []
    for template_id in sorted(ids):
        raw = sensor.export_template(template_id)
        checksum = hashlib.sha256(raw).hexdigest()
        entries.append({
            "id": template_id,
            "name": FINGERPRINT_MAPPING.get_user_for_id(template_id),
            "data_b64": base64.b64encode(raw).decode("ascii"),
            "sha256": checksum,
        })

    return {
        "format_version": BACKUP_FORMAT_VERSION,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "library_size": status["library_size"],
        "template_count": status["template_count"],
        "entries": entries,
    }


def save_backup(path: str, backup_dict: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(backup_dict, fh, indent=2)


def load_backup(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("format_version") != BACKUP_FORMAT_VERSION:
        raise ValueError(f"Unbekanntes Backup-Format (Version {data.get('format_version')}).")
    return data


def _verify_entry(entry: dict) -> bytes:
    raw = base64.b64decode(entry["data_b64"])
    checksum = hashlib.sha256(raw).hexdigest()
    if checksum != entry.get("sha256"):
        raise ValueError(f"Pruefsummenfehler bei Template-ID {entry['id']} - Backup evtl. beschaedigt.")
    return raw


def restore_backup(sensor, backup_dict: dict, overwrite: bool = False, progress_cb=None) -> list:
    results = []
    for entry in backup_dict["entries"]:
        template_id = entry["id"]
        try:
            raw = _verify_entry(entry)
            sensor.import_template(template_id, raw, overwrite=overwrite)
            results.append((template_id, True, None))
            if progress_cb:
                progress_cb(f"ID {template_id} ({entry.get('name') or 'unbenannt'}) importiert.")
        except Exception as exc:  # pylint: disable=broad-except
            results.append((template_id, False, str(exc)))
            if progress_cb:
                progress_cb(f"ID {template_id}: Fehler - {exc}")
    return results
