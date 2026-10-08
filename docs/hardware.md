# Hardware

*Stand: 08.10.2026. Die vollstaendige 40-Pin-Uebersicht steht in
[`docs/gpio-pinbelegung.md`](gpio-pinbelegung.md).*

## Stromversorgung

```
Netzteil (ca. 26 V DC, max. 0,78 A) --[Sicherung]--> Step-Down-Konverter (5,0-5,2 V)
   Zweig 1: Step-Down-USB-Ausgang --> Raspberry Pi (USB-C)
   Zweig 2: Step-Down-5V --> Relais (VCC, COM) --NC--> Monitor-Breakout
   Masse:   alle Massen auf einer Masseklemme (Pi-GND an Pin 39)
```

- Der Pi wird vom Step-Down ueber USB versorgt, nicht ueber die GPIO-Pins.
- Relais-VCC und die Monitor-Plusleitung kommen direkt vom Step-Down; die
  Relais-Masse und die Monitor-Masse liegen an der Masseklemme.
- Zwischen Step-Down-GND und Masseklemme gibt es eine direkte Verbindung. Die
  zusaetzliche Verbindung ueber den Pi (Pin 39) ist redundant, aber
  unschaedlich.
- Gemessene Last: Monitor ca. 1,3 A bei 5 V, Gesamtsystem geschaetzt
  2,3-3,3 A. Leitungsquerschnitt der Hauptleitungen 0,5 mm2, maximal ca.
  20 cm.
- **Sicherungen (Empfehlung):** 26-V-Eingang des Step-Down 1-1,5 A traege
  (DC-Rating mindestens 32 V); Monitor-Zweig vor dem Relais 2-3 A traege;
  Pi-Zweig 3 A traege (optional, da der Pi ueber USB geschuetzt ist).

## Fingerabdrucksensor: GROW R503

- Kapazitaet: 200 Templates (IDs 0-199)
- Anschluss per UART an `/dev/serial0`, Baudrate 57600
- Verkabelung (Details in `docs/gpio-pinbelegung.md`):
  - VCC (rot) -> **ueber BC327-Transistor geschaltet** (siehe unten),
    Emitter an Pin 17 (3,3V)
  - Touch-Power / WAKEUP-Versorgung (weiss) -> dauerhaft an Pin 17 (3,3V),
    unabhaengig vom Schaltzustand der Haupt-VCC
  - GND (schwarz) -> Masseklemme
  - Sensor TXD (gelb) -> Pi RXD, Pin 10 / GPIO15
  - Pi TXD (Pin 8 / GPIO14) -> Sensor RXD (braun)
  - WAKEUP (blau) -> Pin 7 / GPIO4
- Die Adernfarben koennen je nach Kabel variieren; entscheidend ist die
  Funktion. Vertauschte Datenleitungen sind ein haeufiger Fehler.
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
- Basis -> 1-kOhm-Widerstand zu GPIO27 (Pin 13, `FINGERPRINT_POWER_GPIO`)
  + 10-kOhm-Pull-up zu 3,3V
- Kollektor -> rote VCC-Leitung zum R503 (Sensor-Pin 1)

GPIO27 ist **aktiv LOW**: High (Ruhezustand, durch den Pull-up auch beim
Booten des Pi sichergestellt) sperrt den Transistor, der Sensor bleibt
stromlos. Zieht die Software GPIO27 auf Low, leitet der Transistor und der
Sensor wird versorgt. Ablauf in der Software
(`supervisor/hardware_fingerprint.py`): WAKEUP faellt -> GPIO27 auf Low ->
`FINGERPRINT_POWER_ON_DELAY_SECONDS` (100 ms) warten (Sensor-Bootzeit lt.
Datenblatt ca. 50 ms) -> `AutoIdentify` (0x32) ausfuehren (der Sensor bricht
laut Datenblatt nach ca. 10 s ohne Finger von selbst ab) -> GPIO27 wieder
auf High. Nach dem Abschalten muss laut Datenblatt mindestens 2 Sekunden
gewartet werden, bevor erneut eingeschaltet wird
(`FINGERPRINT_POWER_MIN_OFF_SECONDS = 2.5` als Sicherheitsmarge).

Alle uebrigen Leitungen (GND, Touch-Power, WAKEUP, TXD, RXD) bleiben
dauerhaft verbunden.

### Fehlermeldungen im Betrieb

Schlaegt die Erkennung fehl, meldet der Supervisor das ueber den
MQTT-Notify-Kanal (`display/kueche/cmd/notify`, siehe `docs/mqtt.md`) und
zeigt es im Notification-Overlay an. Wiederholte Fehler werden auf eine
Meldung pro Minute gedrosselt (`ERROR_NOTIFY_COOLDOWN_SECONDS`).

