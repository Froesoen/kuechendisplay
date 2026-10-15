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
| `display/kueche/cmd/mode` | `app` oder `slideshow` | Wechselt den Anzeigemodus. Bei `slideshow` wird ein angemeldeter individueller Yuvomi-Nutzer zuerst sofort abgemeldet (Rueckfall auf Familie), danach der Kiosk-Tab zu `DIASHOW_URL` (`http://127.0.0.1:8090/`) navigiert; bei `app` wird die aktuell aktive App erneut aktiviert. |
| `display/kueche/cmd/app` | `yuvomi`, `nodered` oder `custom:<url>` | Setzt die aktive App und `display_mode=app`. Bei `yuvomi` wird zusaetzlich ein frisches Familien-Login ausgefuehrt. Bei `nodered` und `custom:` wird ein angemeldeter individueller Nutzer zuerst sofort abgemeldet. `custom:` erlaubt eine beliebige URL, z. B. `custom:http://example.local/`. |
| `display/kueche/cmd/slideshow/timeout` | Ganzzahl Sekunden (`0` oder mindestens `30`) | Stellt die Inaktivitaetszeit bis zum automatischen Wechsel zur Diashow ein. `0` schaltet den automatischen Wechsel aus. Wird in `~/.kuechendisplay/slideshow_timeout.json` gespeichert und per `status/slideshow/timeout` bestaetigt. Ungueltige Werte werden ignoriert und als Warnung geloggt. Siehe [`automatik.md`](automatik.md). |
| `display/kueche/cmd/display/power` | `true`, `false` oder `toggle` | Schaltet die Monitor-Stromversorgung ueber das Relais-Modul an GPIO17 (Pin 11). `false` = Relais zieht an, Monitor stromlos; `true` = Relais faellt ab, Monitor hat Strom. Kein `wlopm` und kein separater Prozess noetig; die Stromtrennung loest selbst ein HDMI-Hotplug-Ereignis aus. |
| `display/kueche/cmd/wallmode` | `true` oder `false` | Aktiviert/deaktiviert den Wall Mode (setzt/loescht `localStorage`-Key `yuvomi-wall-mode` im Kiosk-Browser und laedt neu). |
| `display/kueche/cmd/kindersicherung` | `true` oder `false` | Aktiviert/deaktiviert die Kindersicherung: Taster loesen nur noch die Notify-Meldung "Kindersicherung" aus, der Fingerabdrucksensor bleibt bei Beruehrung stromlos, und ein transparentes Overlay im Kiosk-Browser blockiert alle Touch-/Klick-Eingaben (der Bildschirm zeigt weiterhin normal an, was gerade aufgerufen ist). `cmd/button/map` und `cmd/user` bleiben auch bei aktiver Kindersicherung nutzbar. Startet nach jedem Neustart des Supervisors immer im Zustand `false` (keine Persistenz); ein MQTT-Reconnect (z. B. Broker-Neustart) aendert den Zustand nicht. Das Ein-/Ausschalten selbst wird per `cmd/notify` quittiert. |
| `display/kueche/cmd/notify` | Text, optional als Markdown (Teilmenge, siehe unten) | Zeigt den Text im Notification-Overlay an (eigener Prozess `notification_overlay.py`, abonniert denselben Topic direkt; der Supervisor selbst loggt die Nachricht nur, und zwar unveraendert). Das Overlay interpretiert den Payload als Markdown und stellt ihn formatiert dar; reiner Text ohne Sonderzeichen erscheint unveraendert. |
| `display/kueche/cmd/notify/clear` | beliebig (z. B. leer) | Blendet das Notification-Overlay sofort aus. |
| `display/kueche/cmd/button/map` | JSON, z. B. `{"key":"2_long","topic":"cmd/mode","payload":"slideshow"}` | Belegt einen Taster (`key` = `1`-`4` + `_short`/`_long`) neu: Taste loest kuenftig eine Publish-Nachricht auf `topic` (relativ zu `display/kueche/`) mit `payload` aus. Persistiert unter `~/.kuechendisplay/button_map.json` und wird sofort per `status/button/map` erneut veroeffentlicht. Funktioniert unabhaengig vom Zustand der Kindersicherung. |
| `display/kueche/cmd/user` | Kennung eines individuellen Kontos, z. B. `person_c` | Meldet den zugehoerigen Yuvomi-Nutzer an, genau wie der Fingerabdruck-Login: Die Kennung ist der Schluessel in `secrets.json` (`individual_accounts`) bzw. in `fingerprint_mapping.py`; Benutzername und Passwort liegen lokal auf dem Geraet und werden **nicht** per MQTT gesendet. Setzt `active_app=yuvomi` und `display_mode=app`. Unbekannte Kennungen oder Kennungen ohne hinterlegte Zugangsdaten fuehren zu keiner Anmeldung (Warnung im Journal mit den bekannten Kennungen). Das alte Format `username:passwort` wird abgelehnt. Der Payload von `cmd/user` wird nie protokolliert. Wird von der Kindersicherung nicht blockiert. |

