"""Zugangsdaten aus der zentralen secrets.json des Projekts (nicht im Repo).

Standardpfad: /home/christoph/Dokumente/Github/.kuechendisplay/secrets.json
Abweichender Pfad: Umgebungsvariable YUVOMI_SECRETS_FILE oder Parameter/GUI-Feld.

Benoetigte Schluessel (zusaetzlich zu den bestehenden Eintraegen der Datei):
    "yuvomi_url":        "https://yuvomi.example.lan"
    "yuvomi_api_token":  "yuvomi_..."
    "yuvomi_verify_tls": true            (optional, Standard true)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SECRETS_FILE = Path("/home/christoph/Dokumente/Github/.kuechendisplay/secrets.json")


class SecretsError(RuntimeError):
    pass


@dataclass(frozen=True)
class YuvomiSecrets:
    url: str
    token: str
    verify_tls: bool = True
    warning: str | None = None

    def __repr__(self) -> str:  # Token nie in Logs/Tracebacks ausgeben
        return f"YuvomiSecrets(url={self.url!r}, token='***', verify_tls={self.verify_tls})"


def resolve_path(path: str | Path | None = None) -> Path:
    return Path(path or os.environ.get("YUVOMI_SECRETS_FILE") or DEFAULT_SECRETS_FILE).expanduser()


def load_yuvomi_secrets(path: str | Path | None = None) -> YuvomiSecrets:
    p = resolve_path(path)
    if not p.is_file():
        raise SecretsError(f"Secrets-Datei nicht gefunden: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SecretsError(f"Secrets-Datei nicht lesbar ({p}): {e.__class__.__name__}") from None
    url = str(data.get("yuvomi_url", "")).strip()
    token = str(data.get("yuvomi_api_token", "")).strip()
    missing = [k for k, v in (("yuvomi_url", url), ("yuvomi_api_token", token)) if not v]
    if missing:
        raise SecretsError(f"In {p} fehlen die Schluessel: {', '.join(missing)}")
    warning = None
    if os.name == "posix" and p.stat().st_mode & 0o077:
        warning = f"{p} ist fuer andere Benutzer lesbar - bitte 'chmod 600 {p}'"
    return YuvomiSecrets(url=url, token=token, verify_tls=bool(data.get("yuvomi_verify_tls", True)),
                         warning=warning)
