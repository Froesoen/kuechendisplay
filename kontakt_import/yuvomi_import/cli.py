"""Kommandozeile: python -m yuvomi_import tabelle.xlsx [--apply]   (ohne Argumente: GUI)"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

from .client import YuvomiError
from .credentials import SecretsError
from .service import ImportConfig, run_import


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="yuvomi_import", description="Tabelle 1:1 nach yuvomi-Kontakten uebertragen.")
    p.add_argument("table", type=Path, help=".xlsx oder .csv")
    p.add_argument("--sheet", help="Tabellenblatt (Standard: erstes)")
    p.add_argument("--apply", action="store_true", help="Wirklich schreiben (Standard: Dry-Run)")
    p.add_argument("--update", action="store_true", help="Bestehende Kontakte (gleicher Name) per PUT ueberschreiben")
    p.add_argument("--category", help="Standardkategorie fuer Zeilen ohne Kategorie (Key oder Name)")
    p.add_argument("--create-category", action="store_true", help="Fehlende Kategorien in yuvomi anlegen")
    p.add_argument("--no-inherit-last-name", action="store_true", help="Leeren Nachnamen NICHT aus dem Haushaltsblock uebernehmen")
    p.add_argument("--inherit-address", action="store_true", help="Leere Adresse aus dem Haushaltsblock uebernehmen")
    p.add_argument("--offline", action="store_true", help="Nur Mapping zeigen, keine Verbindung zu yuvomi")
    p.add_argument("--secrets-file", type=Path, help="Pfad zur secrets.json (Standard: ~/.kuechendisplay/secrets.json)")
    p.add_argument("--report-dir", type=Path, default=Path("reports"))
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = ImportConfig(
        table=args.table, sheet=args.sheet, apply=args.apply, update=args.update,
        default_category=args.category, create_categories=args.create_category,
        inherit_last_name=not args.no_inherit_last_name, inherit_address=args.inherit_address,
        offline=args.offline, secrets_file=args.secrets_file, report_dir=args.report_dir,
    )
    try:
        out = run_import(cfg)
    except (SecretsError, YuvomiError, httpx.HTTPError, OSError, ValueError) as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        return 2
    for r in out.results:
        if r.action in ("error", "skip-invalid") or r.detail:
            print(f"  Zeile {r.line} {r.name}: {r.action} {r.detail}")
    print("Report:", out.report)
    return 1 if out.counts.get("error") else 0