### Aktivitaet und Timer

MQTT-Nachrichten setzen den Auto-Logout individueller Nutzer **nicht**
zurueck; dieser reagiert nur auf Touch im Kiosk-Browser. Den Timer fuer den
automatischen Wechsel zur Diashow setzen Kommandos auf `cmd/#` zurueck, mit
Ausnahme von `cmd/notify`, `cmd/notify/clear`, `cmd/button/map` und
`cmd/slideshow/timeout`. Details siehe [`automatik.md`](automatik.md).

### Retained Nachrichten und Reconnect

Der Broker wiederholt gespeicherte (retained) Nachrichten beim Verbinden und
bei jedem Reconnect des Abonnenten. Der Supervisor ignoriert solche
wiederholten `cmd/#`-Nachrichten (Journal: `Retained Nachricht auf ...
ignoriert`), damit ein einmal gespeichertes Kommando nicht nach jedem
Broker-Neustart erneut ausgefuehrt wird. Live gesendete Kommandos wirken
unveraendert, auch wenn der Publisher das Retain-Flag setzt; nach einem
Reconnect werden sie aber nicht erneut ausgefuehrt. Bereits gespeicherte
retained Kommandos lassen sich mit einer leeren retained Nachricht loeschen:

```bash
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/mode' -n -r
```

### Beispiele

```bash
# Zur Diashow wechseln
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/mode' -m slideshow

# Zurueck zur App-Ansicht
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/mode' -m app

# Automatischen Wechsel zur Diashow nach 15 Minuten bzw. gar nicht
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/slideshow/timeout' -m 900
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/slideshow/timeout' -m 0

# Node-RED-Dashboard aktivieren
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/app' -m nodered

# Beliebige eigene URL anzeigen
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/app' -m 'custom:http://example.local/'

# Monitor-Strom aus- bzw. umschalten (schaltet das Relais)
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/display/power' -m false
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/display/power' -m toggle

# Wall Mode aktivieren
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/wallmode' -m true

# Kindersicherung ein- bzw. ausschalten
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/kindersicherung' -m true
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/kindersicherung' -m false

# Benachrichtigung anzeigen und wieder ausblenden
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/notify' -m 'Muell rausbringen!'
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/notify/clear' -m ''

# Benachrichtigung mit Markdown (mehrzeilig)
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/notify' -m '# Muell
**Heute** raus:
- Restmuell
- *Gelber Sack* und `Papier`'

# Dasselbe einzeilig mit bash-ANSI-C-Quoting
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/notify' -m $'# Muell\n**Heute** raus:\n- Restmuell'

# Taster 2 (langer Druck) neu auf Wallmode-Ein belegen
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/button/map' \
  -m '{"key":"2_long","topic":"cmd/wallmode","payload":"true"}'

# Als individueller Nutzer anmelden (Kennung aus secrets.json, ohne Passwort)
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/user' -m 'person_c'
```

