# kontakt_import

Überträgt jede Zeile einer Adress-Tabelle (`.xlsx`/`.csv`) 1:1 als Kontakt nach [yuvomi](https://github.com/ulsklyc/yuvomi)
(`POST /api/v1/contacts`). **Standard ist ein Dry-Run** – geschrieben wird nur mit `--apply`.

## Einrichtung
```bash
cd kontakt_import
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # URL + API-Token eintragen
```
Token in yuvomi erzeugen (Scopes `contacts:read`, `contacts:write`).

## Benutzung
```bash
python -m yuvomi_import Adressen_Giese.xlsx --offline           # nur Mapping prüfen
python -m yuvomi_import Adressen_Giese.xlsx                     # Dry-Run gegen yuvomi (liest Bestand)
python -m yuvomi_import Adressen_Giese.xlsx --apply --category Familie --create-category
python -m yuvomi_import Adressen_Giese.xlsx --apply --update    # Bestand (gleicher Name) per PUT überschreiben
```
Vor dem ersten `--apply`: yuvomi-Backup/Datenbank sichern. Report je Lauf unter `reports/*.csv`.

## Tabellenlayout
Mit Kopfzeile (Aliase: Nachname, Vorname, Geburtstag, Straße, PLZ, Ort, Telefon, E-Mail, Mobil, Notiz) **oder**
ohne Kopfzeile im Layout der bisherigen Liste:

| Spalte | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Feld | Nachname | Vorname | Geburtstag | Straße+Nr | PLZ | Ort | Festnetz | E-Mail | Mobil | (ignoriert) | Notiz |

## Regeln
- Leerer Nachname → Nachname der Zeile darüber im selben Block; eine Leerzeile beendet den Block (`--no-inherit-last-name` schaltet das ab).
- Zeile ohne Namen (z. B. gemeinsame Familien-E-Mail) wird an den vorherigen Kontakt angehängt.
- Leere Adresse bleibt leer (`--inherit-address` übernimmt die Blockadresse).
- PLZ: `47574.0` → `47574`; rein numerische PLZ < 5 Stellen werden mit führenden Nullen aufgefüllt.
- E-Mail-Zusatztext (z. B. `(gemeinsam)`) landet in den Notizen, ebenso die Notiz-Spalte.
- Idempotent: bestehende Kontakte (gleiche Namens-Token) werden übersprungen; nichts wird gelöscht.
- Grenzen der yuvomi-API: ≤ 20 Einträge je Liste, Label ≤ 50, Telefon ≤ 100 Zeichen.

## Tests
```bash
pytest -q
```
