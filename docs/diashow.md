# Diashow-Modul

Zeigt Bilder von einem NAS-Ordner in zufaelliger Reihenfolge im Kiosk-Browser
an. Geschwindigkeit, ein manueller Rescan und das Vor-/Zurueckblaettern sind
per MQTT steuerbar; am Touchscreen blaettert man durch Tippen auf die linke
bzw. rechte Bildschirmseite. Bilder werden vor der Anzeige bei Bedarf
automatisch auf max. 1920x1080 verkleinert; die Originaldatei im NAS-Ordner
wird dabei ueberschrieben (im Ordner liegen laut Vorgabe nur Kopien, ein
Ueberschreiben ist unkritisch).

Status: **produktiv im Einsatz** auf dem Kuechendisplay, inklusive
Supervisor-Integration (Button 2) und verifiziertem Reboot-Verhalten.

## Architektur

- **NAS-Mount**: SMB-Freigabe `08_kuechendisplay` wird per `systemd.automount`
  unter `/mnt/diashow` eingehaengt. Zugangsdaten liegen unter
  `~/.kuechendisplay/diashow_nas_credentials` (zentrale Ablage aller lokalen
  Geheimnisse des Projekts, analog zu `secrets.json`).
- **`slideshow/slideshow_service.py`**: durchsucht den Mount rekursiv, mischt
  die Playlist, prueft/verkleinert Bilder vor der Anzeige, kopiert das
  aktuelle Bild nach `slideshow/www/img/current.jpg` und meldet Status per
  MQTT sowie in `slideshow/www/img/status.json`. Der Dienst merkt sich die
  Position in der Playlist und kann vor- und zurueckblaettern.
- **Navigations-API**: kleiner HTTP-Endpunkt im Diashow-Dienst auf
  `127.0.0.1:8091` (`POST /api/next`, `POST /api/prev`), den das Frontend bei
  einem Tipp aufruft.
- **`slideshow/www/index.html`**: einfache HTML/JS-Seite, die `status.json`
  alle 500 ms abfragt, `current.jpg` bei geaendertem Bildzaehler `seq` laedt
  und im Kiosk-Browser fullscreen anzeigt. Sie erkennt Tipps auf die linke
  bzw. rechte Seite (Pointer Events) und ruft die Navigations-API auf. Mit
  `?debug=1` blendet sie einen Diagnose-Bereich ein.
- **Webserver**: liefert `slideshow/www` mit `python3 -m http.server` auf
  Port 8090 fuer den Kiosk-Browser direkt aus dem Checkout aus
  (`WorkingDirectory` der Unit `kuechendisplay-diashow-web.service`).
- **Supervisor-Integration**: `supervisor/config.py` definiert
  `DIASHOW_URL = "http://127.0.0.1:8090/"`. `_set_display_mode("slideshow")`
  im Supervisor meldet zuerst einen angemeldeten individuellen Yuvomi-Nutzer
  sofort ab und navigiert dann den bestehenden Kiosk-Tab per CDP zu dieser
  URL. Button 2 (kurz) ist im `button_mapper.py` standardmaessig auf
  `cmd/mode=slideshow` gemappt; zusaetzlich schaltet der Inaktivitaets-Watchdog
  nach der konfigurierten Zeit automatisch dorthin (Standard 10 Minuten =
  `SLIDESHOW_INACTIVITY_TIMEOUT_SECONDS`, per MQTT `cmd/slideshow/timeout`
  aenderbar, `0` = aus; siehe [`automatik.md`](automatik.md)).

## Einrichtung

Diese Anleitung gilt fuer den Benutzer `christoph` und den Checkout unter
`/home/christoph/kuechendisplay` (entspricht `~/kuechendisplay`).

### 1. Code aktualisieren

```bash
cd ~/kuechendisplay
git fetch origin
git switch main
git pull --ff-only origin main
```

### 2. NAS-Zugangsdaten unter ~/.kuechendisplay anlegen

Alle lokalen Geheimnisse des Projekts liegen zentral unter `~/.kuechendisplay`.
Die SMB-Zugangsdaten fuer die Diashow folgen demselben Muster:

```bash
mkdir -p ~/.kuechendisplay
chmod 700 ~/.kuechendisplay

cat > ~/.kuechendisplay/diashow_nas_credentials <<'EOF'
username=kuechendisplay
password=kuechendisplay
EOF

chmod 600 ~/.kuechendisplay/diashow_nas_credentials
```