### Markdown in `cmd/notify`

`notification_overlay.py` wandelt den Payload mit `md_to_pango()` in
Pango-Markup um und zeigt ihn in einem GTK4-Label an. Unterstuetzt wird
folgende Markdown-Teilmenge:

| Markdown | Darstellung |
|---|---|
| ``# Text``, ``## Text``, ``### Text`` | Ueberschrift H1-H3 (fett; xx-large / x-large / large) |
| ``**Text**`` oder ``__Text__`` | fett |
| ``*Text*`` oder ``_Text_`` | kursiv |
| ``~~Text~~`` | durchgestrichen |
| ``Code`` in einfachen Backticks | Monospace |
| Codeblock (Zeilen mit drei Backticks als Begrenzer) | Monospace, Zeile fuer Zeile |
| ``- Punkt``, ``* Punkt``, ``+ Punkt`` | Listenpunkt mit Aufzaehlungszeichen |
| ``1. Punkt`` | nummerierte Liste (die Nummer bleibt erhalten) |
| ``> Text`` | Zitat (kursiv, mit Balken) |
| ``---`` | Trennlinie |
| ``[Text](url)`` | nur der Text, unterstrichen (die URL wird nicht angezeigt, das Overlay ist nicht klickbar verlinkt) |

Hinweise:

- Nicht unterstuetzt: Tabellen, Bilder, verschachtelte Listen und HTML. Die
  Zeichen `<`, `>` und `&` werden maskiert und als normaler Text angezeigt.
- Zeilenumbrueche: Echte Zeilenumbrueche im Payload werden uebernommen. Ein
  woertliches `\n` wird nur dann in einen Umbruch umgewandelt, wenn der
  Payload keinen echten Zeilenumbruch enthaelt (z. B. `-m 'a\nb'`).
- Ein `_` mitten im Wort (z. B. `test_1_x`) wird nicht als kursiv gedeutet.
- Faellt das erzeugte Markup trotzdem durch die Pango-Pruefung, zeigt das
  Overlay den Rohtext an und schreibt `Ungueltiges Markup (...)` ins Log.
- Nach einem Update von `notification_overlay.py` muss der Prozess neu
  gestartet werden (Start ueber `~/.config/labwc/autostart`, nicht systemd).

## Supervisor: Fehlermeldungen des Fingerabdrucksensors (`cmd/notify`)

Fehler bei der Fingerabdruck-Erkennung veroeffentlicht der Supervisor selbst
auf `display/kueche/cmd/notify`; das Notification-Overlay zeigt sie an. Pro
Minute wird hoechstens eine solche Meldung gesendet
(`ERROR_NOTIFY_COOLDOWN_SECONDS` in `supervisor/hardware_fingerprint.py`).
Die Texte enthalten keine Markdown-Syntax und erscheinen daher unveraendert
(siehe "Markdown in `cmd/notify`").

| Text | Bedeutung |
|---|---|
| `Fingerabdrucksensor: keine Antwort - Verkabelung pruefen` | Timeout/Lesefehler (Datenleitungen, Sensorversorgung) |
| `Fingerabdrucksensor: Passwort-Pruefung fehlgeschlagen` | Sensor antwortet, Passwort stimmt nicht |
| `Fingerabdrucksensor: Fehler bei der Erkennung` | sonstiger Fehler, Details im Journal |

Das Fingerabdruck-Admin-Tool (`fingerprint-admin/`) sendet bewusst keine
MQTT-Meldungen und bleibt eigenstaendig nutzbar.

## Supervisor: Status (Ausgang, retained)

