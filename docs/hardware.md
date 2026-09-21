# Hardware

## Fingerabdrucksensor: GROW R503

- Kapazitaet: 200 Templates (IDs 0-199)
- Anschluss per UART an `/dev/serial0`, Baudrate 57600
- Verkabelung (Stand 16.09.2026, vollstaendige 40-Pin-Uebersicht siehe
  `docs/gpio-pinbelegung.md`):
  - VCC (rot) -> **ueber BC327-Transistor geschaltet** (siehe unten),
    kommt vom physischen Pin 17 (3,3V)
  - Touch-Power / WAKEUP-Versorgung (weiss) -> dauerhaft an physischem
    Pin 17 (3,3V) - unabhaengig vom Schaltzustand der Haupt-VCC
  - GND (schwarz) -> physischer Pin 20 (gemeinsame Masse mit den 4 Tastern)
  - Sensor TXD (braun) -> Pi RXD, physischer Pin 10 / GPIO15
  - Pi TXD (gelb) -> Sensor RXD, physischer Pin 8 / GPIO14
  - WAKEUP (blau) -> physischer Pin 7 / GPIO4
- WAKEUP-Signal (Finger aufgelegt) liegt an GPIO4
  (`FINGERPRINT_WAKEUP_GPIO` in `supervisor/config.py`), Pegel high im
  Standby, low bei aufgelegtem Finger. Da die Touch-Power-Versorgung immer
  aktiv ist, funktioniert WAKEUP auch dann, wenn die Haupt-VCC gerade
  abgeschaltet ist.

### Kapazitive Ein-/Ausschaltung der Haupt-VCC (BC327)

Damit der Sensor nicht mehr dauerhaft mit Strom versorgt wird, sondern nur
bei Beruehrung, sitzt ein **BC327-PNP-Transistor** als High-Side-Schalter
in der roten VCC-Leitung:

- Emitter -> Pi 3,3V (Pin 17)
- Basis -> 1-kOhm-Widerstand zu GPIO27 (physischer Pin 13,
  `FINGERPRINT_POWER_GPIO`) + 10-kOhm-Pull-up zu 3,3V
- Kollektor -> rote VCC-Leitung zum R503 (Sensor-Pin 1)

GPIO27 ist **aktiv LOW**: High (Ruhezustand, durch den Pull-up auch beim
Booten des Pi sichergestellt) sperrt den Transistor, der Sensor bleibt
stromlos. Zieht die Software GPIO27 auf Low, leitet der Transistor und der
Sensor wird versorgt. Ablauf in der Software
(`supervisor/hardware_fingerprint.py`): WAKEUP faellt -> GPIO27 auf Low ->
`FINGERPRINT_POWER_ON_DELAY_SECONDS` (100ms) warten (Sensor-Bootzeit lt.
Datenblatt ca. 50ms) -> `AutoIdentify` (0x32) ausfuehren (der Sensor bricht
laut Datenblatt nach ca. 10s ohne Finger von selbst ab) -> GPIO27 wieder
auf High. Nach dem Abschalten muss laut Datenblatt mindestens 2 Sekunden
gewartet werden, bevor erneut eingeschaltet wird
(`FINGERPRINT_POWER_MIN_OFF_SECONDS = 2.5` als Sicherheitsmarge).

Alle uebrigen Leitungen (GND, Touch-Power, WAKEUP, TXD, RXD) bleiben
unveraendert dauerhaft verbunden.

**Wichtig zum Sensor-Passwort:** Ein verlorenes Passwort macht den Sensor
ohne Werksreset/Hersteller-Tool unbrauchbar. Das aktuell gueltige Passwort
steht lokal in `fingerprint-admin/sensor_config.json` (nicht im
Repository, siehe `.gitignore`).

## Physische Taster (4x)

| Taster | GPIO | Physischer Pin | GND |
|---|---|---|---|
| 1 | GPIO5  | 29 | Pin 20 (gemeinsame Masse) |
| 2 | GPIO6  | 31 | Pin 20 (gemeinsame Masse) |
| 3 | GPIO13 | 33 | Pin 20 (gemeinsame Masse) |
| 4 | GPIO19 | 35 | Pin 20 (gemeinsame Masse) |

