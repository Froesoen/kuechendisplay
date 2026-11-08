# Diashow-Modul

Zeigt Bilder von einem NAS-Ordner im Kiosk-Browser an, wahlweise in
zufaelliger oder in sortierter Reihenfolge (nach Ordner und Dateiname).
Geschwindigkeit, Reihenfolge, ein manueller Rescan, Pause/Fortsetzen und das
Vor-/Zurueckblaettern sind per MQTT steuerbar; am Touchscreen blaettert man
durch Tippen auf die linke bzw. rechte Bildschirmseite und haelt die Diashow
durch Tippen in die Mitte an bzw. setzt sie fort. Bilder werden vor der
Anzeige bei Bedarf automatisch auf max. 1920x1080 verkleinert; die
Originaldatei im NAS-Ordner wird dabei ueberschrieben (im Ordner liegen laut
Vorgabe nur Kopien, ein Ueberschreiben ist unkritisch).

Status: **produktiv im Einsatz** auf dem Kuechendisplay, inklusive
Supervisor-Integration (Button 2) und verifiziertem Reboot-Verhalten.

## Architektur

- **NAS-Mount**: SMB-Freigabe `08_kuechendisplay` wird per `systemd.automount`
  unter `/mnt/diashow` eingehaengt. Zugangsdaten liegen unter
  `~/.kuechendisplay/diashow_nas_credentials` (zentrale Ablage aller lokalen
  Geheimnisse des Projekts, analog zu `secrets.json`).
- **`slideshow/slideshow_service.py`**: durchsucht den Mount rekursiv, ordnet
  die Playlist (zufaellig oder sortiert), prueft/verkleinert Bilder vor der
  Anzeige, kopiert das aktuelle Bild nach `slideshow/www/img/current.jpg` und
  meldet Status per MQTT sowie in `slideshow/www/img/status.json`. Der Dienst
  merkt sich die Position in der Playlist, kann vor- und zurueckblaettern und
  bereitet das naechste Bild im Hintergrund als `next.jpg` vor (siehe
  "Vorladen des naechsten Bildes").
- **Navigations-API**: kleiner HTTP-Endpunkt im Diashow-Dienst auf
  `127.0.0.1:8091` (`POST /api/next`, `POST /api/prev`, `POST /api/toggle`),
  den das Frontend bei einem Tipp aufruft.
- **`slideshow/www/index.html`**: einfache HTML/JS-Seite, die `status.json`
  alle 500 ms abfragt, `current.jpg` bei geaendertem Bildzaehler `seq` laedt
  und im Kiosk-Browser fullscreen anzeigt. Sie erkennt Tipps auf die linke
  bzw. rechte Seite (Blaettern) und in die Mitte (Anhalten/Fortsetzen) per
  Pointer Events und ruft die Navigations-API auf. Nach einem Tipp fragt sie
  den Status zusaetzlich nach 150 ms und 450 ms ab, damit Bild und Symbol
  nicht auf den naechsten 500-ms-Takt warten. Bei angehaltener Diashow zeigt
  sie unten links ein kleines Pause-Symbol. Mit `?debug=1` blendet sie einen
  Diagnose-Bereich ein.
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
"Intervall und Reihenfolge bleiben erhalten"). Der Speicherort laesst sich
optional mit dem Schluessel `state_file` in der `config.json` aendern.

