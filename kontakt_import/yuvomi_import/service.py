"""Gemeinsame Ablaufsteuerung fuer CLI und GUI."""
from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .client import YuvomiClient
from .mapper import Options, map_rows
from .reader import read_table
from .credentials import load_yuvomi_secrets
from .sync import Result, resolve_categories, run_sync


@dataclass
class ImportConfig:
    table: Path
    sheet: str | None = None
    apply: bool = False
    update: bool = False
    default_category: str | None = None
    create_categories: bool = False
    inherit_last_name: bool = True
    inherit_address: bool = False
    offline: bool = False
    secrets_file: Path | None = None
    report_dir: Path = Path("reports")


@dataclass
class ImportOutcome:
    results: list[Result]
    report: Path
    counts: dict[str, int] = field(default_factory=dict)


def _client(secrets_file: Path | None, log: Callable[[str], None]) -> YuvomiClient:
    sec = load_yuvomi_secrets(secrets_file)
    if sec.warning:
        log("WARNUNG: " + sec.warning)
    return YuvomiClient(sec.url, sec.token, verify_tls=sec.verify_tls)


def test_connection(secrets_file: Path | None = None, log: Callable[[str], None] = print) -> str:
    client = _client(secrets_file, log)
    try:
        return f"Verbindung OK: {len(client.list_contacts())} Kontakte, {len(client.list_categories())} Kategorien"
    finally:
        client.close()


def list_categories(secrets_file: Path | None = None, log: Callable[[str], None] = print) -> list[dict]:
    client = _client(secrets_file, log)
    try:
        return client.list_categories()
    finally:
        client.close()


def write_report(results: list[Result], report_dir: Path, apply: bool) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = report_dir / f"import-{stamp}{'' if apply else '-dryrun'}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["zeile", "name", "kategorie", "aktion", "yuvomi_id", "hinweis"])
        for r in results:
            w.writerow([r.line, r.name, r.category, r.action, r.contact_id, r.detail])
    return path


def run_import(cfg: ImportConfig, log: Callable[[str], None] = print) -> ImportOutcome:
    if cfg.apply and cfg.offline:
        raise ValueError("--apply und --offline schliessen sich aus.")
    client = None if cfg.offline else _client(cfg.secrets_file, log)
    try:
        log(f"Lese {cfg.table} ...")
        rows = read_table(cfg.table, cfg.sheet)
        items = map_rows(rows, Options(category=cfg.default_category,
                                       inherit_last_name=cfg.inherit_last_name,
                                       inherit_address=cfg.inherit_address))
        log(f"{len(items)} Kontakte aus der Tabelle erkannt")
        if client:
            resolve_categories(client, items, create=cfg.create_categories, apply=cfg.apply, log=log)
        results = run_sync(items, client, apply=cfg.apply, update=cfg.update)
        report = write_report(results, cfg.report_dir, cfg.apply)
        counts = dict(Counter(r.action for r in results))
        log(("IMPORT" if cfg.apply else "DRY-RUN") + f" fertig: {counts}")
        return ImportOutcome(results, report, counts)
    finally:
        if client:
            client.close()
