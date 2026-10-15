# Automatische Moduswechsel (Auto-Logout und Diashow)

*Stand: 15.10.2026*

Diese Seite beschreibt, wann der Supervisor automatisch einen individuellen
Yuvomi-Nutzer abmeldet und wann er automatisch zur Diashow wechselt. Beide
Automatiken laufen als getrennte Inaktivitaets-Watchdogs mit eigenen
Zeitgebern.

## Ueberblick

| Automatik | Standard | Zurueckgesetzt durch | Konfigurierbar |
|---|---|---|---|
| Auto-Logout individueller Nutzer (Rueckfall auf Familie) | 180 s (`USER_INACTIVITY_TIMEOUT_SECONDS`), Warnung 10 s vorher | nur Touch im Kiosk-Browser und Nutzerwechsel | nur im Code (`supervisor/config.py`) |
| Automatischer Wechsel zur Diashow | 600 s | Touch, Taster, Fingerabdruck, MQTT-Kommandos | per MQTT `cmd/slideshow/timeout`, `0` = aus |
| Direkter Logout | sofort | - | nicht abschaltbar |

## 1. Auto-Logout individueller Nutzer

Gilt nur, wenn ein individueller Nutzer angemeldet ist. Ist "Familie" aktiv,
tut der Watchdog nichts.

- Der Watchdog prueft alle 10 Sekunden die Zeit seit der letzten Aktivitaet.
- 10 Sekunden vor Ablauf erscheint die Benachrichtigung
  "Automatische Abmeldung in 10s" (`cmd/notify`).
- Bei Ablauf: Yuvomi-Logout des Nutzers, Login als Familie, Wall Mode wird
  aktiviert. Dabei werden die Session-Cookies im Python-Client und alle
  Chromium-Cookies geloescht.

### Was den Timer zuruecksetzt

- Echte Touch-Beruehrungen im Kiosk-Browser. Ein injiziertes Skript
  (`kiosk_controller.ACTIVITY_TRACKER_SCRIPT`) merkt sich nur `touchstart`;
  der Supervisor liest den Wert alle 5 Sekunden per CDP.
- Ein erfolgreicher Nutzerwechsel (z. B. per Fingerabdruck).

### Was den Timer NICHT zuruecksetzt

- MQTT-Nachrichten jeder Art (auch `cmd/notify`).
- Taster und Fingerabdruck-Erkennung desselben Nutzers.
- Mausbewegung, Klick, Tastatur, Scroll.
- Seitenaufbau, Reload oder Navigation (der Zeitstempel startet bei 0 und
  wird erst durch eine echte Beruehrung gesetzt).

Hintergrund: Die Abmelde-Warnung wird vom Supervisor selbst auf `cmd/notify`
veroeffentlicht und kommt ueber das Abo `cmd/#` wieder an. Fruehere Versionen
werteten jede MQTT-Nachricht als Aktivitaet; die Warnung setzte damit den
Timer zurueck und der Nutzer wurde nie abgemeldet.

## 2. Direkter Logout bei Seiten-/Moduswechsel

Ist ein individueller Nutzer angemeldet, erfolgt der Logout sofort (Rueckfall
auf Familie, Wall Mode an), bevor die neue Seite geladen wird:

| Ereignis | Verhalten |
|---|---|
| Wechsel zur Diashow (Taster 2, `cmd/mode=slideshow`, Diashow-Timer) | Logout, danach Navigation zur Diashow |
| Wechsel zu `nodered` oder `custom:<url>` (`cmd/app`) | Logout, danach Navigation zur App |
| Wechsel zu `yuvomi` (`cmd/app=yuvomi`, Rueckkehr per `cmd/mode=app`) | frisches Logout und Login als Familie |

Die Reihenfolge ist wichtig: Der Wall-Mode-Reload im Rueckfall muss noch die
Yuvomi-Seite treffen und nicht die Zielseite.

## 3. Automatischer Wechsel zur Diashow

Der Watchdog laeuft alle 10 Sekunden. Er wechselt zur Diashow, wenn
`display_mode == app`, der Timeout groesser als 0 ist und die Zeit seit der
letzten Aktivitaet den Timeout erreicht.

### Was den Diashow-Timer zuruecksetzt

