# GPIO-Verkabelungsuebersicht

*Stand: 08.10.2026 (Relais statt MOSFET, Luefter an Pin 4/6, gemeinsame
Masseklemme an Pin 39, R503-Adernfarben an Pin 8/10 korrigiert)*

Diese Seite dokumentiert die komplette physische Verkabelung des
40-Pin-Headers des Raspberry Pi im Kuechendisplay-Projekt. Sie ist das
Gegenstueck zu den funktionalen Beschreibungen in
[`docs/hardware.md`](hardware.md). Alle hier nicht aufgefuehrten Pins sind
frei.

## Belegungsuebersicht

| Pin | GPIO | Funktion | Kabel / Bauteil |
|---|---|---|---|
| 4 | - | Luefter 5V | rot |
| 6 | - | Luefter GND | schwarz |
| 7 | GPIO4 | R503 WAKEUP | blau |
| 8 | GPIO14 | Pi TXD -> Sensor RXD | R503, braun |
| 10 | GPIO15 | Sensor TXD -> Pi RXD | R503, gelb |
| 11 | GPIO17 | Relais-Trigger (Monitor-Strom) | Relais-Eingang IN |
| 13 | GPIO27 | BC327-Basis (R503-VCC-Schalter), ueber 1 kOhm | Transistor, mittlerer Anschluss |
| 17 | - | 3,3V: R503 Touch-Power (weiss) und BC327-Emitter (+ 10-kOhm-Pull-up der Basis) | weiss / Transistor links |
| 29 | GPIO5 | Taster 1 | - |
| 31 | GPIO6 | Taster 2 | - |
| 33 | GPIO13 | Taster 3 | - |
| 35 | GPIO19 | Taster 4 | - |
| 39 | - | GND-Verteilung (Masseklemme) | gemeinsame Masse aller Komponenten |

## Fingerabdrucksensor GROW R503 (UART, TTL 3,3V)

| Funktion | Pin | GPIO | Kabelfarbe |
|---|---|---|---|
| VCC (ueber BC327-Transistor geschaltet) | Kollektor des BC327 (Emitter an Pin 17) | - | Rot |
| Touch-Power (WAKEUP-Versorgung, dauerhaft) | Pin 17 (3,3V, direkt) | - | Weiss |
| GND | Masseklemme (Pin 39) | - | Schwarz |
| Sensor TXD -> Pi RXD | Pin 10 | GPIO15 | Gelb |
| Pi TXD -> Sensor RXD | Pin 8 | GPIO14 | Braun |
| WAKEUP | Pin 7 | GPIO4 | Blau |
| VCC-Schalter (BC327-Basis, ueber 1 kOhm) | Pin 13 | GPIO27 | keine Standardfarbe |

Die Touch-Power-Ader (weiss) bleibt direkt und dauerhaft an Pin 17
angeschlossen. Die VCC-Ader (rot) fuehrt ueber den Kollektor eines
BC327-PNP-Transistors, dessen Emitter an Pin 17 und dessen Basis (ueber
1-kOhm-Widerstand und mit einem 10-kOhm-Pull-up nach Pin 17) an GPIO27
(Pin 13) haengt. Details und Schaltplan: siehe projektinterne Anleitung zur
kapazitiven Fingerprint-Schaltung. **Wichtig:** Massgeblich ist die
Funktion, nicht die Adernfarbe. Der Sensor-TXD muss an Pin 10, der
Sensor-RXD an Pin 8; vertauschte Datenleitungen fuehren zu "Failed to read
data from sensor" (siehe `docs/troubleshooting.md`).

## Monitor-Stromversorgung (Relais-Modul)

| Funktion | Pin | GPIO |
|---|---|---|
| Relais-Trigger IN (Jumper auf High-Level-Trigger) | Pin 11 | GPIO17 |

Das Relais-Modul wird nicht vom Header versorgt:

