# Hardware

## Fingerabdrucksensor: GROW R503

- Kapazitaet: 200 Templates (IDs 0-199)
- Anschluss per UART an `/dev/serial0`, Baudrate 57600
- Verkabelung:
  - TXD (Sensor) -> RXD (Pi), physischer Pin 10 / GPIO15
  - RXD (Sensor) <- TXD (Pi), physischer Pin 8 / GPIO14
  - VCC -> physischer Pin 1
  - GND -> physischer Pin 6
- WAKEUP-Signal (Finger aufgelegt) liegt an GPIO4 (`FINGERPRINT_WAKEUP_GPIO` in `supervisor/config.py`), Pegel high im Standby, low bei aufgelegtem Finger.

**Wichtig zum Sensor-Passwort:** Ein verlorenes Passwort macht den Sensor ohne Werksreset/Hersteller-Tool unbrauchbar. Das aktuell gueltige Passwort steht lokal in `fingerprint-admin/sensor_config.json` (nicht im Repository, siehe `.gitignore`).

## Physische Taster (4x)

| Taster | GPIO | Physischer Pin |
|---|---|---|
| 1 | GPIO5  | 29 |
| 2 | GPIO6  | 31 |
| 3 | GPIO13 | 33 |
| 4 | GPIO19 | 35 |

Jeder Taster unterscheidet kurzen und langen Druck (Schwelle: 1,0 s, siehe `LONG_PRESS_THRESHOLD_SECONDS`). Belegung ist per MQTT (`cmd/button/map`) zur Laufzeit konfigurierbar, siehe `supervisor/button_mapper.py`.

## Display-Power

Physisches An-/Ausschalten des Displays erfolgt ueber `wlopm` in einem eigenen Prozess (`supervisor/display_power_control.py`), da dieser Zugriff auf die grafische Wayland-Sitzung braucht, den der systemd-Supervisor nicht hat. Der Output-Name (`WLOPM_OUTPUT_NAME`, aktuell `HDMI-A-1`) sollte nach jedem Hardware-Wechsel per `wlopm` (ohne Argumente) neu verifiziert werden.
