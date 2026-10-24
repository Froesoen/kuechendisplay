"""Abgleich Tabelle <-> yuvomi: Kategorien aufloesen, anlegen, optional aktualisieren, nie loeschen."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .client import YuvomiClient, YuvomiError
from .mapper import Mapped, name_key


@dataclass
class Result:
    line: int
    name: str
    action: str  # create | update | skip-exists | skip-invalid | duplicate-in-table | error
    contact_id: Any = ""
    detail: str = ""
    category: str = ""


def _existing_index(client: YuvomiClient | None) -> dict[frozenset[str], dict[str, Any]]:
    if client is None:
        return {}
    idx: dict[frozenset[str], dict[str, Any]] = {}
    for c in client.list_contacts():
        first, last = c.get("first_name") or "", c.get("last_name") or ""
        key = name_key(first, last) if (first or last) else name_key(c.get("name") or "", "")
        idx.setdefault(key, c)
    return idx


def resolve_categories(client: YuvomiClient, items: list[Mapped], *, create: bool, apply: bool,
                       log: Callable[[str], None] = print) -> None:
    """Ersetzt Kategorienamen im Payload durch yuvomi-Keys (Treffer ueber Key oder Name).

    Unbekannte Kategorie: mit create=True anlegen (nur bei apply), sonst Warnung und Standardkategorie.
    """
    lookup: dict[str, str] = {}
    for c in client.list_categories():
        lookup[str(c["key"]).casefold()] = c["key"]
        if c.get("name"):
            lookup[str(c["name"]).casefold()] = c["key"]

    for m in items:
        name = m.payload.get("category")
        if not name:
            continue
        k = name.casefold()
        if k not in lookup and create and apply:
            lookup[k] = client.create_category(name)["key"]
            log(f"Kategorie angelegt: {name} -> {lookup[k]}")
        if k in lookup:
            m.payload["category"] = lookup[k]
        elif create:
            m.warnings.append(f"Kategorie {name!r} wuerde angelegt")
        else:
            m.warnings.append(f"Kategorie {name!r} existiert nicht - Standardkategorie")
            del m.payload["category"]


def run_sync(items: list[Mapped], client: YuvomiClient | None, *, apply: bool,
             update: bool) -> list[Result]:
    existing = _existing_index(client)
    seen: set[frozenset[str]] = set()
    results: list[Result] = []

    for m in items:
        cat = str(m.payload.get("category", ""))
        warn = "; ".join(m.warnings)
        if not m.payload:
            results.append(Result(m.line, "", "skip-invalid", detail=warn))
            continue
        key = name_key(m.payload.get("firstName", ""), m.payload.get("lastName", ""))
        if key in seen:
            results.append(Result(m.line, m.display, "duplicate-in-table", detail=warn, category=cat))
            continue
        seen.add(key)

        found = existing.get(key)
        try:
            if found and not update:
                results.append(Result(m.line, m.display, "skip-exists", found["id"], warn, cat))
            elif found:
                if apply:
                    client.update_contact(found["id"], m.payload)
                results.append(Result(m.line, m.display, "update", found["id"], warn, cat))
            else:
                cid = ""
                if apply:
                    cid = client.create_contact(m.payload)["id"]
                results.append(Result(m.line, m.display, "create", cid, warn, cat))
        except YuvomiError as e:
            results.append(Result(m.line, m.display, "error", detail=f"{e} {warn}".strip(), category=cat))
    return results