| Topic | Payload | Zweck |
|---|---|---|
| `display/kueche/status/health` (retain, LWT) | JSON `{"online": true/false, "ts"/"reason": ...}` | Heartbeat alle `HEARTBEAT_INTERVAL_SECONDS` (30s) sowie Last-Will bei Verbindungsverlust bzw. sauberem Shutdown. |
| `display/kueche/status/state` (retain) | JSON `{"display_power": true/false, "display_mode":"app/slideshow", "active_app":"...", "active_user":"...", "wall_mode": true/false, "child_lock": true/false, "slideshow_timeout": 600}` | Gesamtzustand des Displays, aktualisiert bei jeder relevanten Aenderung. `slideshow_timeout` in Sekunden, `0` = automatischer Wechsel zur Diashow aus. |
| `display/kueche/status/slideshow/timeout` (retain) | Ganzzahl Sekunden | Aktueller Diashow-Timeout (identisch zu `slideshow_timeout` in `status/state`); wird bei jeder Zustandsaenderung neu veroeffentlicht. |
| `display/kueche/status/kindersicherung` (retain) | `true` / `false` | Aktueller Zustand der Kindersicherung (identisch zu `child_lock` in `status/state`); wird beim Start des Supervisors explizit auf `false` gesetzt, unabhaengig von einem evtl. stehen gebliebenen retained Wert. Bei einem MQTT-Reconnect bleibt der Zustand erhalten und wird nur erneut veroeffentlicht. |
| `display/kueche/status/button/map` (retain) | JSON aller vier Tastenbelegungen | Aktuelle Button-Map, wird bei Verbindungsaufbau und nach jeder Aenderung per `cmd/button/map` neu veroeffentlicht. |

### Boolean-Konvention

Alle Ein-/Aus-Werte sind JSON-Booleans: `true` oder `false` (ohne Anfuehrungszeichen,
Kleinschreibung). Das gilt fuer `cmd/display/power` (zusaetzlich `toggle`),
`cmd/wallmode`, `cmd/kindersicherung` sowie fuer `status/kindersicherung` und die
Felder `display_power`, `wall_mode` und `child_lock` in `status/state`.

Werte wie `on`, `off`, `1`, `0` oder `"true"` (String) werden nicht mehr akzeptiert:
Der Supervisor schreibt eine Warnung ins Journal und aendert nichts. In Node-RED
muss ein Publisher deshalb einen echten Boolean senden; ein Subscriber erhaelt den
Payload zunaechst als Text und parst ihn bei Bedarf mit einem JSON-Node. In einer
gespeicherten Button-Map muessen Payloads wie `on` fuer `cmd/wallmode` oder
`cmd/display/power` per `cmd/button/map` auf `true` bzw. `false` umgestellt werden.

### Beispiele zum Lesen

```bash
mosquitto_sub -h mqtt -p 1883 -t 'display/kueche/status/state' -C 1 -W 3 -v
mosquitto_sub -h mqtt -p 1883 -t 'display/kueche/status/health' -C 1 -W 3 -v
mosquitto_sub -h mqtt -p 1883 -t 'display/kueche/status/slideshow/timeout' -C 1 -W 3 -v
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
gesteuert, siehe oben; der automatische Wechsel ueber
`cmd/slideshow/timeout`).

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

*Quelle: Code-Stand vom 08.10.2026 (`supervisor/kuechendisplay_supervisor.py`,
`config.py`, `state.py`, `button_mapper.py`, `hardware_buttons.py`,
`hardware_fingerprint.py`, `kiosk_controller.py`, `notification_overlay.py`,
`slideshow/slideshow_service.py`, `docs/diashow.md`, `docs/hardware.md`).
Display-Power (Relais an GPIO17), Kindersicherung und die Fehlermeldungen des
Fingerabdrucksensors laufen direkt im Haupt-Supervisor.
Markdown-Rendering in `notification_overlay.py` ergaenzt am 10.10.2026.
Auto-Logout per Touch, Diashow-Timeout (`cmd/slideshow/timeout`) und
Direkt-Logout ergaenzt am 15.10.2026 (siehe `docs/automatik.md`).
`cmd/user` per Kennung ohne Passwort, Reconnect-Verhalten der
Kindersicherung und Ignorieren retained Kommandos ergaenzt am 15.10.2026.*
