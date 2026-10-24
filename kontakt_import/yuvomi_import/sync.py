"""Abgleich Tabelle <-> yuvomi: anlegen, optional aktualisieren, nie loeschen."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .client import YuvomiClient, YuvomiError
from .mapper import Mapped, name_key


@dataclass
class Result:
    line: int
    name: str
    action: str  # create | update | skip-exists | skip-invalid | duplicate-in-table | error
    contact_id: Any = ""
    detail: str = ""


def _existing_index(client: YuvomiClient | None) -> dict[frozenset[str], dict[str, Any]]:
    if client is None:
        return {}
    idx: dict[frozenset[str], dict[str, Any]] = {}
    for c in client.list_contacts():
        first, last = c.get("first_name") or "", c.get("last_name") or ""
        key = name_key(first, last) if (first or last) else name_key(c.get("name") or "", "")
        idx.setdefault(key, c)
    return idx


def ensure_category(client: YuvomiClient, name: str, create: bool) -> str:
    """Gibt den Kategorie-Key zurueck (Key oder Anzeigename akzeptiert)."""
    for c in client.list_categories():
        if name.casefold() in {str(c["key"]).casefold(), str(c.get("name") or "").casefold()}:
            return c["key"]
    if not create:
        keys = ", ".join(c["key"] for c in client.list_categories())
        raise SystemExit(f"Kategorie {name!r} existiert nicht (vorhanden: {keys}). "
                         "Mit --create-category anlegen lassen.")
    return client.create_category(name)["key"]


def run_sync(items: list[Mapped], client: YuvomiClient | None, *, apply: bool,
             update: bool) -> list[Result]:
    existing = _existing_index(client)
    seen: set[frozenset[str]] = set()
    results: list[Result] = []

    for m in items:
        if not m.payload:
            results.append(Result(m.line, "", "skip-invalid", detail="; ".join(m.warnings)))
            continue
        key = name_key(m.payload.get("firstName", ""), m.payload.get("lastName", ""))
        warn = "; ".join(m.warnings)
        if key in seen:
            results.append(Result(m.line, m.display, "duplicate-in-table", detail=warn))
            continue
        seen.add(key)

        found = existing.get(key)
        try:
            if found and not update:
                results.append(Result(m.line, m.display, "skip-exists", found["id"], warn))
            elif found:
                if apply:
                    client.update_contact(found["id"], m.payload)
                results.append(Result(m.line, m.display, "update", found["id"], warn))
            else:
                cid = ""
                if apply:
                    cid = client.create_contact(m.payload)["id"]
                results.append(Result(m.line, m.display, "create", cid, warn))
        except YuvomiError as e:
            results.append(Result(m.line, m.display, "error", detail=f"{e} {warn}".strip()))
    return results
