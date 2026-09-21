# MQTT-Schnittstelle

Zentrale Referenz aller MQTT-Topics des Kuechendisplay-Projekts. Broker: `mqtt`
(lokales Netz, Port `1883`, **ohne Authentifizierung**) - siehe
`supervisor/config.py` (`MQTT_BROKER_HOST`, `MQTT_BROKER_PORT`).

Es gibt zwei unabhaengige Topic-Namensraeume:

- **Supervisor** (Anzeige-/App-/Nutzersteuerung): Praefix `display/kueche/`
- **Diashow-Modul** (Bildinhalt/Tempo der Slideshow): Praefix
  `display/kueche/diashow/` (Unter-Namensraum des Supervisor-Praefixes)

Alle Beispiele nutzen `mosquitto_pub`/`mosquitto_sub`:

```bash
mosquitto_pub -h mqtt -p 1883 -t '<topic>' -m '<payload>'
mosquitto_sub -h mqtt -p 1883 -t '<topic>' -C 1 -W 3 -v
```

## Supervisor: Befehle (Eingang, `cmd/...`)

Der Supervisor (`supervisor/kuechendisplay_supervisor.py`) abonniert beim
Verbindungsaufbau `display/kueche/cmd/#`.

| Topic | Payload | Wirkung |
|---|---|---|
| `display/kueche/cmd/mode` | `app` oder `slideshow` | Wechselt den Anzeigemodus. Bei `slideshow` wird der Kiosk-Tab zu `DIASHOW_URL` (`http://127.0.0.1:8090/`) navigiert; bei `app` wird die aktuell aktive App erneut aktiviert. |
| `display/kueche/cmd/app` | `yuvomi`, `nodered` oder `custom:<url>` | Setzt die aktive App und `display_mode=app`. Bei `yuvomi` wird zusaetzlich der Familien-Login sichergestellt. `custom:` erlaubt eine beliebige URL, z. B. `custom:http://example.local/`. |
| `display/kueche/cmd/display/power` | `on`, `off` oder `toggle` | Schaltet die Monitor-Stromversorgung direkt per GPIO17 (GERUI-MOSFET-Modul) - kein `wlopm` und kein separater Prozess mehr noetig, da die Stromtrennung selbst ein HDMI-Hotplug-Ereignis ausloest, auf das der Wayland-Compositor automatisch reagiert. |
| `display/kueche/cmd/wallmode` | `on` (alles andere = aus) | Aktiviert/deaktiviert den Wall Mode (setzt/loescht `localStorage`-Key `yuvomi-wall-mode` im Kiosk-Browser und laedt neu). |
| `display/kueche/cmd/kindersicherung` | `on` (alles andere = aus) | Aktiviert/deaktiviert die Kindersicherung: Taster loesen nur noch die Notify-Meldung "Kindersicherung" aus, der Fingerabdrucksensor bleibt bei Beruehrung stromlos, und ein transparentes Overlay im Kiosk-Browser blockiert alle Touch-/Klick-Eingaben (der Bildschirm zeigt weiterhin normal an, was gerade aufgerufen ist). `cmd/button/map` bleibt auch bei aktiver Kindersicherung nutzbar. Startet nach jedem Neustart des Supervisors immer im Zustand `off` (keine Persistenz). Das Ein-/Ausschalten selbst wird per `cmd/notify` quittiert. |
| `display/kueche/cmd/notify` | beliebiger Text | Zeigt den Text im Notification-Overlay an (eigener Prozess `notification_overlay.py`, abonniert denselben Topic direkt; der Supervisor selbst loggt die Nachricht nur). |
| `display/kueche/cmd/notify/clear` | beliebig (z. B. leer) | Blendet das Notification-Overlay sofort aus. |
| `display/kueche/cmd/button/map` | JSON, z. B. `{"key":"2_long","topic":"cmd/mode","payload":"slideshow"}` | Belegt einen Taster (`key` = `1`-`4` + `_short`/`_long`) neu: Taste loest kuenftig eine Publish-Nachricht auf `topic` (relativ zu `display/kueche/`) mit `payload` aus. Persistiert unter `~/.kuechendisplay/button_map.json` und wird sofort per `status/button/map` erneut veroeffentlicht. Funktioniert unabhaengig vom Zustand der Kindersicherung. |
| `display/kueche/cmd/user` | `username:password` | Manueller Test-Login: meldet den angegebenen Yuvomi-Nutzer an (ohne Doppelpunkt wird die Nachricht ignoriert und eine Warnung geloggt). |

### Beispiele

```bash
# Zur Diashow wechseln
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/mode' -m slideshow

# Zurueck zur App-Ansicht
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/mode' -m app

# Node-RED-Dashboard aktivieren
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/app' -m nodered

# Beliebige eigene URL anzeigen
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/app' -m 'custom:http://example.local/'

# Display aus- bzw. umschalten (schaltet jetzt die echte Stromversorgung)
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/display/power' -m off
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/display/power' -m toggle

# Wall Mode aktivieren
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/wallmode' -m on

# Kindersicherung ein- bzw. ausschalten
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/kindersicherung' -m on
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/kindersicherung' -m off

# Benachrichtigung anzeigen und wieder ausblenden
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/notify' -m 'Muell rausbringen!'
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/notify/clear' -m ''

# Taster 2 (langer Druck) neu auf Wallmode-Ein belegen
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/button/map' \
  -m '{"key":"2_long","topic":"cmd/wallmode","payload":"on"}'

# Testweise als individueller Nutzer anmelden
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/user' -m 'kind1:geheimespasswort'
```

