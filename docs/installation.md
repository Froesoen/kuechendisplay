# Installation auf dem Raspberry Pi

*Stand: 08.10.2026*

## Voraussetzungen

- Raspberry Pi OS mit labwc-Desktop, UART aktiviert (`raspi-config`: serielle
  Hardware-Schnittstelle an, Login-Shell ueber seriell aus)
- Zugriff auf einen MQTT-Broker (Hostname `mqtt` im lokalen Netz)
- Laufendes Yuvomi-Frontend, erreichbar unter der in `supervisor/config.py` hinterlegten `YUVOMI_BASE_URL`
- Verkabelung gemaess [`docs/hardware.md`](hardware.md) und
  [`docs/gpio-pinbelegung.md`](gpio-pinbelegung.md) bereits umgesetzt,
  insbesondere der BC327-Transistor an GPIO27 (Fingerprint-VCC) und das
  Relais-Modul an GPIO17 (Monitor-Stromversorgung, High-Level-Trigger,
  Monitor ueber COM/NC).

**Verhalten ohne laufende Software:** Das Relais ist abgefallen, der Monitor
hat Strom (NC geschlossen); der Fingerabdrucksensor bleibt dank Pull-up am
BC327 stromlos. Der Monitor ist damit auch waehrend des Bootens an. Erst der
Supervisor schaltet ihn bei Bedarf ueber GPIO17 aus.

## 1. Repository klonen

```bash
git clone https://github.com/Froesoen/kuechendisplay.git ~/kuechendisplay
```

## 2. Secrets anlegen (nicht im Repo)

```bash
mkdir -p ~/.kuechendisplay
cp ~/kuechendisplay/supervisor/secrets.json.example ~/.kuechendisplay/secrets.json
nano ~/.kuechendisplay/secrets.json   # echte Zugangsdaten eintragen
```

## 3. Python-Umgebung

Im Referenz-Setup laeuft der Supervisor mit der venv `~/kuechendisplay-venv`;
dieselbe venv nutzt auch die Fingerabdruck-GUI (Schritt 6). Der Supervisor
benoetigt Systemzugriff auf GPIO/UART. Benoetigte Pakete: `paho-mqtt`,
`pychrome`, `requests`, `gpiozero`, `pyserial`,
`adafruit-circuitpython-fingerprint`.

## 4. systemd-Dienst einrichten

Dienstname: `kuechendisplay-supervisor.service`, startet
`kuechendisplay_supervisor.py` aus `~/kuechendisplay/supervisor/` mit dem
Python der venv aus Schritt 3. Der Dateiname ist bewusst gleich geblieben
(ohne `_v2`-Suffix), damit bestehende Autostart-/systemd-Verdrahtung
unveraendert bleibt. Der Supervisor steuert die Monitor-Stromversorgung
(GPIO17) und die Fingerprint-VCC (GPIO27) direkt selbst - dafuer ist kein
zusaetzlicher Dienst und kein `wlopm` noetig.

## 5. Zusatzprozess in ~/.config/labwc/autostart

- `notification_overlay.py` (Notification-Overlay). Es benoetigt `gir1.2-gtk4layershell-1.0` (GTK4, nicht `gir1.2-gtklayershell-0.1`), `paho-mqtt` und laeuft mit System-Python (nicht der venv). Start mit `LD_PRELOAD` fuer `libgtk4-layer-shell.so.0`:

```bash
LD_PRELOAD=/usr/lib/aarch64-linux-gnu/libgtk4-layer-shell.so.0 python3 ~/kuechendisplay/supervisor/notification_overlay.py
```

Das Overlay zeigt auch die Fehlermeldungen des Supervisors an (siehe
[`docs/mqtt.md`](mqtt.md)). Meldungen bleiben stehen (`NOTIFY_DISPLAY_SECONDS`
ist `None`), bis sie angetippt oder per `cmd/notify/clear` (Standard: Taster 4
kurz) ausgeblendet werden. Die Display-Power-Steuerung (frueher per `wlopm` in
`display_power_control.py`) ist Teil des Supervisors und muss hier nicht mehr
separat gestartet werden.

Siehe [`docs/kiosk-labwc.md`](kiosk-labwc.md) fuer die vollstaendige autostart-Konfiguration.

## 6. Fingerabdruck-GUI einrichten

```bash
cd ~/kuechendisplay/fingerprint-admin
cp sensor_config.json.example sensor_config.json
cp sudoers_kuechendisplay_fingerprint.txt.example sudoers_kuechendisplay_fingerprint.txt
# <DEIN_BENUTZERNAME> in der sudoers-Datei ersetzen, dann:
sudo visudo -cf sudoers_kuechendisplay_fingerprint.txt
sudo cp sudoers_kuechendisplay_fingerprint.txt /etc/sudoers.d/kuechendisplay-fingerprint
sudo chmod 440 /etc/sudoers.d/kuechendisplay-fingerprint

python3 -m venv ~/kuechendisplay-venv
source ~/kuechendisplay-venv/bin/activate
pip install pyserial adafruit-circuitpython-fingerprint
```

Start der GUI: `bash start_fingerprint_gui.sh`. Das Skript stoppt den
Supervisor, schaltet per `pinctrl` die Sensorversorgung (GPIO27) fuer die
Dauer der GUI-Nutzung ein und startet den Supervisor danach wieder (siehe
[`docs/hardware.md`](hardware.md)).

## 7. Namenszuordnung eintragen

Die Namenszuordnung liegt ausserhalb des Repositories und wird von
Supervisor und GUI gemeinsam genutzt:

```bash
cp ~/kuechendisplay/example-config/fingerprint_mapping.py.example ~/.kuechendisplay/fingerprint_mapping.py
chmod 600 ~/.kuechendisplay/fingerprint_mapping.py
nano ~/.kuechendisplay/fingerprint_mapping.py   # Platzhalter person_a-person_d durch echte Namen ersetzen
```

Passend dazu in `supervisor/config.py` (`INDIVIDUAL_USER_CREDENTIALS` wird
aus `secrets.json` abgeleitet) die Schluessel in `secrets.json`
(`individual_accounts`) anlegen. Die Bezeichner muessen mit den Schluesseln in
`fingerprint_mapping.py` uebereinstimmen, siehe `example-config/README.md`.

## 8. Funktionstest

```bash
# Monitor ueber das Relais aus- und wieder einschalten
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/display/power' -m off
sleep 5
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/display/power' -m on

# Fingerabdruck: Sensor beruehren, Log ansehen
journalctl -u kuechendisplay-supervisor -f
```

Bei Problemen siehe [`docs/troubleshooting.md`](troubleshooting.md).

## Updates

Updates auf dem Pi: `git pull` in `~/kuechendisplay/` und anschliessend
`sudo systemctl restart kuechendisplay-supervisor`.