- Relais VCC (5V): direkt vom Step-Down-Konverter
- Relais GND: Masseklemme
- Kontakte: COM = geschaltete 5V-Leitung vom Step-Down, NC = zum
  Monitor-Breakout-Board (NO bleibt unbelegt)

So ist der Monitor im Ruhezustand (Relais abgefallen, z. B. waehrend des
Bootens) an. GPIO17 HIGH zieht das Relais an und schaltet den Monitor aus.
Die Invertierung uebernimmt der Supervisor (`OutputDevice(active_high=False)`).
Details zur Stromversorgung: siehe `docs/hardware.md`.

## Taster (4x Momentschalter, gegen gemeinsames GND, interner Pull-Up)

| Taster | Pin | GPIO | GND-Verbindung |
|---|---|---|---|
| Taster 1 | Pin 29 | GPIO5  | Masseklemme (Pin 39) |
| Taster 2 | Pin 31 | GPIO6  | Masseklemme (Pin 39) |
| Taster 3 | Pin 33 | GPIO13 | Masseklemme (Pin 39) |
| Taster 4 | Pin 35 | GPIO19 | Masseklemme (Pin 39) |

## Luefter (bereits vorinstalliert)

| Funktion | Pin | Kabelfarbe |
|---|---|---|
| 5V  | Pin 4 | Rot |
| GND | Pin 6 | Schwarz |

Bereits vor Projektbeginn installiert. Pin 2 und Pin 4 sind beide 5V; der
Luefter haengt an Pin 4.

## Masseklemme (Pin 39)

Alle Massen laufen zusammen auf einer Klemme: Pi-GND (Pin 39), Step-Down-GND,
Relais-GND, Monitor-Breakout-GND, Taster und R503. Zwischen Step-Down und
Klemme gibt es eine zusaetzliche direkte Verbindung; die Verbindung ueber den
Pi ist damit redundant, aber unschaedlich.

## 40-Pin-Header - Gesamtuebersicht

| Pin | Funktion links | Funktion rechts | Pin |
|---|---|---|---|
| 1 | 3V3 (frei) | 5V (frei) | 2 |
| 3 | GPIO2 | 5V (Luefter, Rot) | 4 |
| 5 | GPIO3 | GND (Luefter, Schwarz) | 6 |
| 7 | GPIO4 (R503 WAKEUP, Blau) | GPIO14 (Pi TXD, R503 Braun) | 8 |
| 9 | GND (frei) | GPIO15 (Pi RXD, R503 Gelb) | 10 |
| 11 | GPIO17 (Relais-Trigger) | GPIO18 | 12 |
| 13 | GPIO27 (BC327-Basis, R503-VCC-Schalter) | GND | 14 |
| 15 | GPIO22 | GPIO23 | 16 |
| 17 | 3V3 (R503 Touch-Power Weiss, BC327-Emitter) | GPIO24 | 18 |
| 19 | GPIO10 | GND (frei) | 20 |
| 21 | GPIO9 | GPIO25 | 22 |
| 23 | GPIO11 | GPIO8 | 24 |
| 25 | GND | GPIO7 | 26 |
| 27 | GPIO0 | GPIO1 | 28 |
| 29 | GPIO5 (Taster 1) | GND | 30 |
| 31 | GPIO6 (Taster 2) | GPIO12 | 32 |
| 33 | GPIO13 (Taster 3) | GND | 34 |
| 35 | GPIO19 (Taster 4) | GPIO16 | 36 |
| 37 | GPIO26 | GPIO20 | 38 |
| 39 | GND (Masseklemme) | GPIO21 | 40 |

**Hinweis:** Pin 1, 2, 9 und 20 werden in der aktuellen Verkabelung nicht
genutzt. Taster-Kabel haben keine dokumentierte Standardfarbe (abhaengig vom
verwendeten Kabelmaterial); dort steht daher die Funktionsbezeichnung.