## Supervisor: Status (Ausgang, retained)

| Topic | Payload | Zweck |
|---|---|---|
| `display/kueche/status/health` (retain, LWT) | JSON `{"online": true/false, "ts"/"reason": ...}` | Heartbeat alle `HEARTBEAT_INTERVAL_SECONDS` (30s) sowie Last-Will bei Verbindungsverlust bzw. sauberem Shutdown. |
| `display/kueche/status/state` (retain) | JSON `{"display_power":"on/off", "display_mode":"app/slideshow", "active_app":"...", "active_user":"...", "wall_mode": true/false, "child_lock": true/false}` | Gesamtzustand des Displays, aktualisiert bei jeder relevanten Aenderung. |
| `display/kueche/status/kindersicherung` (retain) | `on` / `off` | Aktueller Zustand der Kindersicherung; wird bei jedem Start des Supervisors explizit auf `off` gesetzt, unabhaengig von einem evtl. stehen gebliebenen retained Wert. |
| `display/kueche/status/button/map` (retain) | JSON aller vier Tastenbelegungen | Aktuelle Button-Map, wird bei Verbindungsaufbau und nach jeder Aenderung per `cmd/button/map` neu veroeffentlicht. |

### Beispiele zum Lesen

```bash
mosquitto_sub -h mqtt -p 1883 -t 'display/kueche/status/state' -C 1 -W 3 -v
mosquitto_sub -h mqtt -p 1883 -t 'display/kueche/status/health' -C 1 -W 3 -v
mosquitto_sub -h mqtt -p 1883 -t 'display/kueche/status/kindersicherung' -C 1 -W 3 -v
mosquitto_sub -h mqtt -p 1883 -t 'display/kueche/status/button/map' -C 1 -W 3 -v
```

## Standard-Tastenbelegung (Ausloeser fuer obige Publishes)

Physische Taster (`supervisor/button_mapper.py`, `DEFAULT_BUTTON_MAP`) senden
selbst keine MQTT-Nachrichten "roh", sondern loesen intern die folgenden
`cmd/...`-Publishes aus (relativ zu `display/kueche/`), die sich per
`cmd/button/map` umkonfigurieren lassen. Ist die Kindersicherung aktiv,
wird diese Belegung komplett uebersteuert: jeder Tastendruck loest dann
ausschliesslich `cmd/notify` = `Kindersicherung` aus.

| Taste | Standard-Aktion |
|---|---|
| 1 kurz | `cmd/app` = `yuvomi` |
| 1 lang | `cmd/display/power` = `toggle` |
| 2 kurz | `cmd/mode` = `slideshow` |
| 3 kurz | `cmd/app` = `nodered` |
| 4 kurz | `cmd/notify/clear` = `` |

## Diashow-Modul (`slideshow/slideshow_service.py`)

Eigener MQTT-Client mit Praefix `display/kueche/diashow` (siehe
`slideshow/config.json`, Schluessel `mqtt.topic_prefix`). Steuert
ausschliesslich Inhalt/Tempo der Diashow selbst - unabhaengig davon, ob sie
gerade sichtbar ist (Sichtbarkeit wird ueber `cmd/mode` des Supervisors
gesteuert, siehe oben).

| Topic | Richtung | Payload | Zweck |
|---|---|---|---|
| `display/kueche/diashow/set/intervall` | Eingang | Sekunden, z. B. `15` (min. 2s) | Anzeigedauer pro Bild aendern |
| `display/kueche/diashow/set/rescan` | Eingang | beliebig, z. B. `1` | Neu-Scan des NAS-Ordners ausloesen (wird beim naechsten Bildwechsel wirksam) |
| `display/kueche/diashow/set/aktiv` | Eingang | `ON` / `OFF` | Diashow pausieren/fortsetzen |
| `display/kueche/diashow/status` (retain) | Ausgang | JSON `{"intervall":..., "anzahl_bilder":..., "letzter_scan":..., "aktiv":...}` | Aktueller Zustand fuer Dashboards/Node-RED |

### Beispiele

```bash
# Manueller Rescan
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/diashow/set/rescan' -m 1

# Intervall auf 15s setzen
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/diashow/set/intervall' -m 15

# Diashow pausieren / fortsetzen
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/diashow/set/aktiv' -m OFF
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/diashow/set/aktiv' -m ON

# Status lesen
mosquitto_sub -h mqtt -p 1883 -t 'display/kueche/diashow/status' -C 1 -W 3 -v
```

## Kompletter Wechsel zur Diashow und zurueck

```bash
# Diashow anzeigen (navigiert den Kiosk-Tab zur Diashow-URL)
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/mode' -m slideshow

# Waehrenddessen z. B. Intervall anpassen
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/diashow/set/intervall' -m 20

# Zurueck zur App-Ansicht
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/mode' -m app
```

---

*Quelle: Code-Stand vom 21.09.2026 (`supervisor/kuechendisplay_supervisor.py`,
`config.py`, `state.py`, `button_mapper.py`, `hardware_buttons.py`,
`hardware_fingerprint.py`, `kiosk_controller.py`, `notification_overlay.py`,
`slideshow/slideshow_service.py`, `docs/diashow.md`, `docs/hardware.md`).
Display-Power und Kindersicherung laufen seit diesem Stand direkt im
Haupt-Supervisor, `display_power_control.py` wurde entfernt.*