- Touch im Kiosk-Browser
- Taster (auch bei aktiver Kindersicherung)
- Fingerabdruck-Erkennung
- MQTT-Kommandos auf `cmd/#`, ausgenommen `cmd/notify`, `cmd/notify/clear`,
  `cmd/button/map` und `cmd/slideshow/timeout`

Bei aktiver Kindersicherung blockiert das Overlay den Touch; Touch setzt
dann keinen der beiden Timer zurueck.

### Konfiguration per MQTT

| Topic | Payload | Wirkung |
|---|---|---|
| `display/kueche/cmd/slideshow/timeout` | `600` | Wechsel nach 600 Sekunden Inaktivitaet |
| `display/kueche/cmd/slideshow/timeout` | `0` | automatischer Wechsel aus |
| `display/kueche/status/slideshow/timeout` (retain) | Sekunden | aktueller Wert |

- Erlaubt sind `0` oder ganze Sekunden ab 30 (`SLIDESHOW_TIMEOUT_MIN_SECONDS`).
  Andere Werte werden abgelehnt und als Warnung geloggt.
- Der Wert wird in `~/.kuechendisplay/slideshow_timeout.json` gespeichert und
  ueberlebt einen Neustart. Fehlt die Datei, gilt der Default (600 s).
- Der Wert steht auch als `slideshow_timeout` in `status/state`.
- Das Intervall der Bilder (`display/kueche/diashow/set/intervall`) ist davon
  unabhaengig.

```bash
# Automatischen Wechsel abschalten
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/slideshow/timeout' -m 0

# Auf 15 Minuten setzen
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/slideshow/timeout' -m 900

# Aktuellen Wert lesen
mosquitto_sub -h mqtt -p 1883 -t 'display/kueche/status/slideshow/timeout' -C 1 -W 3 -v
```

## 4. Zusammenspiel

Beide Timer laufen unabhaengig. Typischer Ablauf bei angemeldetem Nutzer ohne
weitere Eingaben: nach 180 s Rueckfall auf Familie, nach 600 s (gerechnet ab
der letzten Aktivitaet) Wechsel zur Diashow, dabei kein weiterer Logout noetig.
Wird vorher die Diashow aufgerufen, erfolgt der Logout sofort.

Die Rueckkehr aus der Diashow erfolgt durch einen Taster, einen
Fingerabdruck oder `cmd/mode=app`. Ein Touch auf die Diashow-Seite setzt nur
den Timer zurueck, wechselt aber nicht den Modus.

## 5. Verifikation

```bash
sudo journalctl -u kuechendisplay-supervisor.service -f
```

Erwartete Logzeilen:

```text
Inaktivitaets-Warnung: automatische Abmeldung in 10s
Rueckfall von '<nutzer>' zu '<familie>' (Grund: Inaktivitaet, ...)
Direkter Logout von '<nutzer>' (Diashow)
Automatischer Diashow-Wechsel: nach 900s
Automatischer Diashow-Wechsel: deaktiviert
```

Test: Nutzer per Fingerabdruck anmelden, 3 Minuten nichts beruehren. Nach
der Warnung muss der Rueckfall auf Familie folgen. Danach mit
`mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/mode' -m slideshow`
den direkten Logout pruefen.

## 6. Troubleshooting

**Nutzer bleibt trotz Inaktivitaet angemeldet.** Pruefen, ob etwas den Timer
zuruecksetzt:

- Im Journal nach `Nutzerwechsel` oder Touch-Ereignissen suchen; MQTT-Traffic
  beeinflusst den Logout nicht mehr.
- `curl -s http://127.0.0.1:9222/json` zeigt die offenen CDP-Tabs. Liefert
  `window.__kuechendisplayLastActivity` einen neuen Wert ohne Beruehrung, ist
  ein Touch-Geraet oder Treiber die Ursache (z. B. Phantom-Touches).
- Ein Fingerabdruck desselben Nutzers waehrend der Sitzung zaehlt als
  Nutzerwechsel und setzt den Timer zurueck.

**Diashow startet nicht automatisch.** `status/slideshow/timeout` darf nicht
`0` sein, `display_mode` muss `app` sein, und Taster, Touch oder MQTT-Kommandos
duerfen den Timer nicht laufend zuruecksetzen.

**Abmelde-Warnung bleibt stehen.** Sie wird bei Touch oder Nutzerwechsel
automatisch zurueckgenommen; sonst per `cmd/notify/clear` ausblenden.