Alle 4 Taster-GND-Leitungen sind zusammen mit der Sensor-GND-Leitung
(schwarz) an Pin 20 gebuendelt.

Jeder Taster unterscheidet kurzen und langen Druck (Schwelle: 1,0 s, siehe
`LONG_PRESS_THRESHOLD_SECONDS`). Belegung ist per MQTT (`cmd/button/map`)
zur Laufzeit konfigurierbar, siehe `supervisor/button_mapper.py`. Ist die
Kindersicherung aktiv (siehe unten), loest jeder Tastendruck ausschliesslich
die Notify-Meldung "Kindersicherung" aus, unabhaengig von der konfigurierten
Belegung.

## Luefter (bereits vorinstalliert)

| Funktion | Physischer Pin | Kabelfarbe |
|---|---|---|
| 5V  | Pin 2 | Rot |
| GND | Pin 6 | Schwarz |

Bereits vor Projektbeginn installiert, keine Kollision mit
Fingerabdrucksensor oder Tastern (diese nutzen Pin 17/20, nicht Pin 2/6).

## Display-Power (MOSFET-Modul)

Die Monitor-Stromversorgung wird ueber ein **GERUI-Dual-MOSFET-Trigger-
Modul** (Low-Side, Logic-Level, aktiv HIGH) direkt geschaltet - keine
Software-Blanking-Loesung wie frueher per `wlopm` mehr. Der TRIG-Eingang
des Moduls haengt an GPIO17 (physischer Pin 11, `MONITOR_POWER_GPIO` in
`supervisor/config.py`) und wird direkt im Haupt-Supervisor
(`supervisor/kuechendisplay_supervisor.py`) angesteuert - ein eigener
Prozess ist dafuer nicht mehr noetig, da kein Zugriff auf die Wayland-
Sitzung erforderlich ist.

Das physische Ein-/Ausschalten der Monitor-Stromversorgung erzeugt am
HDMI-Ausgang dasselbe Hotplug-Ereignis wie das manuelle Ziehen/Stecken des
Kabels; der Wayland-Compositor (labwc) fragt das EDID danach automatisch
neu ab und reaktiviert den Ausgang von selbst. Ein zusaetzlicher
Software-Befehl (`wlopm`) ist dafuer nicht mehr erforderlich.

Stromversorgungsarchitektur (Netzteil, Step-Down-Konverter, Sicherung):
siehe die projektinterne Planungsnotiz zur Monitor-Stromschaltung
(nicht Teil dieses Repositories, lokal beim Projektinhaber archiviert).

## Kindersicherung

Per MQTT (`cmd/kindersicherung`, siehe `docs/mqtt.md`) lassen sich Taster,
Fingerabdrucksensor und Touch-Eingaben im Kiosk-Browser gemeinsam sperren:

- Taster: jeder Druck loest nur die Notify-Meldung "Kindersicherung" aus.
- Fingerabdrucksensor: GPIO27 bleibt dauerhaft High, der Sensor wird bei
  Beruehrung nicht mit Strom versorgt; stattdessen erscheint ebenfalls die
  Notify-Meldung.
- Touchscreen: Der Bildschirm bleibt an und zeigt weiterhin normal an, was
  gerade aufgerufen ist. Ein transparentes Overlay im Kiosk-Browser
  (`supervisor/kiosk_controller.py`, `KioskController.set_touch_blocked`)
  faengt alle Touch-/Klick-Eingaben ab.
- Die Kindersicherung ist nicht persistent und startet nach jedem Neustart
  des Supervisors immer im Zustand "aus". `cmd/button/map` bleibt auch bei
  aktiver Kindersicherung nutzbar.

## Vollstaendige GPIO-/Pin-Uebersicht

Die komplette Zuordnung aller 40 Header-Pins inkl. Kabelfarben ist in
[`docs/gpio-pinbelegung.md`](gpio-pinbelegung.md) dokumentiert.
