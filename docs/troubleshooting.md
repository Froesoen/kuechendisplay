# Troubleshooting

## Supervisor stuerzt beim Boot sofort ab (CDP-Verbindung)

Chromium ist beim Systemstart u. U. noch nicht bereit, wenn der Supervisor bereits startet. Der `KioskController` wartet deshalb bis zu 60 s auf den CDP-Port (`CDP_WAIT_TIMEOUT_SECONDS`). Tritt der Fehler trotzdem auf, `CDP_WAIT_TIMEOUT_SECONDS` in `supervisor/config.py` erhoehen.

## notification_overlay.py stuerzt beim Boot ab

Ursache: DNS/Netzwerk ist beim Boot oft noch nicht bereit, wenn labwc die Autostart-Datei ausfuehrt (`mqtt` nicht aufloesbar -> `socket.gaierror`). Das Skript nutzt `connect_with_retry()`, das die Verbindung wiederholt statt einmalig versucht. Falls der Fehler weiterhin auftritt, `MQTT_CONNECT_RETRY_DELAY_SECONDS` pruefen bzw. erhoehen.

## Nutzerwechsel wirkt sich nicht auf status/state aus (Wall-Mode-Bug)

Frueher aenderte `wall_mode.set()` nur den Browser-Zustand, ohne den `state_store` zu aktualisieren. Fix: `on_wall_mode_change`-Callback an `YuvomiUserManager` uebergeben, der den `state_store` explizit mitzieht (siehe `kuechendisplay_supervisor.py`, Konstruktor).

## Cookies bleiben nach Logout/Neustart haengen

`YuvomiSessionManager.logout()` ruft zusaetzlich `kiosk.clear_browser_cookies()` auf, um Cookie-Reste zwischen Nutzerwechseln zu verhindern. Falls trotzdem alte Sitzungen sichtbar bleiben, pruefen ob `clear_browser_cookies()` tatsaechlich aufgerufen wird (Log-Zeile "Alle Browser-Cookies geloescht").

## Fingerabdruck: "Failed to read data from sensor"

Der Supervisor meldet `RuntimeError: Failed to read data from sensor` (Aufruf in `adafruit_fingerprint.verify_password`), im Overlay erscheint "Fingerabdrucksensor: keine Antwort - Verkabelung pruefen". Der Sensor liefert dann keine (oder keine vollstaendige) Antwort. Ursachen in dieser Reihenfolge pruefen:

1. **Datenleitungen vertauscht:** Sensor-TXD muss an Pin 10 (GPIO15), Sensor-RXD an Pin 8 (GPIO14). Die Adernfarben koennen je nach Kabel abweichen; massgeblich ist die Funktion (siehe `docs/gpio-pinbelegung.md`).
2. **Versorgung:** Waehrend einer Beruehrung muessen am R503-Pin 1 gegen Pin 2 kurz ca. 3,3 V anliegen (BC327 leitet), und Pin 6 (Touch-Power) dauerhaft 3,3 V.
3. **UART:** `ls -l /dev/serial0` und `raspi-config` (serielle Hardware-Schnittstelle an, Login-Shell aus).
4. **Direkter Test ohne Supervisor:**

```bash
sudo systemctl stop kuechendisplay-supervisor
pinctrl set 27 op dl                       # Sensor einschalten (GPIO27 LOW)
python3 - <<'EOF'
import serial, time
u = serial.Serial("/dev/serial0", 57600, timeout=1)
time.sleep(0.5)
u.write(bytes.fromhex("EF01FFFFFFFF01000713000000000 01B".replace(" ", "")))
print(u.read(32).hex())
EOF
pinctrl set 27 op dh                       # Sensor ausschalten
sleep 3 && sudo systemctl start kuechendisplay-supervisor
```

Eine Antwort, die mit `ef01ffffffff07` beginnt, zeigt, dass die UART-Strecke funktioniert (bei geaendertem Passwort kommt ein Fehlercode zurueck). Bleibt die Ausgabe leer, liegt der Fehler an Verkabelung oder Versorgung.

## Fingerabdruck-Sensor nicht erreichbar (`/dev/serial0` belegt)