### 3. NAS-Mount einrichten

```bash
sudo apt update
sudo apt install -y cifs-utils smbclient dos2unix

sudo mkdir -p /mnt/diashow

# Manueller Test
sudo mount -v -t cifs //192.168.178.3/08_kuechendisplay /mnt/diashow \
  -o credentials=/home/christoph/.kuechendisplay/diashow_nas_credentials,vers=2.0,uid=$(id -u christoph),gid=$(id -g christoph),noperm

findmnt /mnt/diashow
ls -la /mnt/diashow

sudo umount /mnt/diashow
```

Wenn der Test funktioniert, dauerhaften Automount einrichten:

```bash
sudo cp /etc/fstab /etc/fstab.bak.$(date +%F-%H%M%S)

printf '%s\n' '//192.168.178.3/08_kuechendisplay /mnt/diashow cifs credentials=/home/christoph/.kuechendisplay/diashow_nas_credentials,vers=2.0,uid=1000,gid=1000,noperm,x-systemd.automount,noauto,_netdev,nofail 0 0' | sudo tee -a /etc/fstab

sudo systemctl daemon-reload
sudo systemctl restart remote-fs.target

ls -la /mnt/diashow
findmnt /mnt/diashow
```

Die UID/GID (hier `1000`) mit `id -u christoph` und `id -g christoph` pruefen
und bei Abweichung anpassen.

Bilder duerfen direkt im Ordner `08_kuechendisplay` oder in beliebig tiefen
Unterordnern liegen; der Scan durchsucht rekursiv (`Path.rglob`).

### 4. Python-Abhaengigkeiten

```bash
sudo apt install -y python3-pil python3-paho-mqtt mosquitto-clients
```

### 5. Lokale Diashow-Konfiguration

Der MQTT-Broker (`mqtt`, Port 1883) ist im lokalen Netz ohne Authentifizierung
erreichbar - dieselbe Konfiguration wie im bestehenden Supervisor
(`supervisor/config.py`, `MQTT_BROKER_HOST`/`MQTT_BROKER_PORT`). Die Diashow
benoetigt daher **keine** MQTT-Zugangsdaten.

```bash
cd ~/kuechendisplay
mkdir -p slideshow/www/img

cat > slideshow/config.json <<'EOF'
{
  "image_root": "/mnt/diashow",
  "output_dir": "/home/christoph/kuechendisplay/slideshow/www/img",
  "target_width": 1920,
  "target_height": 1080,
  "jpeg_quality": 85,
  "default_interval": 10,
  "mqtt": {
    "host": "mqtt",
    "port": 1883,
    "client_id": "kuechendisplay-diashow",
    "topic_prefix": "display/kueche/diashow"
  }
}
EOF

chmod 600 slideshow/config.json
```

Optional lassen sich die Adresse und der Port der Navigations-API mit den
Schluesseln `api_host` (Standard `127.0.0.1`) und `api_port` (Standard `8091`)
auf oberster Ebene der `config.json` aendern. Das Frontend ruft den Port
`8091` auf; bei einem anderen Port muss die Konstante `API` in
`slideshow/www/index.html` angepasst werden.

`default_interval` gilt nur, solange noch kein Intervall per MQTT gesetzt
wurde. Danach liegt der zuletzt eingestellte Wert in
`~/.kuechendisplay/diashow_state.json` und hat beim Start Vorrang (siehe
"Intervall bleibt erhalten"). Der Speicherort laesst sich optional mit dem
Schluessel `state_file` in der `config.json` aendern.

Der Topic-Praefix `display/kueche/diashow` ist bewusst an den bestehenden
Supervisor-Namensraum (`display/kueche/`) angeglichen, damit kein zweiter,
davon abweichender MQTT-Namensraum entsteht.

`slideshow/config.json` enthaelt keine Geheimnisse mehr, wird aber trotzdem
nicht committed (lokale Pfade/Broker-Adresse):

```bash
printf '\n# Lokale Diashow-Konfiguration\nslideshow/config.json\n' >> .git/info/exclude
```

### 6. Manueller Testlauf (vor systemd)

```bash
cd ~/kuechendisplay
DIASHOW_CONFIG="$HOME/kuechendisplay/slideshow/config.json" \
python3 slideshow/slideshow_service.py
```

Erwartete Ausgabe:

```text
MQTT verbunden (reason_code=Success)
Navigations-API laeuft auf http://127.0.0.1:8091
Scan abgeschlossen: N Bilder gefunden
Verkleinert: DATEINAME.jpg (...)
```

