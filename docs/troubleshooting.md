# Troubleshooting

## Supervisor stuerzt beim Boot sofort ab (CDP-Verbindung)

Chromium ist beim Systemstart u. U. noch nicht bereit, wenn der Supervisor bereits startet. Der `KioskController` wartet deshalb bis zu 60 s auf den CDP-Port (`CDP_WAIT_TIMEOUT_SECONDS`). Tritt der Fehler trotzdem auf, `CDP_WAIT_TIMEOUT_SECONDS` in `supervisor/config.py` erhoehen.

## display_power_control.py / notification_overlay.py stuerzen beim Boot ab

Ursache: DNS/Netzwerk ist beim Boot oft noch nicht bereit, wenn labwc die Autostart-Datei ausfuehrt (`mqtt` nicht aufloesbar -> `socket.gaierror`). Beide Skripte enthalten bereits `connect_with_retry()`, das die Verbindung wiederholt statt einmalig versucht. Falls der Fehler weiterhin auftritt, `MQTT_CONNECT_RETRY_DELAY_SECONDS` pruefen bzw. erhoehen.

## Nutzerwechsel wirkt sich nicht auf status/state aus (Wall-Mode-Bug)

Frueher aenderte `wall_mode.set()` nur den Browser-Zustand, ohne den `state_store` zu aktualisieren. Fix: `on_wall_mode_change`-Callback an `YuvomiUserManager` uebergeben, der den `state_store` explizit mitzieht (siehe `kuechendisplay_supervisor.py`, Konstruktor).

## Cookies bleiben nach Logout/Neustart haengen

`YuvomiSessionManager.logout()` ruft zusaetzlich `kiosk.clear_browser_cookies()` auf, um Cookie-Reste zwischen Nutzerwechseln zu verhindern. Falls trotzdem alte Sitzungen sichtbar bleiben, pruefen ob `clear_browser_cookies()` tatsaechlich aufgerufen wird (Log-Zeile "Alle Browser-Cookies geloescht").

## Fingerabdruck-Sensor nicht erreichbar (`/dev/serial0` belegt)

`/dev/serial0` kann nur von einem Prozess gleichzeitig geoeffnet werden. Wenn sowohl der Supervisor (`hardware_fingerprint.py`) als auch die Fingerabdruck-GUI gleichzeitig zugreifen wollen, schlaegt eine der beiden Verbindungen fehl. Die GUI stoppt daher automatisch `kuechendisplay-supervisor.service` waehrend sie laeuft (siehe `supervisor_control.py` / `start_fingerprint_gui.sh`) und startet ihn beim Beenden zuverlaessig wieder.

## Sensor-Passwort falsch / Verbindung schlaegt fehl

Pruefen, ob das Passwort in `fingerprint-admin/sensor_config.json` mit dem tatsaechlich auf dem Sensor gesetzten Passwort uebereinstimmt. Bei einem Sensorwechsel ohne Passwortaenderung reicht es, `sensor_config.json` anzupassen.

## wlopm findet den Display-Output nicht

`WLOPM_OUTPUT_NAME` in `supervisor/config.py` und `display_power_control.py` (aktuell `HDMI-A-1`) muss zum tatsaechlichen Output passen. Pruefen mit `wlopm` (ohne Argumente) direkt auf dem Pi.