`/dev/serial0` kann nur von einem Prozess gleichzeitig geoeffnet werden. Wenn sowohl der Supervisor (`hardware_fingerprint.py`) als auch die Fingerabdruck-GUI gleichzeitig zugreifen wollen, schlaegt eine der beiden Verbindungen fehl. Die GUI stoppt daher automatisch `kuechendisplay-supervisor.service` waehrend sie laeuft (siehe `supervisor_control.py` / `start_fingerprint_gui.sh`) und startet ihn beim Beenden zuverlaessig wieder.

## Fingerabdruck-GUI verbindet nicht, obwohl der Supervisor gestoppt ist

Der R503 wird ueber den BC327 (GPIO27) nur bei Beruehrung vom Supervisor versorgt. `start_fingerprint_gui.sh` schaltet die Versorgung per `pinctrl` waehrend der GUI-Nutzung dauerhaft ein. Wird die GUI direkt mit `python3 main.py` gestartet, bleibt der Sensor stromlos. Immer ueber `bash start_fingerprint_gui.sh` starten. Falls `pinctrl` fehlt oder keine Rechte hat, erscheint eine Warnung im Terminal; mit `SENSOR_POWER_GPIO=none` laesst sich die Steuerung abschalten (nur sinnvoll bei dauerhaft versorgtem Sensor).

## Sensor-Passwort falsch / Verbindung schlaegt fehl

Pruefen, ob das Passwort in `fingerprint-admin/sensor_config.json` mit dem tatsaechlich auf dem Sensor gesetzten Passwort uebereinstimmt. Bei einem Sensorwechsel ohne Passwortaenderung reicht es, `sensor_config.json` anzupassen. Der Supervisor selbst nutzt das Standardpasswort der Bibliothek; ein im Sensor geaendertes Passwort fuehrt dort zu Fehlern.

## Monitor hat nach dem Wiedereinschalten kein Signal

Das Abschalten des Monitorstroms wirkt wie ein gezogenes HDMI-Kabel (Hotplug). Mit sauberer Verkabelung wird das Bild nach dem Einschalten im Referenz-Setup wieder erkannt. Tritt es dennoch auf (oder meldet sich der Nutzer im Betriebssystem ab):

1. Kontakte pruefen (Wackelkontakte in der Stromzufuehrung haben im Referenz-Setup dieselben Symptome verursacht).
2. Logs nach einem Fehlversuch: `journalctl -b --no-pager | grep -iE "labwc|wlroots|segfault|session|drm|hdmi" | tail -80`.
3. Ausgang per SSH aufwecken: `WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 wlr-randr --output HDMI-A-1 --on`. Kommt das Bild zurueck, ist es ein Hotplug-Problem.
4. labwc-Version pruefen (`labwc --version`, `apt list --upgradable | grep labwc`): In labwc 0.20.1 blieb ein Display nach kurzem HDMI-Hotplug teils schwarz, gemeldet in raspberrypi/trixie-feedback#105 (laut Meldung in 0.20.2 behoben).
5. Hotplug unterdruecken: in `/boot/firmware/cmdline.txt` (eine Zeile) `video=HDMI-A-1:<Breite>x<Hoehe>@60D` ergaenzen (`D` erzwingt den digitalen Ausgang). Vorher Sicherungskopie anlegen.

Der Ausgangsname `HDMI-A-1` laesst sich mit `wlr-randr` pruefen.

## Touch des Monitors faellt aus

Die Touchdaten laufen ueber D+/D- zum Pi (siehe `docs/hardware.md`, Monitorkabel). Pruefen:

```bash
lsusb
sudo dmesg | tail -30
libinput list-devices | grep -i -A3 touch
```

- Geraet fehlt in `lsusb`: Verkabelung/Enumeration pruefen (Datenleitungen verdrillt und kurz, gemeinsame Masse, CC1/CC2 je 10 kOhm nach VBUS, kein zweites VBUS vom Pi).
- Geraet vorhanden, aber keine Reaktion: in `~/.config/labwc/rc.xml` das Touchgeraet dem Ausgang zuordnen (`<touch deviceName="..." mapToOutput="HDMI-A-1" />`; Namen aus `libinput list-devices`). Beim Bearbeiten die Hinweise aus `docs/kiosk-labwc.md` beachten.
