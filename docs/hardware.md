# Hardware

## Fingerabdrucksensor: GROW R503

- Kapazitaet: 200 Templates (IDs 0-199)
- Anschluss per UART an `/dev/serial0`, Baudrate 57600
- Verkabelung (Stand 16.09.2026, vollstaendige 40-Pin-Uebersicht siehe
  `docs/gpio-pinbelegung.md`):
  - VCC (rot) -> physischer Pin 17 (3,3V)
  - Touch-Power / WAKEUP-Versorgung (weiss) -> ebenfalls physischer Pin 17
    (mit VCC zusammengefuehrt, da der Sensor aktuell dauerhaft mit Strom
    versorgt wird)
  - GND (schwarz) -> physischer Pin 20 (gemeinsame Masse mit den 4 Tastern)
  - Sensor TXD (braun) -> Pi RXD, physischer Pin 10 / GPIO15
  - Pi TXD (gelb) -> Sensor RXD, physischer Pin 8 / GPIO14
  - WAKEUP (blau) -> physischer Pin 7 / GPIO4
- WAKEUP-Signal (Finger aufgelegt) liegt an GPIO4
  (`FINGERPRINT_WAKEUP_GPIO` in `supervisor/config.py`), Pegel high im
  Standby, low bei aufgelegtem Finger.
- Physischer Pin 1 wird in der aktuellen Verkabelung nicht mehr genutzt
  (VCC wurde auf Pin 17 verlegt).
- Laut Hersteller-Datenblatt besitzt der Sensor zwei getrennte
  Versorgungsleitungen: VCC (Pin 1 am Sensorstecker) fuer die komplette
  Sensor-Elektronik (~100-120 mA im Betrieb) sowie eine separate
  "Touch-Power"-Leitung (3,3VT, Pin 6 am Sensorstecker) ausschliesslich
  fuer die kapazitive Beruehrungserkennung, die im Standby nur ca. 2 uA
  zieht. Aktuell sind beide Leitungen auf denselben Dauerstrom-Pin (Pin 17)
  gelegt. Das ist die Grundlage fuer die geplante Erweiterung, bei der nur
  die Touch-Power-Leitung dauerhaft aktiv bleibt und die Haupt-VCC erst per
  MOSFET eingeschaltet wird, sobald WAKEUP ausloest.

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
zur Laufzeit konfigurierbar, siehe `supervisor/button_mapper.py`.

## Luefter (bereits vorinstalliert)

| Funktion | Physischer Pin | Kabelfarbe |
|---|---|---|
| 5V  | Pin 2 | Rot |
| GND | Pin 6 | Schwarz |

Bereits vor Projektbeginn installiert, keine Kollision mit
Fingerabdrucksensor oder Tastern (diese nutzen Pin 17/20, nicht Pin 2/6).

## Display-Power

Physisches An-/Ausschalten des Displays erfolgt ueber `wlopm` in einem
eigenen Prozess (`supervisor/display_power_control.py`), da dieser
Zugriff auf die grafische Wayland-Sitzung braucht, den der
systemd-Supervisor nicht hat. Der Output-Name (`WLOPM_OUTPUT_NAME`,
aktuell `HDMI-A-1`) sollte nach jedem Hardware-Wechsel per `wlopm` (ohne
Argumente) neu verifiziert werden. Hinweis: `wlopm` schaltet nur das
Signal aus (Software-Blanking), nicht die tatsaechliche Stromversorgung
des Monitors - eine geplante Erweiterung soll dies um eine echte
MOSFET-Stromabschaltung ergaenzen.

## Vollstaendige GPIO-/Pin-Uebersicht

Die komplette Zuordnung aller 40 Header-Pins inkl. Kabelfarben ist in
[`docs/gpio-pinbelegung.md`](gpio-pinbelegung.md) dokumentiert.
