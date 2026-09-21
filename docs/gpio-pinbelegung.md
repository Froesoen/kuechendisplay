# GPIO-Verkabelungsuebersicht

*Stand: 21.09.2026 (ueberarbeitet - kapazitive Fingerprint-Schaltung und
Monitor-MOSFET ergaenzt)*

Diese Seite dokumentiert die komplette physische Verkabelung des
40-Pin-Headers des Raspberry Pi im Kuechendisplay-Projekt. Sie ist das
Gegenstueck zu den funktionalen Beschreibungen in
[`docs/hardware.md`](hardware.md).

## Fingerabdrucksensor GROW R503 (UART, TTL 3,3V)

| Funktion | Physischer Pin (40-Pin-Header) | GPIO | Kabelfarbe |
|---|---|---|---|
| VCC (ueber BC327-Transistor geschaltet) | Pin 17 (3,3V, ueber Emitter/Kollektor des BC327) | - | Rot |
| Touch-Power (WAKEUP-Versorgung, dauerhaft) | Pin 17 (3,3V, direkt) | - | Weiss |
| GND | Pin 20 (gemeinsame Masse mit Tastern) | - | Schwarz |
| Sensor TXD -> Pi RXD | Pin 10 | GPIO15 | Braun |
| Pi TXD -> Sensor RXD | Pin 8 | GPIO14 | Gelb |
| WAKEUP | Pin 7 | GPIO4 | Blau |
| VCC-Schalter (BC327-Basis, ueber 1kOhm) | Pin 13 | GPIO27 | neu, keine Standardfarbe |

Die Touch-Power-Ader (weiss) bleibt direkt und dauerhaft an Pin 17
angeschlossen. Die VCC-Ader (rot) fuehrt stattdessen ueber den Kollektor
eines BC327-PNP-Transistors, dessen Emitter an Pin 17 und dessen Basis
(ueber 1kOhm-Widerstand plus 10kOhm-Pull-up nach Pin 17) an GPIO27 (Pin 13)
haengt. Details und Schaltplan: siehe projektinterne Anleitung zur
kapazitiven Fingerprint-Schaltung. GND ist weiterhin Teil der gemeinsamen
Masseleitung mit den Tastern.

## Monitor-Stromversorgung (GERUI-Dual-MOSFET-Modul)

| Funktion | Physischer Pin (40-Pin-Header) | GPIO |
|---|---|---|
| TRIG (MOSFET-Modul, aktiv HIGH = Monitor an) | Pin 11 | GPIO17 |
| Steuer-GND (Referenz fuer TRIG) | Pin 9 | GND |

Das MOSFET-Modul schaltet Low-Side (OUT- geschaltet, OUT+ durchverbunden)
in der separaten 5V-Stromversorgung des Monitors (eigenes Netzteil ->
Step-Down-Konverter, nicht Teil des 40-Pin-Headers). Details zur
vorgelagerten Stromversorgungsarchitektur (Netzteil, Step-Down-Konverter,
Sicherung): siehe projektinterne Planungsnotiz zur Monitor-Stromschaltung.

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
Fingerabdrucksensor, Tastern oder dem MOSFET-Steuersignal (diese nutzen
Pin 17/20/13/11/9, nicht Pin 2/6).

## 40-Pin-Header - Gesamtuebersicht mit belegten Pins und Kabelfarben

| Pin | Funktion links | Funktion rechts | Pin |
|---|---|---|---|
| 1 | 3V3 | 5V (Luefter, Rot) | 2 |
| 3 | GPIO2 | 5V | 4 |
| 5 | GPIO3 | GND (Luefter, Schwarz) | 6 |
| 7 | GPIO4 (R503 WAKEUP, Blau) | GPIO14 (R503 RXD-Pfad, Gelb) | 8 |
| 9 | GND (Monitor-MOSFET Steuer-GND) | GPIO15 (R503 TXD-Pfad, Braun) | 10 |
| 11 | GPIO17 (Monitor-MOSFET TRIG) | GPIO18 | 12 |
| 13 | GPIO27 (R503 VCC-Schalter, BC327-Basis) | GND | 14 |
| 15 | GPIO22 | GPIO23 | 16 |
| 17 | 3V3 (R503 VCC ueber BC327 + Touch-Power, Rot/Weiss) | GPIO24 | 18 |
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
Funktionsbezeichnung statt einer Farbe. Pin 9 wird sowohl als allgemeine
GND-Referenz als auch konkret als Steuer-GND fuer das Monitor-MOSFET-Modul
genutzt (beide GND-Pins sind elektrisch identisch).
