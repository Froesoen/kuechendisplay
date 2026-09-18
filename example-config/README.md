# example-config/

Diese Dateien sind Vorlagen fuer den geschuetzten Ordner `~/.kuechendisplay/`,
der bewusst NICHT im Git-Repository liegt (siehe `.gitignore`). Er wird von
beiden Modulen genutzt:

- `supervisor/` (Kuechendisplay-Supervisor)
- `fingerprint-admin/` (Fingerabdruck-Verwaltungs-GUI)

## Einrichtung

```bash
mkdir -p ~/.kuechendisplay
chmod 700 ~/.kuechendisplay
cp example-config/secrets.json.example ~/.kuechendisplay/secrets.json
cp example-config/fingerprint_mapping.py.example ~/.kuechendisplay/fingerprint_mapping.py
chmod 600 ~/.kuechendisplay/secrets.json ~/.kuechendisplay/fingerprint_mapping.py
```

Anschliessend beide Dateien mit echten Werten befuellen:

- `secrets.json`: echte Zugangsdaten fuer familie/benjamin/miriam eintragen.
- `fingerprint_mapping.py`: echte Namen und Template-ID-Bereiche eintragen.

`button_map.json` muss NICHT manuell angelegt werden - der Supervisor erzeugt
die Datei beim ersten Start automatisch mit `{}` als Inhalt.

Beide Module (`supervisor/config.py` und `fingerprint-admin/config.py`) laden
`fingerprint_mapping.py` zur Laufzeit direkt aus `~/.kuechendisplay/`, sodass
nur eine einzige gemeinsame Kopie gepflegt werden muss.