In einem zweiten Terminal parallel pruefen:

```bash
ls -lah ~/kuechendisplay/slideshow/www/img/
cat ~/kuechendisplay/slideshow/www/img/status.json
```

Mit `Ctrl+C` beenden, wenn `current.jpg` und `status.json` korrekt entstehen.

### 7. systemd-Dienste einrichten

```bash
cd ~/kuechendisplay

sudo cp slideshow/systemd/kuechendisplay-diashow.service /etc/systemd/system/
sudo cp slideshow/systemd/kuechendisplay-diashow-web.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now kuechendisplay-diashow.service
sudo systemctl enable --now kuechendisplay-diashow-web.service
```

Pruefen:

```bash
systemctl status kuechendisplay-diashow.service --no-pager
systemctl status kuechendisplay-diashow-web.service --no-pager
curl -I http://localhost:8090/
curl -I http://localhost:8090/img/current.jpg
```

### 8. Supervisor-Integration (Button 2)

Keine zusaetzliche Konfiguration noetig - `DIASHOW_URL` ist in
`supervisor/config.py` fest eingetragen und Button 2 ist im
`button_mapper.py` bereits standardmaessig auf `cmd/mode=slideshow`
gemappt. Nach einem `git pull` reicht ein Neustart des Supervisor-Dienstes:

```bash
sudo systemctl restart kuechendisplay-supervisor.service
sudo systemctl status kuechendisplay-supervisor.service --no-pager
```

Button 2 kurz druecken und im Log pruefen:

```bash
sudo journalctl -u kuechendisplay-supervisor.service -n 10 --no-pager
```

Erwartet:

```text
MQTT empfangen: display/kueche/cmd/mode = slideshow
Wechsle zu Diashow: http://127.0.0.1:8090/
supervisor.kiosk: Navigiere zu http://127.0.0.1:8090/
```

War ein individueller Yuvomi-Nutzer angemeldet, steht davor zusaetzlich
`Direkter Logout von '...' (Diashow)`.

Rueckkehr zur App-Ansicht (z. B. Yuvomi) manuell testen:

```bash
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/mode' -m app
```

Der automatische Inaktivitaets-Watchdog schaltet zusaetzlich nach 10 Minuten
ohne Aktivitaet (Standard) selbststaendig auf die Diashow um. Die Zeit laesst
sich per MQTT aendern, `0` schaltet den automatischen Wechsel aus:

```bash
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/slideshow/timeout' -m 900
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/slideshow/timeout' -m 0
```

Details zu Aktivitaetsquellen und Zusammenspiel mit dem Auto-Logout stehen in
[`automatik.md`](automatik.md).

## Blaettern per Tippen und MQTT

In der Diashow lassen sich Bilder manuell vor- und zurueckblaettern:

| Bedienung | Wirkung |
|---|---|
| Tippen auf die **linken 30 %** des Bildschirms | vorheriges Bild |
| Tippen auf die **rechten 30 %** des Bildschirms | naechstes Bild |
| Tippen in der Mitte (40 %) | keine Funktion |
| MQTT `display/kueche/diashow/set/naechstes` | naechstes Bild |
| MQTT `display/kueche/diashow/set/vorheriges` | vorheriges Bild |
| `POST http://127.0.0.1:8091/api/next` bzw. `/api/prev` | naechstes bzw. vorheriges Bild |
| Pfeiltasten (nur zum Testen am PC) | naechstes bzw. vorheriges Bild |

Verhalten:

- Ein Tipp ist eine kurze Beruehrung: Bewegung unter 40 Pixeln und Dauer unter
  800 ms. Laengere oder wandernde Beruehrungen zaehlen nicht. Beim Tipp
  leuchtet die jeweilige Seite kurz auf.
- Wischgesten werden nicht ausgewertet. Im Referenz-Setup faengt der
  Kiosk-Browser bzw. der Compositor sie ab: Die Seite bekommt sie nicht oder
  es wechselt der Tab. Deshalb wird getippt statt gewischt.
- Das Blaettern laeuft umlaufend. Nach dem letzten Bild beginnt die Liste
  wieder von vorn bzw. beim Zurueckblaettern am Anfang beim letzten Bild.
- Nach jedem manuellen Wechsel beginnt das Intervall neu: das Bild bleibt
  wieder die volle Anzeigedauer stehen, bevor die Diashow automatisch
  weiterschaltet.
