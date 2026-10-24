"""Kommandozeile: python -m yuvomi_import tabelle.xlsx [--apply]"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from .client import YuvomiClient
from .mapper import Options, map_rows
from .reader import read_table
from .sync import ensure_category, run_sync


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="yuvomi_import", description="Tabelle 1:1 nach yuvomi-Kontakten uebertragen.")
    p.add_argument("table", type=Path, help=".xlsx oder .csv")
    p.add_argument("--sheet", help="Tabellenblatt (Standard: erstes)")
    p.add_argument("--apply", action="store_true", help="Wirklich schreiben (Standard: Dry-Run)")
    p.add_argument("--update", action="store_true", help="Bestehende Kontakte (gleicher Name) per PUT ueberschreiben")
    p.add_argument("--category", help="Kontakt-Kategorie (Key oder Name)")
    p.add_argument("--create-category", action="store_true", help="Kategorie anlegen, falls sie fehlt")
    p.add_argument("--no-inherit-last-name", action="store_true", help="Leeren Nachnamen NICHT aus dem Haushaltsblock uebernehmen")
    p.add_argument("--inherit-address", action="store_true", help="Leere Adresse aus dem Haushaltsblock uebernehmen")
    p.add_argument("--offline", action="store_true", help="Nur Mapping zeigen, keine Verbindung zu yuvomi")
    p.add_argument("--report-dir", type=Path, default=Path("reports"))
    return p


def _client_from_env() -> YuvomiClient:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    url, token = os.environ.get("YUVOMI_URL"), os.environ.get("YUVOMI_API_TOKEN")
    if not url or not token:
        sys.exit("YUVOMI_URL und YUVOMI_API_TOKEN muessen gesetzt sein (siehe .env.example).")
    verify = os.environ.get("YUVOMI_VERIFY_TLS", "true").lower() != "false"
    return YuvomiClient(url, token, verify_tls=verify)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.apply and args.offline:
        sys.exit("--apply und --offline schliessen sich aus.")

    client = None if args.offline else _client_from_env()
    category = None
    if args.category:
        if client is None:
            category = args.category
        else:
            category = ensure_category(client, args.category, args.create_category and args.apply)

    rows = read_table(args.table, args.sheet)
    items = map_rows(rows, Options(category=category,
                                   inherit_last_name=not args.no_inherit_last_name,
                                   inherit_address=args.inherit_address))
    results = run_sync(items, client, apply=args.apply, update=args.update)

    args.report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report = args.report_dir / f"import-{stamp}{'' if args.apply else '-dryrun'}.csv"
    with report.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["zeile", "name", "aktion", "yuvomi_id", "hinweis"])
        for r in results:
            w.writerow([r.line, r.name, r.action, r.contact_id, r.detail])

    counts = Counter(r.action for r in results)
    print(("APPLY" if args.apply else "DRY-RUN"), "-", dict(counts))
    for r in results:
        if r.action in ("error", "skip-invalid") or r.detail:
            print(f"  Zeile {r.line} {r.name}: {r.action} {r.detail}")
    print("Report:", report)
    if client:
        client.close()
    return 1 if counts.get("error") else 0
