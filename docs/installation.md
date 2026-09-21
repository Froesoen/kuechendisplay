# Installation auf dem Raspberry Pi

## Voraussetzungen

- Raspberry Pi OS mit labwc-Desktop, UART aktiviert (`raspi-config`)
- Zugriff auf einen MQTT-Broker (Hostname `mqtt` im lokalen Netz)
- Laufendes Yuvomi-Frontend, erreichbar unter der in `supervisor/config.py` hinterlegten `YUVOMI_BASE_URL`
- Verkabelung gemaess [`docs/hardware.md`](hardware.md) und
  [`docs/gpio-pinbelegung.md`](gpio-pinbelegung.md) bereits umgesetzt,
  insbesondere der BC327-Transistor an GPIO27 (Fingerprint-VCC) und das
  MOSFET-Modul an GPIO17 (Monitor-Stromversorgung) - startet der Supervisor
  ohne diese Verkabelung, bleiben Sensor bzw. Monitor dauerhaft stromlos.

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

## 3. Python-Umgebung fuer den Supervisor

Der Supervisor benoetigt Systemzugriff auf GPIO/UART - je nach bisherigem Setup laeuft er mit System-Python oder einer venv mit `--system-site-packages`. Benoetigte Pakete: `paho-mqtt`, `pychrome`, `requests`, `gpiozero`, `pyserial`, `adafruit-circuitpython-fingerprint`.

## 4. systemd-Dienst einrichten

Dienstname: `kuechendisplay-supervisor.service`, startet `python3 ~/kuechendisplay/supervisor/kuechendisplay_supervisor.py`. Der Dateiname ist bewusst gleich geblieben (ohne `_v2`-Suffix), damit bestehende Autostart-/systemd-Verdrahtung unveraendert bleibt. Der Supervisor steuert seit der Kindersicherungs-/MOSFET-Erweiterung auch die Monitor-Stromversorgung (GPIO17) und die Fingerprint-VCC (GPIO27) direkt selbst - dafuer ist kein zusaetzlicher Dienst und kein `wlopm` mehr noetig.

## 5. Zusatzprozess in ~/.config/labwc/autostart

- `notification_overlay.py` (Notification-Overlay, braucht `LD_PRELOAD` fuer `libgtk4-layer-shell.so.0`, siehe Kommentar im Dateikopf)

`display_power_control.py` gibt es nicht mehr - die Display-Power-Steuerung (frueher per `wlopm` in einem separaten Prozess) ist seit der MOSFET-Umstellung direkt Teil von `kuechendisplay_supervisor.py` (Schritt 4) und muss hier nicht mehr separat gestartet werden.

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

Start der GUI: `bash start_fingerprint_gui.sh`

## 7. Namenszuordnung eintragen

In `supervisor/fingerprint_mapping.py` UND `fingerprint-admin/fingerprint_mapping.py` (beide synchron halten!) die Platzhalter `person_a`-`person_d` durch die tatsaechlichen Namen ersetzen. Passend dazu in `supervisor/config.py` (`INDIVIDUAL_USER_CREDENTIALS`) die Schluessel anpassen und in `secrets.json` die zugehoerigen Zugangsdaten hinterlegen.