- Mehrere schnelle Tipps werden zusammengefasst; angezeigt wird das Endbild.
  Heben sich Vor und Zurueck dabei auf, wird das aktuelle Bild erneut
  angezeigt und nicht automatisch weitergeschaltet. Zwischen Tipp und neuem
  Bild liegen etwa 0,5 bis 1 Sekunde.
- Das Tippen beendet die Diashow nicht; der Anzeigemodus bleibt `slideshow`.
  Ein Touch setzt wie sonst den Timer fuer den automatischen Wechsel zurueck
  (siehe [`automatik.md`](automatik.md)).
- Bei aktiver Kindersicherung blockiert das Overlay den Touch; dann ist auch
  das Tippen gesperrt. Die MQTT-Topics funktionieren weiterhin.
- Ist die Diashow per `set/aktiv` pausiert, zeigt ein manueller Wechsel
  trotzdem das naechste bzw. vorherige Bild; danach bleibt sie pausiert.

Test:

```bash
curl -X POST http://127.0.0.1:8091/api/next
curl -X POST http://127.0.0.1:8091/api/prev
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/diashow/set/naechstes' -m 1
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/diashow/set/vorheriges' -m 1
```

Im Journal erscheint pro Wechsel `Manuelle Navigation: +1` bzw. `-1`.

## Diagnose-Modus (?debug=1)

Mit dem Parameter `?debug=1` blendet die Seite unten links einen
Diagnose-Bereich ein. Die erste Zeile zeigt die aktuelle Position (`Bild 17 /
252 dateiname.jpg`), darunter stehen die letzten acht Ereignisse mit Uhrzeit
(`pointerdown`, `pointerup`, `pointercancel`, `touchstart`, `touchend`,
`click`, `senden prev|next` sowie Fehler beim Senden).

Am Kiosk oeffnen und wieder verlassen:

```bash
# Diagnose-Seite anzeigen
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/app' -m 'custom:http://127.0.0.1:8090/?debug=1'

# Zurueck zur normalen Diashow bzw. zu Yuvomi
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/mode' -m slideshow
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/app' -m yuvomi
```

`cmd/app` mit `custom:` meldet einen angemeldeten individuellen Nutzer sofort
ab (siehe [`automatik.md`](automatik.md)).

## MQTT-Schnittstelle (Diashow-Modul)

| Topic | Richtung | Payload | Zweck |
|---|---|---|---|
| `display/kueche/diashow/set/intervall` | Eingang | Sekunden, z. B. `15` | Anzeigedauer pro Bild aendern (min. 2s); wird dauerhaft gespeichert |
| `display/kueche/diashow/set/rescan` | Eingang | beliebig, z. B. `1` | Loest einen Neu-Scan des NAS-Ordners aus |
| `display/kueche/diashow/set/aktiv` | Eingang | `ON` / `OFF` | Diashow pausieren/fortsetzen |
| `display/kueche/diashow/set/naechstes` | Eingang | beliebig, z. B. `1` | Zum naechsten Bild blaettern |
| `display/kueche/diashow/set/vorheriges` | Eingang | beliebig, z. B. `1` | Zum vorherigen Bild blaettern |
| `display/kueche/diashow/status` (retain) | Ausgang | JSON `{"intervall":..., "anzahl_bilder":..., "letzter_scan":..., "aktiv":..., "seq":..., "index":..., "datei":...}` | Aktueller Zustand fuer Dashboards/Node-RED. `seq` ist ein Bildzaehler, der bei jedem neuen Bild um 1 steigt (Startwert: Unix-Zeit beim Dienststart). `index` ist die 1-basierte Position des angezeigten Bildes in der aktuellen Reihenfolge (`0` = noch kein Bild, z. B. direkt nach einem Scan), `datei` sein Dateiname. |

Zur Abgrenzung: Das Umschalten der **Anzeige** (Button 2, Watchdog) laeuft
ueber den bestehenden Supervisor-Namensraum `display/kueche/cmd/mode`, nicht
ueber die obigen Diashow-Topics; die Zeit bis zum automatischen Wechsel
stellt `display/kueche/cmd/slideshow/timeout` ein. Die Diashow-Topics steuern
ausschliesslich Inhalt/Tempo der Diashow selbst, unabhaengig davon, ob sie
gerade sichtbar ist. Vom Broker wiederholte retained Nachrichten auf den
`set/...`-Topics werden ignoriert.