| Meldung | Bedeutung |
|---|---|
| Fingerabdrucksensor: keine Antwort - Verkabelung pruefen | Timeout oder Lesefehler (Datenleitungen, Sensorversorgung) |
| Fingerabdrucksensor: Passwort-Pruefung fehlgeschlagen | Sensor antwortet, Passwort stimmt nicht |
| Fingerabdrucksensor: Fehler bei der Erkennung | sonstiger Fehler (Details im Journal) |

### Fingerabdruck-Verwaltung (Admin-Tool)

Das Admin-Tool (`fingerprint-admin/`) stoppt waehrend der Nutzung den
Supervisor. Damit der Sensor dann trotzdem Strom hat, schaltet
`fingerprint-admin/start_fingerprint_gui.sh` GPIO27 per `pinctrl` dauerhaft
auf Low und nach dem Beenden wieder auf High (danach 2,5 s Pause, dann wird
der Supervisor gestartet). Mit `SENSOR_POWER_GPIO=none bash
start_fingerprint_gui.sh` bleibt die Steuerung aus, z. B. bei einem
dauerhaft versorgten Sensor. Die Python-GUI selbst bleibt unabhaengig vom
Kuechendisplay und sendet keine MQTT-Meldungen.

**Wichtig zum Sensor-Passwort:** Ein verlorenes Passwort macht den Sensor
ohne Werksreset/Hersteller-Tool unbrauchbar. Das aktuell gueltige Passwort
steht lokal in `fingerprint-admin/sensor_config.json` (nicht im
Repository, siehe `.gitignore`).

## Physische Taster (4x)

| Taster | GPIO | Pin | GND |
|---|---|---|---|
| 1 | GPIO5  | 29 | Masseklemme |
| 2 | GPIO6  | 31 | Masseklemme |
| 3 | GPIO13 | 33 | Masseklemme |
| 4 | GPIO19 | 35 | Masseklemme |

Jeder Taster unterscheidet kurzen und langen Druck (Schwelle: 1,0 s, siehe
`LONG_PRESS_THRESHOLD_SECONDS`). Belegung ist per MQTT (`cmd/button/map`)
zur Laufzeit konfigurierbar, siehe `supervisor/button_mapper.py`. Ist die
Kindersicherung aktiv (siehe unten), loest jeder Tastendruck ausschliesslich
die Notify-Meldung "Kindersicherung" aus, unabhaengig von der konfigurierten
Belegung.

## Luefter (bereits vorinstalliert)

| Funktion | Pin | Kabelfarbe |
|---|---|---|
| 5V  | Pin 4 | Rot |
| GND | Pin 6 | Schwarz |

## Display-Power (Relais-Modul)

Die Monitor-Stromversorgung wird ueber ein **Relais-Modul** (Optokoppler,
Trigger-Jumper auf **High-Level-Trigger**) geschaltet - keine
Software-Blanking-Loesung wie frueher per `wlopm`. Der Trigger-Eingang
haengt an GPIO17 (Pin 11, `MONITOR_POWER_GPIO` in `supervisor/config.py`) und
wird direkt im Haupt-Supervisor (`supervisor/kuechendisplay_supervisor.py`)
angesteuert; ein eigener Prozess ist dafuer nicht noetig.

- Die Monitor-Plusleitung laeuft ueber **COM/NC**. Im Ruhezustand (Relais
  abgefallen, GPIO nicht angesteuert, z. B. waehrend des Bootens) ist der
  Monitor an. NO bleibt unbelegt.
- GPIO17 HIGH zieht das Relais an, die NC-Verbindung oeffnet, der Monitor ist
  aus. Der Supervisor invertiert die Logik (`active_high=False`): `on()` =
  GPIO LOW = Monitor an, `off()` = GPIO HIGH = Monitor aus.
- Versorgung des Relais-Moduls: VCC direkt vom Step-Down, GND von der
  Masseklemme.

Das physische Ein-/Ausschalten der Monitor-Stromversorgung erzeugt am
HDMI-Ausgang dasselbe Hotplug-Ereignis wie das Ziehen/Stecken des Kabels.
Im aktuellen Aufbau wird das Bild nach dem Wiedereinschalten wieder erkannt;
bei Problemen siehe `docs/troubleshooting.md`.

### Monitorkabel (USB-C-Breakout)

Alle sechs Adern des USB-Kabels zum Monitor sind belegt:

| Ader | Anschluss |
|---|---|
| VBUS | geschaltete 5V ueber das Relais (COM/NC) |
| GND | Masseklemme |
| CC1, CC2 | je 10 kOhm nach VBUS (signalisiert dem Monitor bis zu 3 A bei 5 V) |
| D+, D- | USB-Datenleitungen zum Raspberry Pi (Touch) |

Die Touch-Funktion braucht die CC-Widerstaende; ohne sie funktioniert nur
das Display (VBUS/GND), nicht der Touch. Der Pi liefert fuer Touch nur D+/D-
und die gemeinsame Masse; eine VBUS-Verbindung vom Pi zum Monitor besteht
nicht.

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