Die Reihenfolge der Bilder legt der optionale Schluessel `default_order` fest
(`zufall` oder `reihenfolge`, Standard `zufall`). Auch er gilt nur, solange
noch keine Reihenfolge per MQTT gesetzt wurde (siehe "Reihenfolge: zufaellig
oder sortiert").

Meldungen bei leerer Playlist sendet der Dienst standardmaessig an
`display/kueche/cmd/notify` (Praefix-Basis des `topic_prefix` plus
`/cmd/notify`). Mit dem optionalen Schluessel `notify_topic` auf oberster
Ebene der `config.json` laesst sich dieses Topic aendern (siehe "Warnung bei
leerer Playlist").

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
Scan abgeschlossen: N Bilder gefunden (Reihenfolge: zufall)
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

## Bedienung per Tippen und MQTT

In der Diashow lassen sich Bilder manuell vor- und zurueckblaettern und die
Diashow anhalten bzw. fortsetzen:

| Bedienung | Wirkung |
|---|---|
| Tippen auf die **linken 30 %** des Bildschirms | vorheriges Bild |
| Tippen auf die **rechten 30 %** des Bildschirms | naechstes Bild |
| Tippen in der **Mitte** (40 %) | Diashow anhalten bzw. fortsetzen |
| MQTT `display/kueche/diashow/set/naechstes` | naechstes Bild |
| MQTT `display/kueche/diashow/set/vorheriges` | vorheriges Bild |
| MQTT `display/kueche/diashow/set/aktiv` (`ON` / `OFF`) | Diashow fortsetzen bzw. anhalten |
| `POST http://127.0.0.1:8091/api/next`, `/api/prev` bzw. `/api/toggle` | naechstes Bild, vorheriges Bild bzw. Anhalten/Fortsetzen umschalten |
| Pfeiltasten, Leertaste (nur zum Testen am PC) | naechstes/vorheriges Bild bzw. Anhalten/Fortsetzen |

Verhalten:

- Ein Tipp ist eine kurze Beruehrung: Bewegung unter 40 Pixeln und Dauer unter
  800 ms. Laengere oder wandernde Beruehrungen zaehlen nicht. Beim Tipp auf
  die linke oder rechte Seite leuchtet diese kurz auf.
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
  angezeigt und nicht automatisch weitergeschaltet. Vorwaerts geht es
  schneller als zurueck, weil nur das naechste Bild vorgeladen wird (siehe
  "Vorladen des naechsten Bildes").
- Tippen in die Mitte schaltet um: Laeuft die Diashow, wird sie angehalten;
  ist sie angehalten, wird sie fortgesetzt und zeigt sofort das naechste
  Bild. Zur Rueckmeldung blitzt kurz ein Pause- bzw. Play-Symbol in der
  Bildmitte auf.
- Solange die Diashow angehalten ist, zeigt ein kleines Pause-Symbol in der
  unteren linken Ecke den Zustand an. Es richtet sich nach `aktiv` im Status
  und erscheint daher auch, wenn die Diashow per MQTT (`set/aktiv`) oder im
  Node-RED-Dashboard angehalten wurde.
- Die Pause wird nicht gespeichert und endet nicht von selbst: Nach einem
  Neustart des Dienstes laeuft die Diashow immer; ein automatisches
  Fortsetzen gibt es nicht.
- Ist die Diashow angehalten, zeigt ein manuelles Blaettern trotzdem das
  naechste bzw. vorherige Bild; danach bleibt sie angehalten.
- Das Tippen beendet die Diashow nicht; der Anzeigemodus bleibt `slideshow`.
  Ein Touch setzt wie sonst den Timer fuer den automatischen Wechsel zurueck
  (siehe [`automatik.md`](automatik.md)).
- Bei aktiver Kindersicherung blockiert das Overlay den Touch; dann ist auch
  das Tippen (links, rechts und Mitte) gesperrt. Die MQTT-Topics
  funktionieren weiterhin.

Test:

```bash
curl -X POST http://127.0.0.1:8091/api/next
curl -X POST http://127.0.0.1:8091/api/prev
curl -X POST http://127.0.0.1:8091/api/toggle
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/diashow/set/naechstes' -m 1
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/diashow/set/vorheriges' -m 1
```

Im Journal erscheint pro Wechsel `Manuelle Navigation: +1` bzw. `-1`, beim
Anhalten/Fortsetzen `Diashow aktiv=False` bzw. `True`.

## Reihenfolge: zufaellig oder sortiert

Die Diashow kennt zwei Reihenfolgen:

| Wert | Reihenfolge |
|---|---|
| `zufall` | gemischt (Standard); neu gemischt beim Start des Dienstes, nach einem Rescan und wenn die Liste einmal durchgelaufen ist |
| `reihenfolge` | sortiert nach Ordner, darin nach Dateiname |

Bei `reihenfolge` gilt:

- Die Sortierung ist natuerlich und beachtet die Gross-/Kleinschreibung nicht:
  `IMG_2.jpg` kommt vor `IMG_10.jpg`.
- Sortiert wird zuerst nach dem Ordner (Pfad relativ zum Bilderordner),
  dann nach dem Dateinamen. Die Dateien eines Ordners stehen vor denen seiner
  Unterordner, wie im Dateimanager. Beispiel:

  ```text
  08_kuechendisplay/bild_1.jpg
  08_kuechendisplay/bild_2.jpg
  08_kuechendisplay/Urlaub/IMG_2.jpg
  08_kuechendisplay/Urlaub/IMG_10.jpg
  08_kuechendisplay/Weihnachten/IMG_1.jpg
  ```

- Nach dem letzten Bild wird neu gescannt und wieder mit dem ersten Bild
  begonnen. Auch ein manueller Rescan beginnt am Anfang der Liste.

Umgeschaltet wird per MQTT:

```bash
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/diashow/set/reihenfolge' -m reihenfolge
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/diashow/set/reihenfolge' -m zufall
```

Akzeptiert werden zusaetzlich `sortiert`, `sorted`, `order` und `name` fuer die
sortierte sowie `zufaellig`, `random` und `shuffle` fuer die zufaellige
Reihenfolge (ohne Beachtung der Gross-/Kleinschreibung). Ein anderer Wert wird
ignoriert und als Warnung ins Journal geschrieben.

Beim Umschalten im laufenden Betrieb bleibt das aktuelle Bild Ausgangspunkt:
Bei `reihenfolge` steht die Diashow an dessen Position in der sortierten
Liste, bei `zufall` wird es an den Anfang der neu gemischten Liste gesetzt.
Danach zeigt die Diashow sofort das naechste Bild der neuen Reihenfolge. Ist
sie gerade angehalten, bleibt sie angehalten. Die Reihenfolge steht im Status
(`reihenfolge`) und bleibt nach einem Neustart erhalten (siehe "Intervall und
Reihenfolge bleiben erhalten").

## Vorladen des naechsten Bildes

Nach jeder Anzeige bereitet ein Hintergrund-Thread des Dienstes das folgende
Bild der Playlist vor: Es wird geprueft, bei Bedarf verkleinert und als
`slideshow/www/img/next.jpg` abgelegt. Beim naechsten Wechsel wird diese Datei
nur noch atomar in `current.jpg` umbenannt, die Wartezeit nach einem Tipp
verkuerzt sich dadurch.

- Vorgeladen wird immer nur das Bild nach dem aktuellen. Beim Zurueckblaettern
  und beim Umbruch am Listenende wird das Bild wie bisher direkt erzeugt.
- Nach einem Rescan, einem Wechsel der Reihenfolge oder wenn das Vorladen
  fehlschlaegt, faellt der Dienst ebenfalls auf den direkten Weg zurueck.
  Fehler stehen als `Vorladen fehlgeschlagen fuer ...` im Journal.
- Angehaltene Diashow: Das naechste Bild wird trotzdem einmal vorbereitet und
  beim Fortsetzen oder beim naechsten Tipp nach rechts verwendet.
- `next.jpg` (und die temporaere Datei `next.tmp.jpg`) liegen im selben Ordner
  wie `current.jpg` (`slideshow/www/img/`, Laufzeitdaten, nicht Teil des
  Repositorys).

## Warnung bei leerer Playlist

Findet ein Scan keine Bilder (typisch: NAS nicht gemountet, Ordner nicht
lesbar), schreibt der Dienst eine Warnung ins Journal und sendet an das
Notification-Overlay die Meldung `Diashow: Keine Bilder gefunden (NAS pruefen)`
(mit Umlaut `prüfen`) auf `display/kueche/cmd/notify`.

- Die Meldung wird hoechstens alle 10 Minuten wiederholt, auch wenn der Dienst
  weiter erfolglos scannt.
- Sobald wieder Bilder gefunden werden, hebt der Dienst die Meldung per
  `display/kueche/cmd/notify/clear` auf (Journal: `Bilder wieder gefunden`).
  Das blendet auch eine zu diesem Zeitpunkt angezeigte andere Meldung aus.
- Das Topic laesst sich mit `notify_topic` in der `config.json` aendern; das
  Aufheben nutzt `<notify_topic>/clear`.

Test (Bilderordner voruebergehend auf einen leeren Ordner setzen):

```bash
mkdir -p /tmp/leer
cp ~/kuechendisplay/slideshow/config.json /tmp/config.backup.json
sed -i 's#"image_root": *"[^"]*"#"image_root": "/tmp/leer"#' ~/kuechendisplay/slideshow/config.json
sudo systemctl restart kuechendisplay-diashow.service

# danach zuruecksetzen
cp /tmp/config.backup.json ~/kuechendisplay/slideshow/config.json
sudo systemctl restart kuechendisplay-diashow.service
```

## Diagnose-Modus (?debug=1)

Mit dem Parameter `?debug=1` blendet die Seite unten links einen
Diagnose-Bereich ein. Die erste Zeile zeigt die aktuelle Position, den
Dateinamen und die Reihenfolge (`Bild 17 / 252  dateiname.jpg  [zufall]`), bei
angehaltener Diashow zusaetzlich `[PAUSE]`. Darunter stehen die letzten acht
Ereignisse mit Uhrzeit (`pointerdown`, `pointerup`, `pointercancel`,
`touchstart`, `touchend`, `click`, `senden prev|next|toggle` sowie Fehler beim
Senden). Der Bereich liegt rechts neben dem Pause-Symbol.

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
| `display/kueche/diashow/set/reihenfolge` | Eingang | `zufall` oder `reihenfolge` | Reihenfolge der Bilder umschalten (zufaellig bzw. sortiert nach Ordner und Dateiname); wird dauerhaft gespeichert |
| `display/kueche/diashow/set/rescan` | Eingang | beliebig, z. B. `1` | Loest einen Neu-Scan des NAS-Ordners aus |
| `display/kueche/diashow/set/aktiv` | Eingang | `ON` / `OFF` | Diashow fortsetzen/anhalten |
| `display/kueche/diashow/set/naechstes` | Eingang | beliebig, z. B. `1` | Zum naechsten Bild blaettern |
| `display/kueche/diashow/set/vorheriges` | Eingang | beliebig, z. B. `1` | Zum vorherigen Bild blaettern |
| `display/kueche/diashow/status` (retain) | Ausgang | JSON `{"intervall":..., "reihenfolge":..., "anzahl_bilder":..., "letzter_scan":..., "aktiv":..., "seq":..., "index":..., "datei":...}` | Aktueller Zustand fuer Dashboards/Node-RED. `reihenfolge` ist `zufall` oder `reihenfolge`. `seq` ist ein Bildzaehler, der bei jedem neuen Bild um 1 steigt (Startwert: Unix-Zeit beim Dienststart). `index` ist die 1-basierte Position des angezeigten Bildes in der aktuellen Reihenfolge (`0` = noch kein Bild, z. B. direkt nach einem Scan), `datei` sein Dateiname. |

Zur Abgrenzung: Das Umschalten der **Anzeige** (Button 2, Watchdog) laeuft
ueber den bestehenden Supervisor-Namensraum `display/kueche/cmd/mode`, nicht
ueber die obigen Diashow-Topics; die Zeit bis zum automatischen Wechsel
stellt `display/kueche/cmd/slideshow/timeout` ein. Die Diashow-Topics steuern
ausschliesslich Inhalt/Tempo der Diashow selbst, unabhaengig davon, ob sie
gerade sichtbar ist. Vom Broker wiederholte retained Nachrichten auf den
`set/...`-Topics werden ignoriert.

Die Reihenfolge der Bilder ist zwischen zwei Scans fest. Neu geordnet wird
beim Start des Dienstes, nach einem Rescan, wenn die Liste einmal
durchgelaufen ist und beim Umschalten der Reihenfolge; danach beginnt `index`
bei einem Scan wieder bei 1 (Details in "Reihenfolge: zufaellig oder
sortiert").

### Intervall und Reihenfolge bleiben erhalten

Jedes per `set/intervall` gesetzte Intervall (z. B. vom Slider im
Node-RED-Dashboard) und jede per `set/reihenfolge` gesetzte Reihenfolge
speichert der Dienst in `~/.kuechendisplay/diashow_state.json`, z. B.
`{"intervall": 31.0, "reihenfolge": "zufall"}`. Beim Start des Dienstes haben
diese Werte Vorrang vor `default_interval` bzw. `default_order` aus der
`config.json`. Dadurch bleiben sie nach einem Neustart des Dienstes oder des
Pi erhalten.

- Ist die Datei nicht vorhanden, defekt oder enthaelt sie einen ungueltigen
  Wert (Intervall unter 2 s oder keine endliche Zahl, unbekannte
  Reihenfolge), gelten `default_interval` bzw. `default_order`; bei einem
  ungueltigen Inhalt steht eine Meldung im Journal.
- Der Zustand "pausiert" (`set/aktiv`, Tippen in die Mitte) wird bewusst
  **nicht** gespeichert. Nach jedem Start laeuft die Diashow und wechselt
  automatisch.
- Nicht endliche Werte (`inf`, `nan`) lehnt der Dienst ab und schreibt eine
  Warnung ins Journal.
- Zurueck zu den Werten aus der `config.json`: Datei loeschen und den Dienst
  neu starten.

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

# Sortiert (nach Ordner und Dateiname) bzw. wieder zufaellig
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/diashow/set/reihenfolge' -m reihenfolge
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/diashow/set/reihenfolge' -m zufall

# Diashow anhalten / fortsetzen
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/diashow/set/aktiv' -m OFF
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/diashow/set/aktiv' -m ON

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
  jeweiligen Bildes, nicht vorab fuer alle Bilder. Beim Vorladen laeuft sie
  fuer das jeweils naechste Bild bereits im Hintergrund.

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
- **Meldung "Diashow: Keine Bilder gefunden (NAS pruefen)"**: Der Scan findet
  keine Bilder. `findmnt /mnt/diashow` und `ls /mnt/diashow` pruefen, ggf.
  Mount neu anstossen (`sudo systemctl restart remote-fs.target`) und einen
  Rescan ausloesen (`set/rescan`). Die Meldung verschwindet von selbst, sobald
  wieder Bilder gefunden werden.
- **Diashow startet nicht automatisch**: `display/kueche/status/slideshow/timeout`
  pruefen (`0` = aus) und ob Taster, Touch oder MQTT-Kommandos den Timer
  laufend zuruecksetzen (siehe [`automatik.md`](automatik.md)).
- **Diashow steht still, obwohl kein Fehler im Journal steht**: Moeglicherweise
  ist sie angehalten (Tippen in die Mitte oder `set/aktiv` = `OFF`). Ein
  kleines Pause-Symbol unten links zeigt das an; `"aktiv": false` im Status
  bestaetigt es. Ein weiterer Tipp in die Mitte bzw. `set/aktiv` = `ON`
  setzt sie fort.
- **Intervall oder Reihenfolge springen nach einem Neustart auf den Standard**:
  Im Journal des Diashow-Dienstes muss beim Start
  `Gespeichertes Intervall geladen: ...` bzw.
  `Gespeicherte Reihenfolge geladen: ...` stehen
  (`sudo journalctl -u kuechendisplay-diashow.service -b --no-pager | grep -i gespeichert`).
  Fehlt die Zeile, existiert `~/.kuechendisplay/diashow_state.json` nicht
  oder ist ungueltig (dann steht eine Warnung im Journal). Pruefen, ob die
  Datei dem Benutzer des Dienstes (`christoph`) gehoert und beschreibbar ist
  (`ls -l ~/.kuechendisplay/`); Schreibfehler stehen als
  `Einstellungen konnten nicht gespeichert werden` im Journal. Ein Intervall
  unter 2 s oder `inf`/`nan` wird nicht uebernommen.
- **Tippen reagiert nicht**: Im Journal des Diashow-Dienstes muss
  `Navigations-API laeuft auf http://127.0.0.1:8091` stehen
  (`sudo journalctl -u kuechendisplay-diashow.service -n 30 --no-pager`).
  Steht dort `API-Port ... nicht verfuegbar`, belegt ein anderer Prozess den
  Port (`ss -ltnp | grep 8091`); dann `api_port` in `config.json` und `API` in
  `index.html` anpassen. Mit `curl -X POST http://127.0.0.1:8091/api/next`
  (bzw. `/api/prev`, `/api/toggle`) laesst sich die API ohne Touch pruefen.
  Die API lauscht nur auf `127.0.0.1`; ueber einen anderen Rechner im Netz
  funktioniert das Tippen daher nicht. Bei aktiver Kindersicherung ist der
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
