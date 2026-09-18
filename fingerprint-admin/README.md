# Fingerabdruck-Verwaltung (Produktivversion) - Kuechendisplay Familienplaner

Eigenstaendiges Tkinter-GUI-Tool zur Verwaltung des GROW R503 Fingerabdrucksensors:
Enrollment, Loeschen, Identifikationstest, Backup/Restore und Passwortverwaltung.

Bewusst **eigenstaendig** gehalten (eigene Kopie von `fingerprint_mapping.py`),
damit dieses Tool auch fuer andere Projekte mit demselben Sensor wiederverwendet
werden kann, unabhaengig vom Kuechendisplay-Supervisor.

> **Status:** Aktiv im Einsatz, aber noch nicht im Detail vollstaendig getestet.
> Bitte zunaechst mit unkritischen Test-IDs (z. B. 199) pruefen, bevor produktive
> Zuordnungen (0-39) veraendert werden.

## Dateien

| Datei | Zweck |
|---|---|
| `config.py` | Pfade, UART-Einstellungen, Verwaltung des Sensor-Passworts (`sensor_config.json`) |
| `sensor_core.py` | Wrapper um `adafruit_fingerprint`: Verbindung, Enrollment (mit Bugfix), Loeschen, Identify, Template-Export/Import, Passwortaenderung |
| `backup_store.py` | Backup-Dateiformat (JSON, Base64 + SHA-256), Erstellen/Wiederherstellen |
| `logging_setup.py` | Rotierendes Audit-Log (`fingerprint_admin.log`) |
| `gui_app.py` | Tkinter-Oberflaeche, Hintergrundthreads fuer blockierende Sensor-Vorgaenge |
| `main.py` | Einstiegspunkt (`python3 main.py`) |
| `fingerprint_mapping.py` | Namenszuordnung (eigene Kopie, siehe Hinweis oben) |
| `supervisor_control.py` | Stoppt/startet `kuechendisplay-supervisor.service` waehrend Sensorzugriff |
| `start_fingerprint_gui.sh` | Start-Skript inkl. Supervisor-Stop/-Restart |

## Installation

```bash
python3 -m venv ~/kuechendisplay-venv
source ~/kuechendisplay-venv/bin/activate
pip install pyserial adafruit-circuitpython-fingerprint
sudo apt install python3-tk   # falls tkinter fehlt
```

Verkabelung siehe `../docs/hardware.md` (TXD->RXD Pin 10/GPIO15, RXD<-TXD Pin 8/GPIO14, VCC Pin 1, GND Pin 6).

## Ersteinrichtung

1. `sensor_config.json.example` nach `sensor_config.json` kopieren (Default-Passwort `0`).
2. `sudoers_kuechendisplay_fingerprint.txt.example` nach `sudoers_kuechendisplay_fingerprint.txt`
   kopieren, `<DEIN_BENUTZERNAME>` durch deinen echten Linux-Benutzernamen ersetzen,
   dann gemaess der Kommentare in der Datei installieren.

Beide `.example`-Dateien sowie `sensor_config.json`, `backups/` und `fingerprint_admin.log`
sind bewusst per `.gitignore` vom Repository ausgeschlossen.

## Start

```bash
bash start_fingerprint_gui.sh
```

Das Skript stoppt vor dem Sensorzugriff automatisch `kuechendisplay-supervisor.service`
(Konflikt um `/dev/serial0`) und startet ihn beim Beenden zuverlaessig wieder - auch bei
Absturz oder Strg+C.

## Bugfix: belegte ID beschreiben

Beim Enrollment prueft die GUI zuerst, ob die eingegebene ID bereits belegt ist. Ist das
der Fall, erscheint ein Bestaetigungsdialog; erst nach "Ja" wird das alte Template geloescht
und danach neu aufgenommen. Ohne Bestaetigung bricht der Vorgang sauber ab - kein Absturz mehr.

## Backup / Restore (Sensorwechsel)

- **Backup erstellen (alle):** liest jedes belegte Template ueber `load_model` + `get_fpdata`
  aus und speichert es als JSON-Datei mit SHA-256-Pruefsumme pro Eintrag.
- **Backup wiederherstellen:** liest die JSON-Datei, prueft die Pruefsummen und schreibt jedes
  Template per `send_fpdata` + `store_model` auf den aktuell verbundenen Sensor. Vor dem
  Ueberschreiben belegter IDs wird explizit gefragt.

Fuer einen Sensorwechsel: altes Modul anschliessen -> Backup erstellen -> neues Modul
anschliessen (Passwort in `sensor_config.json` ggf. anpassen) -> Backup wiederherstellen.

## Sensor-Passwort aendern

Ueber den Button "Sensor-Passwort aendern" wird der R503-Befehl `PS_SetPwd` (0x12) genutzt.
Da die verwendete Python-Bibliothek dafuer keine oeffentliche Methode bereitstellt, wird das
Rohkommando ueber die internen Hilfsmethoden der Bibliothek gesendet.

**Wichtig:** Ein verlorenes Passwort macht den Sensor ohne Werksreset/Hersteller-Tool
unbrauchbar. Die GUI verlangt deshalb doppelte Eingabe des neuen Passworts sowie eine
explizite Sicherheitsbestaetigung, bevor die Aenderung durchgefuehrt wird.

## Nicht enthaltene, aber vorbereitete Erweiterungsideen

- MQTT-Publish bei erkanntem Finger (Integration in bestehende Home-Automation-Flows)
- Batch-Import der Namenszuordnung aus CSV
- Duplikat-Check vor Enrollment (`finger_search()` vorab)
- Automatisches Mini-Backup einzelner IDs vor Loeschen/Ueberschreiben
- PIN-Schutz fuer die GUI selbst
