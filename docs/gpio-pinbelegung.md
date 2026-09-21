# GPIO-Verkabelungsuebersicht

*Stand: 16.09.2026 (ueberarbeitet)*

Diese Seite dokumentiert die komplette physische Verkabelung des
40-Pin-Headers des Raspberry Pi im Kuechendisplay-Projekt. Sie ist das
Gegenstueck zu den funktionalen Beschreibungen in
[`docs/hardware.md`](hardware.md).

## Fingerabdrucksensor GROW R503 (UART, TTL 3,3V)

| Funktion | Physischer Pin (40-Pin-Header) | GPIO | Kabelfarbe |
|---|---|---|---|
| VCC | Pin 17 (3,3V) | - | Rot |
| Touch-Power (WAKEUP-Versorgung) | Pin 17 (3,3V, mit VCC zusammengefuehrt) | - | Weiss |
| GND | Pin 20 (gemeinsame Masse mit Tastern) | - | Schwarz |
| Sensor TXD -> Pi RXD | Pin 10 | GPIO15 | Braun |
| Pi TXD -> Sensor RXD | Pin 8 | GPIO14 | Gelb |
| WAKEUP | Pin 7 | GPIO4 | Blau |

VCC liegt an Pin 17 statt Pin 1 (Pin 1 wird nicht mehr benoetigt). Die
separate Touch-Power-Ader (weiss) wird mit VCC zusammengefuehrt, da der
Sensor aktuell dauerhaft mit Strom versorgt wird. GND ist Teil der
gemeinsamen Masseleitung mit den Tastern.

## Taster (4x Momentschalter, gegen gemeinsames GND, interner Pull-Up)

| Taster | Physischer Pin (40-Pin-Header) | GPIO | GND-Verbindung |
|---|---|---|---|
| Taster 1 | Pin 29 | GPIO5  | Pin 20 (gemeinsame Masse) |
| Taster 2 | Pin 31 | GPIO6  | Pin 20 (gemeinsame Masse) |
| Taster 3 | Pin 33 | GPIO13 | Pin 20 (gemeinsame Masse) |
| Taster 4 | Pin 35 | GPIO19 | Pin 20 (gemeinsame Masse) |

Alle 4 Taster-GND-Leitungen werden zusammen mit der Sensor-GND-Leitung
(schwarz) gebuendelt und gemeinsam an Pin 20 angeschlossen.

## Luefter (bereits vorinstalliert)

| Funktion | Physischer Pin (40-Pin-Header) | Kabelfarbe |
|---|---|---|
| 5V  | Pin 2 | Rot |
| GND | Pin 6 | Schwarz |

Bereits vor Projektbeginn installiert, keine Kollision mit
Fingerabdrucksensor oder Tastern (diese nutzen Pin 17/20, nicht Pin 2/6).

## 40-Pin-Header - Gesamtuebersicht mit belegten Pins und Kabelfarben

| Pin | Funktion links | Funktion rechts | Pin |
|---|---|---|---|
| 1 | 3V3 | 5V (Luefter, Rot) | 2 |
| 3 | GPIO2 | 5V | 4 |
| 5 | GPIO3 | GND (Luefter, Schwarz) | 6 |
| 7 | GPIO4 (R503 WAKEUP, Blau) | GPIO14 (R503 RXD-Pfad, Gelb) | 8 |
| 9 | GND | GPIO15 (R503 TXD-Pfad, Braun) | 10 |
| 11 | GPIO17 | GPIO18 | 12 |
| 13 | GPIO27 | GND | 14 |
| 15 | GPIO22 | GPIO23 | 16 |
| 17 | 3V3 (R503 VCC+Touch-Power, Rot/Weiss) | GPIO24 | 18 |
| 19 | GPIO10 | GND (Gem. Masse, Schwarz) | 20 |
| 21 | GPIO9 | GPIO25 | 22 |
| 23 | GPIO11 | GPIO8 | 24 |
| 25 | GND | GPIO7 | 26 |
| 27 | GPIO0 | GPIO1 | 28 |
| 29 | GPIO5 (Taster 1) | GND | 30 |
| 31 | GPIO6 (Taster 2) | GPIO12 | 32 |
| 33 | GPIO13 (Taster 3) | GND | 34 |
| 35 | GPIO19 (Taster 4) | GPIO16 | 36 |
| 37 | GPIO26 | GPIO20 | 38 |
| 39 | GND | GPIO21 | 40 |

**Hinweis:** Physischer Pin 1 wird in der aktuellen Planung nicht mehr
genutzt. Taster-Kabel haben keine dokumentierte Standardfarbe (abhaengig
vom verwendeten Kabelmaterial) - dort steht daher weiterhin die
Funktionsbezeichnung statt einer Farbe.
