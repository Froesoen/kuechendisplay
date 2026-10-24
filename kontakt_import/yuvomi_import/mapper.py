"""Tabellenzeile -> yuvomi-Kontakt-Payload (POST/PUT /api/v1/contacts).

Felder laut server/routes/contacts.js: firstName, lastName, category, birthday (YYYY-MM-DD),
birthday_year_unknown, notes, phones[], emails[], addresses[] (jeweils mit Pflichtfeld label; isPrimary optional).
Grenzen: max. 20 Eintraege je Liste, Label <= 50, Telefon <= 100, E-Mail <= 255 Zeichen.
yuvomi kennt genau EINE Kategorie je Kontakt; weitere Eintraege einer Zelle ("A; B") landen in den Notizen.
Geburtstag ohne Jahr ("08.11." oder "8.11"): birthday_year_unknown=true, yuvomi ersetzt das Jahr durch einen Platzhalter.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

EMAIL_RE = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")
DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%d.%m.%y")
CATEGORY_SPLIT_RE = re.compile(r"[;,|]")
PARTIAL_DATE_RE = re.compile(r"^\s*(\d{1,2})\.\s*(\d{1,2})\.?\s*$")
PLACEHOLDER_YEAR = 2000  # Schaltjahr, damit 29.02. gueltig bleibt


@dataclass
class Options:
    category: str | None = None  # Standardkategorie fuer Zeilen ohne eigene Kategorie
    inherit_last_name: bool = True
    inherit_address: bool = False


@dataclass
class Mapped:
    line: int
    payload: dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    @property
    def display(self) -> str:
        return f"{self.payload.get('firstName', '')} {self.payload.get('lastName', '')}".strip()


def parse_date(v: Any) -> tuple[str | None, str | None]:
    if v in ("", None):
        return None, None
    if isinstance(v, (date, datetime)):
        d = v.date() if isinstance(v, datetime) else v
        return d.isoformat(), None
    s = str(v).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat(), None
        except ValueError:
            pass
    return None, f"Geburtstag nicht lesbar: {s!r}"


def parse_partial_date(v: Any) -> str | None:
    """'08.11.' -> '2000-11-08' (Jahr = Platzhalter); None, wenn kein Tag.Monat-Format."""
    m = PARTIAL_DATE_RE.match(v) if isinstance(v, str) else None
    if not m:
        return None
    try:
        return date(PLACEHOLDER_YEAR, int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        return None


def clean_postal(v: Any) -> str:
    s = str(v or "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s.zfill(5) if s.isdigit() and len(s) < 5 else s


def split_emails(raw: str) -> tuple[list[str], str]:
    """Adressen herausloesen; uebrig bleibender Text (z. B. '(gemeinsam)') wird Hinweis."""
    found = EMAIL_RE.findall(raw)
    rest = EMAIL_RE.sub(" ", raw)
    rest = re.sub(r"[;,()\s]+", " ", rest).strip()
    return found, rest


def split_categories(raw: Any) -> list[str]:
    return [c.strip() for c in CATEGORY_SPLIT_RE.split(str(raw or "")) if c.strip()]


def _row_empty(row: dict[str, Any]) -> bool:
    return not any(str(row.get(k, "")).strip() for k in row if not k.startswith("_"))


def map_rows(rows: list[dict[str, Any]], opts: Options | None = None) -> list[Mapped]:
    opts = opts or Options()
    result: list[Mapped] = []
    block_last = ""
    block_addr: dict[str, str] | None = None

    for row in rows:
        if _row_empty(row):
            block_last, block_addr = "", None
            continue

        warnings: list[str] = []
        first = str(row["first_name"]).strip()
        last = str(row["last_name"]).strip()
        if last:
            block_last = last
        elif opts.inherit_last_name and block_last:
            last = block_last
        own_last = str(row["last_name"]).strip()
        if not first and not own_last and result and result[-1].payload and block_last:
            _merge_into_previous(result[-1], row, warnings)
            continue
        if not first and not last:
            result.append(Mapped(row["_line"], {}, ["Zeile ohne Namen uebersprungen"]))
            continue

        notes: list[str] = []
        note = str(row["note"]).strip()
        if note:
            notes.append(note)

        payload: dict[str, Any] = {}
        if first:
            payload["firstName"] = first
        if last:
            payload["lastName"] = last

        cats = split_categories(row.get("category", ""))
        if cats:
            payload["category"] = cats[0]
        elif opts.category:
            payload["category"] = opts.category
        if len(cats) > 1:
            notes.append("Weitere Kategorien: " + ", ".join(cats[1:]))
            warnings.append("yuvomi kennt nur eine Kategorie je Kontakt - Rest in Notizen")

        partial = parse_partial_date(row["birthday"])
        if partial:
            payload["birthday"] = partial
            payload["birthday_year_unknown"] = True
        else:
            bday, werr = parse_date(row["birthday"])
            if bday:
                payload["birthday"] = bday
            if werr:
                warnings.append(werr)

        phones = []
        for key, label in (("phone_home", "Festnetz"), ("phone_mobile", "Mobil")):
            val = str(row[key]).strip()
            if val:
                phones.append({"label": label, "value": val[:100], "isPrimary": not phones})
                if len(val) > 100:
                    warnings.append(f"{label}-Nummer auf 100 Zeichen gekuerzt")
        if phones:
            payload["phones"] = phones

        emails = []
        addrs, rest = split_emails(str(row["email"]))
        for a in addrs:
            emails.append({"label": "Privat", "value": a, "isPrimary": not emails})
        if rest:
            notes.append(f"E-Mail-Hinweis: {rest}")
        if str(row["email"]).strip() and not addrs:
            warnings.append(f"Keine gueltige E-Mail: {row['email']!r}")
            notes.append(f"E-Mail (roh): {row['email']}")
        if emails:
            payload["emails"] = emails

        addr = {
            "street": str(row["street"]).strip(),
            "postalCode": clean_postal(row["postal_code"]),
            "city": str(row["city"]).strip(),
        }
        if any(addr.values()):
            block_addr = addr
        elif opts.inherit_address and block_addr:
            addr = block_addr
        if any(addr.values()):
            payload["addresses"] = [
                {"label": "Zuhause", "isPrimary": True, **{k: v for k, v in addr.items() if v}}
            ]

        if notes:
            payload["notes"] = "\n".join(notes)

        result.append(Mapped(row["_line"], payload, warnings))

    if rows and rows[0].get("_unmapped") and result:
        result[0].warnings.append("Spalten nicht zugeordnet (werden ignoriert): " + str(rows[0]["_unmapped"]))
    return result


def name_key(first: str, last: str) -> frozenset[str]:
    """Reihenfolge-unabhaengiger Namensschluessel fuer den Abgleich mit Bestandskontakten."""
    tokens = re.findall(r"\w+", f"{first} {last}".casefold())
    return frozenset(tokens)


def _merge_into_previous(prev: Mapped, row: dict[str, Any], warnings: list[str]) -> None:
    """Zeile ohne Vor-/Nachnamen (z. B. gemeinsame Familien-E-Mail) -> an vorherigen Kontakt haengen."""
    addrs, rest = split_emails(str(row["email"]))
    p = prev.payload
    for a in addrs:
        p.setdefault("emails", []).append({"label": "Gemeinsam", "value": a, "isPrimary": not p.get("emails")})
    extra = [t for t in (str(row["note"]).strip(), f"E-Mail-Hinweis: {rest}" if rest else "") if t]
    for key, label in (("phone_home", "Festnetz"), ("phone_mobile", "Mobil")):
        val = str(row[key]).strip()
        if val:
            p.setdefault("phones", []).append({"label": label, "value": val[:100], "isPrimary": not p.get("phones")})
    if extra:
        p["notes"] = "\n".join(filter(None, [p.get("notes", ""), *extra]))
    prev.warnings.append(f"Zeile {row['_line']} an diesen Kontakt angehaengt")
