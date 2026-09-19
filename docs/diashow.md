# Diashow-Modul

Zeigt Bilder von einem NAS-Ordner in zufaelliger Reihenfolge im Kiosk-Browser
an. Geschwindigkeit und ein manueller Rescan sind per MQTT steuerbar. Bilder
werden vor der Anzeige bei Bedarf automatisch auf max. 1920x1080 verkleinert;
die Originaldatei im NAS-Ordner wird dabei ueberschrieben (im Ordner liegen
laut Vorgabe nur Kopien, ein Ueberschreiben ist unkritisch).

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
  MQTT sowie in `slideshow/www/img/status.json`.
- **`slideshow/www/index.html`**: einfache HTML/JS-Seite, die `current.jpg`
  und `status.json` per Polling abruft und im Kiosk-Browser fullscreen
  anzeigt.
- **Webserver**: liefert `slideshow/www` mit `python3 -m http.server` auf
  Port 8090 fuer den Kiosk-Browser aus.
- **Supervisor-Integration**: `supervisor/config.py` definiert
  `DIASHOW_URL = "http://127.0.0.1:8090/"`. `_set_display_mode("slideshow")`
  im Supervisor navigiert den bestehenden Kiosk-Tab per CDP zu dieser URL.
  Button 2 (kurz) ist im `button_mapper.py` standardmaessig auf
  `cmd/mode=slideshow` gemappt; zusaetzlich schaltet der bestehende
  Inaktivitaets-Watchdog nach `SLIDESHOW_INACTIVITY_TIMEOUT_SECONDS`
  (10 Minuten) automatisch dorthin.

## Einrichtung

Diese Anleitung gilt fuer den Benutzer `christoph` und den Checkout unter
`/home/christoph/kuechendisplay` (entspricht `~/kuechendisplay`).

### 1. Branch auschecken

```bash
cd ~/kuechendisplay
git fetch origin
git switch feature/diashow-modul
git pull --ff-only origin feature/diashow-modul
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

Rueckkehr zur App-Ansicht (z. B. Yuvomi) manuell testen:

```bash
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/cmd/mode' -m app
```

Der automatische Inaktivitaets-Watchdog schaltet zusaetzlich nach 10 Minuten
ohne Aktivitaet selbststaendig auf die Diashow um (bestehende Supervisor-
Logik, `SLIDESHOW_INACTIVITY_TIMEOUT_SECONDS`).

## MQTT-Schnittstelle (Diashow-Modul)

| Topic | Richtung | Payload | Zweck |
|---|---|---|---|
| `display/kueche/diashow/set/intervall` | Eingang | Sekunden, z. B. `15` | Anzeigedauer pro Bild aendern (min. 2s) |
| `display/kueche/diashow/set/rescan` | Eingang | beliebig, z. B. `1` | Loest einen Neu-Scan des NAS-Ordners aus |
| `display/kueche/diashow/set/aktiv` | Eingang | `ON` / `OFF` | Diashow pausieren/fortsetzen |
| `display/kueche/diashow/status` (retain) | Ausgang | JSON `{"intervall":..., "anzahl_bilder":..., "letzter_scan":..., "aktiv":...}` | Aktueller Zustand fuer Dashboards/Node-RED |

Zur Abgrenzung: Das Umschalten der **Anzeige** (Button 2, Watchdog) laeuft
ueber den bestehenden Supervisor-Namensraum `display/kueche/cmd/mode`, nicht
ueber die obigen Diashow-Topics. Die Diashow-Topics steuern ausschliesslich
Inhalt/Tempo der Diashow selbst, unabhaengig davon, ob sie gerade sichtbar ist.

Beispiele:

```bash
# Manueller Rescan
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/diashow/set/rescan' -m 1

# Intervall auf 15s setzen
mosquitto_pub -h mqtt -p 1883 -t 'display/kueche/diashow/set/intervall' -m 15

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
- `current.jpg` wird unabhaengig vom Quellformat immer als JPEG erzeugt,
  damit auch PNG/WebP-Quellen im Browser-Frontend zuverlaessig angezeigt
  werden.

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