Die Reihenfolge der Bilder ist zwischen zwei Scans fest. Neu gemischt wird
beim Start des Dienstes, nach einem Rescan und wenn die Liste einmal
durchgelaufen ist; danach beginnt `index` wieder bei 1.

### Intervall bleibt erhalten

Jedes per `set/intervall` gesetzte Intervall (z. B. vom Slider im
Node-RED-Dashboard) speichert der Dienst in
`~/.kuechendisplay/diashow_state.json`, z. B. `{"intervall": 31.0}`. Beim
Start des Dienstes hat dieser Wert Vorrang vor `default_interval` aus der
`config.json`. Dadurch bleibt das Intervall nach einem Neustart des Dienstes
oder des Pi erhalten.

- Ist die Datei nicht vorhanden, defekt oder enthaelt sie einen ungueltigen
  Wert (unter 2 s oder keine endliche Zahl), gilt `default_interval`; bei
  einem ungueltigen Inhalt steht eine Meldung im Journal.
- Der Zustand "pausiert" (`set/aktiv`) wird bewusst **nicht** gespeichert.
  Nach jedem Start laeuft die Diashow und wechselt automatisch.
- Nicht endliche Werte (`inf`, `nan`) lehnt der Dienst ab und schreibt eine
  Warnung ins Journal.
- Zurueck zum Wert aus der `config.json`: Datei loeschen und den Dienst neu
  starten.

```bash
cat ~/.kuechendisplay/diashow_state.json
rm ~/.kuechendisplay/diashow_state.json
sudo systemctl restart kuechendisplay-diashow.service
```

Beispiele:

```bash
# Manueller Rescan
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/diashow/set/rescan' -m 1

# Intervall auf 15s setzen
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/diashow/set/intervall' -m 15

# Naechstes bzw. vorheriges Bild
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/diashow/set/naechstes' -m 1
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/diashow/set/vorheriges' -m 1

# Status lesen
mosquitto_sub -h mqtt -p 1883 -t 'display/kueche/diashow/status' -C 1 -W 3 -v
```

Ein Rescan wird beim naechsten Bildwechsel verarbeitet, damit das aktuell
sichtbare Bild nicht abrupt unterbrochen wird.

## Verhalten der Groessenreduktion

- Vor jeder Anzeige wird die Bildgroesse per Pillow geprueft; EXIF-Rotation
  wird zuerst korrigiert (`ImageOps.exif_transpose`).
- Passt das Bild bereits in 1920x1080, passiert nichts.
- Andernfalls wird proportional verkleinert (kein Zuschneiden, kein
  Hochskalieren). Die temporaere Datei erhaelt bewusst ein echtes
  Bild-Suffix (`DATEINAME.resize-tmp.jpg/png/webp`), damit Pillow das
  Zielformat sicher erkennt, und wird per `os.replace()` atomar in die
  Originaldatei zurueckgeschrieben.
- `current.jpg` ist unabhaengig vom Quellformat immer ein JPEG, damit auch
  PNG/WebP-Quellen im Browser-Frontend zuverlaessig angezeigt werden.
- Schnellweg: Ist die Quelldatei bereits ein JPEG (RGB oder Graustufen), passt
  in 1920x1080 und hat keine EXIF-Drehung, wird sie unveraendert nach
  `current.jpg` kopiert statt neu kodiert. Das verkuerzt die Wartezeit nach
  einem Tipp. Alle anderen Faelle werden wie zuvor neu kodiert.
- Die Verkleinerung der Originale geschieht lazy bei der ersten Anzeige des
  jeweiligen Bildes, nicht vorab fuer alle Bilder.

## Bekanntes Verhalten / Troubleshooting

- **`unknown file extension: .tmp` beim Verkleinern**: bereits behoben -
  temporaere Dateien verwenden jetzt ein echtes Bildsuffix statt `.tmp`.
- **`DeprecationWarning: Callback API version 1 is deprecated`**: behoben -
  der MQTT-Client verwendet `mqtt.CallbackAPIVersion.VERSION2`.
- **`Yuvomi-Logout mit Status 401 (evtl. bereits abgemeldet)` beim Booten
  des Supervisors**: unveraendertes, bestehendes Verhalten (nicht durch die
  Diashow verursacht) - harmlos, der anschliessende Login greift zuverlaessig.
- **Diashow zeigt nach Reboot ein altes Bild**: pruefen, ob
  `kuechendisplay-diashow.service` tatsaechlich laeuft und der NAS-Mount
  aktiv ist (`findmnt /mnt/diashow`); der Dienst scannt beim Start neu.
