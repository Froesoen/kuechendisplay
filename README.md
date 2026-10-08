# Kuechendisplay / Familienplaner

Raspberry-Pi-Kiosk-Display mit Familienplaner-Anzeige (Yuvomi), Fingerabdruck-Login (GROW R503), physischen Tastern, MQTT-Steuerung und Home-Automation-Integration.

## Ordnerstruktur

- `supervisor/` - aktiver Python-Supervisor (v2), orchestriert Chromium-Kiosk, Yuvomi-Login/-Logout, Zustandsmodell, Taster- und Fingerabdruck-Hardware, Display-Power (Relais), Kindersicherung, MQTT.
- `fingerprint-admin/` - eigenstaendiges Tkinter-GUI-Tool zur Verwaltung des Fingerabdrucksensors (Enrollment, Backup/Restore, Passwortverwaltung). Bewusst getrennt vom Supervisor, damit es auch fuer andere Projekte mit demselben Sensor wiederverwendbar bleibt.
- `archive/` - veraltete erste Testversionen (v1-Supervisor, CLI-Fingerabdruck-Tool), nur zur Historie, nicht mehr gepflegt.
- `docs/` - Hardware-Verkabelung, GPIO-Belegung, MQTT-Schnittstelle, Kiosk/labwc-Konfiguration, Diashow, Installation, Troubleshooting.

## Architekturueberblick

Der Supervisor laeuft als systemd-Dienst `kuechendisplay-supervisor.service` und steuert einen im Kiosk-Modus laufenden Chromium-Browser per Chrome DevTools Protocol. Er reagiert auf MQTT-Kommandos (Topic-Praefix `display/kueche/cmd/...`) und meldet seinen Zustand unter `display/kueche/status/...` zurueck. Die Display-Power-Steuerung (Monitor-Strom ueber ein Relais an GPIO17, Pin 11) und die Fingerprint-Versorgung (BC327 an GPIO27) laufen direkt im Supervisor; `wlopm` und ein separater Prozess sind dafuer nicht mehr noetig.

Ein zusaetzlicher, unabhaengiger Prozess ergaenzt ihn:

- `notification_overlay.py` - eigenes Wayland-Layer-Shell-Fenster fuer Benachrichtigungen (auch Fehlermeldungen des Fingerabdrucksensors, siehe [`docs/mqtt.md`](docs/mqtt.md)). Es wird ueber `~/.config/labwc/autostart` gestartet (nicht ueber systemd) und laeuft mit System-Python. Meldungen bleiben stehen, bis sie angetippt oder per `cmd/notify/clear` (Standard: Taster 4 kurz) ausgeblendet werden.

## Betriebssystem-Layout (empfohlen)

Das Repository ist so aufgebaut, dass es 1:1 als Checkout auf dem Raspberry Pi dienen kann:

```
~/kuechendisplay/          <- git clone dieses Repos
  supervisor/               <- systemd-Dienst startet hieraus
  fingerprint-admin/        <- GUI-Start hieraus
  docs/
~/.kuechendisplay/          <- NICHT im Repo: secrets.json, fingerprint_mapping.py, button_map.json
~/kuechendisplay-venv/      <- NICHT im Repo: Python-venv (Supervisor und Fingerabdruck-GUI)
```

Updates auf dem Pi erfolgen direkt per `git pull` in `~/kuechendisplay/`.

## Weiterfuehrende Dokumentation

- [`docs/hardware.md`](docs/hardware.md) - Stromversorgung, Relais, Sensor- und Monitorverkabelung
- [`docs/gpio-pinbelegung.md`](docs/gpio-pinbelegung.md) - komplette Belegung des 40-Pin-Headers
- [`docs/mqtt.md`](docs/mqtt.md) - MQTT-Topics und Meldungen
- [`docs/diashow.md`](docs/diashow.md) - Diashow-Modul
- [`docs/kiosk-labwc.md`](docs/kiosk-labwc.md) - labwc/rc.xml-Konfiguration, Autostart, Taskleiste
- [`docs/installation.md`](docs/installation.md) - Ersteinrichtung auf dem Raspberry Pi
- [`docs/troubleshooting.md`](docs/troubleshooting.md) - bekannte Stolperfallen
- [`fingerprint-admin/README.md`](fingerprint-admin/README.md) - Bedienung der Fingerabdruck-GUI

## Verwandtes, separates Projekt

Die Yuvomi-Google-Calendar-Integration (OAuth-Verifizierungsseiten fuer Google) lebt in einem eigenen, separaten Repository und ist bewusst nicht Teil dieses Projekts.

## Lizenz

MIT, siehe [`LICENSE`](LICENSE).
