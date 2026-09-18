# Kuechendisplay / Familienplaner

Raspberry-Pi-Kiosk-Display mit Familienplaner-Anzeige (Yuvomi), Fingerabdruck-Login (GROW R503), physischen Tastern, MQTT-Steuerung und Home-Automation-Integration.

## Ordnerstruktur

- `supervisor/` - aktiver Python-Supervisor (v2), orchestriert Chromium-Kiosk, Yuvomi-Login/-Logout, Zustandsmodell, Taster- und Fingerabdruck-Hardware, MQTT.
- `fingerprint-admin/` - eigenstaendiges Tkinter-GUI-Tool zur Verwaltung des Fingerabdrucksensors (Enrollment, Backup/Restore, Passwortverwaltung). Bewusst getrennt vom Supervisor, damit es auch fuer andere Projekte mit demselben Sensor wiederverwendbar bleibt.
- `archive/` - veraltete erste Testversionen (v1-Supervisor, CLI-Fingerabdruck-Tool), nur zur Historie, nicht mehr gepflegt.
- `docs/` - Hardware-Verkabelung, Kiosk/labwc-Konfiguration, Installation, Troubleshooting.

## Architekturueberblick

Der Supervisor laeuft als systemd-Dienst `kuechendisplay-supervisor.service` und steuert einen im Kiosk-Modus laufenden Chromium-Browser per Chrome DevTools Protocol. Er reagiert auf MQTT-Kommandos (Topic-Praefix `display/kueche/cmd/...`) und meldet seinen Zustand unter `display/kueche/status/...` zurueck. Zwei zusaetzliche, unabhaengige Prozesse ergaenzen ihn:

- `display_power_control.py` - physisches An-/Ausschalten des Displays per `wlopm` (braucht Zugriff auf die grafische Wayland-Sitzung, die der systemd-Dienst nicht hat)
- `notification_overlay.py` - eigenes Wayland-Layer-Shell-Fenster fuer kurze Benachrichtigungen

Beide werden ueber `~/.config/labwc/autostart` gestartet, nicht ueber systemd.

## Betriebssystem-Layout (empfohlen)

Das Repository ist so aufgebaut, dass es 1:1 als Checkout auf dem Raspberry Pi dienen kann:

```
~/kuechendisplay/          <- git clone dieses Repos
  supervisor/               <- systemd-Dienst startet hieraus
  fingerprint-admin/        <- GUI-Start hieraus
  docs/
~/.kuechendisplay/          <- NICHT im Repo: secrets.json, button_map.json
~/kuechendisplay-venv/      <- NICHT im Repo: Python-venv fuer Fingerabdruck-GUI
```

Updates auf dem Pi erfolgen direkt per `git pull` in `~/kuechendisplay/`.

## Weiterfuehrende Dokumentation

- [`docs/hardware.md`](docs/hardware.md) - GPIO-Pinbelegung, Sensor-Verkabelung
- [`docs/kiosk-labwc.md`](docs/kiosk-labwc.md) - labwc/rc.xml-Konfiguration, Autostart, Taskleiste
- [`docs/installation.md`](docs/installation.md) - Ersteinrichtung auf dem Raspberry Pi
- [`docs/troubleshooting.md`](docs/troubleshooting.md) - bekannte Stolperfallen
- [`fingerprint-admin/README.md`](fingerprint-admin/README.md) - Bedienung der Fingerabdruck-GUI

## Verwandtes, separates Projekt

Die Yuvomi-Google-Calendar-Integration (OAuth-Verifizierungsseiten fuer Google) lebt in einem eigenen, separaten Repository und ist bewusst nicht Teil dieses Projekts.

## Lizenz

MIT, siehe [`LICENSE`](LICENSE).