- **Diashow startet nicht automatisch**: `display/kueche/status/slideshow/timeout`
  pruefen (`0` = aus) und ob Taster, Touch oder MQTT-Kommandos den Timer
  laufend zuruecksetzen (siehe [`automatik.md`](automatik.md)).
- **Intervall springt nach einem Neustart auf den Standard (10 s)**: Im
  Journal des Diashow-Dienstes muss beim Start
  `Gespeichertes Intervall geladen: ...` stehen
  (`sudo journalctl -u kuechendisplay-diashow.service -b --no-pager | grep -i intervall`).
  Fehlt die Zeile, existiert `~/.kuechendisplay/diashow_state.json` nicht
  oder ist ungueltig (dann steht eine Warnung im Journal). Pruefen, ob die
  Datei dem Benutzer des Dienstes (`christoph`) gehoert und beschreibbar ist
  (`ls -l ~/.kuechendisplay/`); Schreibfehler stehen als
  `Intervall konnte nicht gespeichert werden` im Journal. Ein Intervall
  unter 2 s oder `inf`/`nan` wird nicht uebernommen.
- **Tippen reagiert nicht**: Im Journal des Diashow-Dienstes muss
  `Navigations-API laeuft auf http://127.0.0.1:8091` stehen
  (`sudo journalctl -u kuechendisplay-diashow.service -n 30 --no-pager`).
  Steht dort `API-Port ... nicht verfuegbar`, belegt ein anderer Prozess den
  Port (`ss -ltnp | grep 8091`); dann `api_port` in `config.json` und `API` in
  `index.html` anpassen. Mit `curl -X POST http://127.0.0.1:8091/api/next`
  laesst sich die API ohne Touch pruefen. Bei aktiver Kindersicherung ist der
  Touch gesperrt. Ob Beruehrungen die Seite erreichen, zeigt der
  Diagnose-Modus (`?debug=1`).
- **Nach einem Update zeigt die Diashow noch das alte Verhalten**: Der
  Webserver liefert die Dateien direkt aus dem Checkout; nach einem
  `git pull` ist weder ein Neustart des Pi noch des Webservers noetig, nur der
  Diashow-Dienst muss neu starten
  (`sudo systemctl restart kuechendisplay-diashow.service`). Der Kiosk-Browser
  kann die alte `index.html` aber aus seinem Cache laden. Einmal die Diashow
  oeffnen und die Seite ohne Cache neu laden:

  ```bash
  mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/mode' -m slideshow
  sleep 3
  ~/kuechendisplay-venv/bin/python - <<'EOF'
  import pychrome
  b = pychrome.Browser(url="http://127.0.0.1:9222")
  t = [x for x in b.list_tab() if x._kwargs.get("type") == "page"][0]
  t.start()
  t.Page.reload(ignoreCache=True)
  t.stop()
  EOF
  ```

## Reboot-Test (verifiziertes Verfahren)

1. Alle Dienste auf Autostart pruefen:
   ```bash
   systemctl is-enabled kuechendisplay-supervisor.service kuechendisplay-diashow.service kuechendisplay-diashow-web.service
   ```
   Erwartet: dreimal `enabled`.
2. Neustart ausloesen:
   ```bash
   sudo reboot
   ```
3. Nach 60-90s erneut per SSH verbinden und pruefen:
   ```bash
   findmnt /mnt/diashow
   systemctl status kuechendisplay-diashow.service --no-pager
   systemctl status kuechendisplay-diashow-web.service --no-pager
   systemctl status kuechendisplay-supervisor.service --no-pager
   ```
   Alle drei Dienste muessen `active (running)` sein, der NAS-Mount aktiv.
4. Frische Bilder pruefen:
   ```bash
   ls -lah ~/kuechendisplay/slideshow/www/img/
   cat ~/kuechendisplay/slideshow/www/img/status.json
   ```
5. Button 2 druecken und im Supervisor-Log die Zeile
   `Wechsle zu Diashow: http://127.0.0.1:8090/` bestaetigen.
6. Mit `mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/mode' -m app`
   zurueck zur App-Ansicht wechseln und im Log die entsprechende
   `status/state`-Aktualisierung bestaetigen.

Dieses Verfahren wurde auf dem produktiven Kuechendisplay erfolgreich
durchlaufen: NAS-Automount, beide Diashow-Dienste und der Supervisor starten
nach einem Reboot ohne manuelles Eingreifen in der richtigen Reihenfolge.
