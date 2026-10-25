# kontakt_import

Überträgt jede Zeile einer Adress-Tabelle (`.xlsx`/`.csv`) 1:1 als Kontakt nach [yuvomi](https://github.com/ulsklyc/yuvomi)
(`POST /api/v1/contacts`). **Vorschau (Dry-Run) ist der Standard** – geschrieben wird nur beim bewussten Import.

## Einrichtung
```bash
cd kontakt_import
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
sudo apt install python3-tk        # nur für die GUI
```

### API-Token in der secrets.json
Der Token liegt – wie alle Zugangsdaten des Projekts – in `/home/christoph/Dokumente/Github/.kuechendisplay/secrets.json` (nicht im Repo; das ist der Standardpfad).
Diese drei Schlüssel zusätzlich zu den vorhandenen Einträgen ergänzen (Vorlage: `secrets.json.example`):
```json
"yuvomi_url": "https://yuvomi.example.lan",
"yuvomi_api_token": "yuvomi_...",
"yuvomi_verify_tls": true
```
```bash
chmod 600 /home/christoph/Dokumente/Github/.kuechendisplay/secrets.json
```
Token in yuvomi mit den Scopes `contacts:read` und `contacts:write` erzeugen. Ein anderer Pfad geht über das GUI-Feld,
`--secrets-file` oder die Umgebungsvariable `YUVOMI_SECRETS_FILE`. Der Token wird nie geloggt oder im Report gespeichert.

## GUI
```bash
./start_gui.sh            # oder: python -m yuvomi_import   (ohne Argumente)
```
Ablauf: Tabelle wählen → optional Blatt/Optionen → **„Vorschau (Dry-Run)“** → Ergebnistabelle prüfen →
**„Importieren“** (erst freigeschaltet, wenn die Vorschau mit denselben Einstellungen fehlerfrei lief; vorher Rückfrage).
Zusätzlich: „Verbindung testen“, „Kategorien anzeigen“ (Keys der vorhandenen yuvomi-Kategorien) und „Report-Ordner öffnen“.
Die Option „Vorhandene Kontakte (gleicher Name) überschreiben“ ist standardmäßig aktiviert.

## Kommandozeile
```bash
python -m yuvomi_import Adressen_Giese.xlsx --offline                # nur Tabelle prüfen
python -m yuvomi_import Adressen_Giese.xlsx                          # Dry-Run gegen yuvomi (liest Bestand)
python -m yuvomi_import Adressen_Giese.xlsx --apply --create-category
python -m yuvomi_import Adressen_Giese.xlsx --apply --no-update      # Bestand (gleicher Name) nur überspringen
```
Bestehende Kontakte werden standardmäßig per PUT aktualisiert; `--no-update` überspringt sie stattdessen.
Vor dem ersten Import: yuvomi-Backup/Datenbank sichern. Je Lauf entsteht ein Report `reports/*.csv`.

## Tabellenlayout
Mit Kopfzeile (Aliase: Nachname, Vorname, Geburtstag, Straße, PLZ, Ort, Telefon, E-Mail, Mobil, Notiz, **Kategorie**/Tag/Gruppe)
**oder** ohne Kopfzeile in dieser Spaltenreihenfolge:

| Spalte | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Feld | Nachname | Vorname | Geburtstag | Straße+Nr | PLZ | Ort | Festnetz | E-Mail | Mobil | (ignoriert) | Notiz | Kategorie (optional) |

## Kategorien
yuvomi kennt **eine** Kategorie je Kontakt (keine Mehrfach-Tags).
- Die Zelle darf den Kategorie-**Key** oder den **Namen** enthalten (Groß-/Kleinschreibung egal). Die mitgelieferten
  yuvomi-Kategorien haben übersetzte Standardnamen und werden daher über ihren Key angesprochen – siehe „Kategorien anzeigen“.
- Steht in der Zelle mehr als ein Eintrag (`Familie; Weihnachtskarte`), wird der erste die Kategorie, der Rest landet in den Notizen.
- „Standardkategorie“ gilt für Zeilen ohne eigene Kategorie, sonst nimmt yuvomi `misc`.
- Unbekannte Kategorien werden nur mit „Fehlende Kategorien anlegen“ (`--create-category`) und nur beim Import angelegt;
  in der Vorschau erscheint der Hinweis „würde angelegt“. Ohne diese Option fällt der Kontakt auf die Standardkategorie zurück.

## Regeln
- Leerer Nachname → Nachname der Zeile darüber im selben Block; eine Leerzeile beendet den Block (`--no-inherit-last-name` schaltet das ab).
- Zeile ohne Namen (z. B. gemeinsame Familien-E-Mail) wird an den vorherigen Kontakt angehängt.
- Leere Adresse bleibt leer (`--inherit-address` übernimmt die Blockadresse).
- PLZ: `47574.0` → `47574`; rein numerische PLZ < 5 Stellen werden mit führenden Nullen aufgefüllt.
- Geburtstag ohne Jahr (`08.11.`) wird als Geburtstag ohne Jahr an yuvomi übergeben.
- E-Mail-Zusatztext (z. B. `(gemeinsam)`) landet in den Notizen, ebenso die Notiz-Spalte.
- Abgleich mit dem Bestand über die Namensbestandteile; Titel wie Oma, Opa, Mama oder Papa werden ignoriert, Zusätze wie `(Susi)` stören nicht.
- Es wird nichts gelöscht.
- Grenzen der yuvomi-API: ≤ 20 Einträge je Liste, Label ≤ 50, Telefon ≤ 100 Zeichen.

## Tests
```bash
python -m pytest -q
```
