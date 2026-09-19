# Diashow-Modul

Zeigt Bilder von einem NAS-Ordner in zufaelliger Reihenfolge im Kiosk-Browser
an. Geschwindigkeit und ein manueller Rescan sind per MQTT steuerbar. Bilder
werden vor der Anzeige bei Bedarf automatisch auf max. 1920x1080 verkleinert;
die Originaldatei im NAS-Ordner wird dabei ueberschrieben (im Ordner liegen
laut Vorgabe nur Kopien, ein Ueberschreiben ist unkritisch).

## Architektur

- **NAS-Mount**: SMB-Freigabe `08_kuechendisplay` wird per `systemd.automount`
  unter `/mnt/diashow` eingehaengt.
- **`slideshow_service.py`**: durchsucht den Mount rekursiv, mischt die
  Playlist, prueft/verkleinert Bilder vor der Anzeige, kopiert das aktuelle
  Bild nach `www/img/current.jpg` und meldet Status per MQTT sowie in
  `www/img/status.json`.
- **`www/index.html`**: einfache HTML/JS-Seite, die `current.jpg` und
  `status.json` per Polling abruft und im Kiosk-Browser fullscreen anzeigt.
- **Webserver**: liefert den `www`-Ordner mit `python3 -m http.server` auf
  Port 8090 fuer den Kiosk-Browser aus.

Der Kiosk-Controller kann die Diashow wie jede andere Ansicht einfach ueber
die URL `http://localhost:8090/` einbinden.

## Installation

Diese Anleitung gilt fuer den Benutzer `christoph` und den Checkout unter
`/home/christoph/kuechendisplay` (entspricht `~/kuechendisplay`).

### 1. Branch auschecken

```bash
cd ~/kuechendisplay
git fetch origin
git switch feature/diashow-modul
git pull --ff-only origin feature/diashow-modul
```

### 2. NAS-Mount

```bash
NAS="192.168.178.3"
SHARE="08_kuechendisplay"
MOUNT="/mnt/diashow"
USER="kuechendisplay"
PASS="kuechendisplay"

sudo apt update
sudo apt install -y cifs-utils smbclient dos2unix
sudo mkdir -p "$MOUNT"

sudo tee /etc/diashow_credentials >/dev/null <<EOF
username=$USER
password=$PASS
EOF
sudo chmod 600 /etc/diashow_credentials

smbclient "//$NAS/$SHARE" -U "$USER" -m SMB3 -c 'ls'

sudo mount.cifs "//$NAS/$SHARE" "$MOUNT" \
  -o "credentials=/etc/diashow_credentials,vers=2.0,uid=$(id -u christoph),gid=$(id -g christoph),noperm"
findmnt "$MOUNT"
ls -la "$MOUNT"

sudo umount "$MOUNT"
echo "//$NAS/$SHARE $MOUNT cifs credentials=/etc/diashow_credentials,vers=2.0,uid=$(id -u christoph),gid=$(id -g christoph),noperm,x-systemd.automount,noauto,_netdev,nofail 0 0" | sudo tee -a /etc/fstab
sudo systemctl daemon-reload
sudo systemctl restart remote-fs.target

ls -la "$MOUNT"
findmnt "$MOUNT"
```

Bilder duerfen direkt im Ordner `08_kuechendisplay` oder in beliebig tiefen
Unterordnern liegen; der Scan durchsucht rekursiv (`Path.rglob`).

### 3. Python-Abhaengigkeiten

```bash
sudo apt install -y python3-pil python3-paho-mqtt
```

### 4. Lokale Konfiguration

```bash
cd ~/kuechendisplay
mkdir -p slideshow/www/img
cp slideshow/config.example.json slideshow/config.json
chmod 600 slideshow/config.json
nano slideshow/config.json
```

Passe mindestens den MQTT-Bereich an. Die lokale `config.json` enthaelt
Zugangsdaten und wird nicht committed.

```json
{
  "image_root": "/mnt/diashow",
  "output_dir": "/home/christoph/kuechendisplay/slideshow/www/img",
  "mqtt": {
    "host": "DEINE-MQTT-BROKER-IP",
    "port": 1883,
    "username": "DEIN_MQTT_BENUTZER",
    "password": "DEIN_MQTT_PASSWORT",
    "topic_prefix": "kuechendisplay/diashow"
  }
}
```

### 5. Dienste einrichten

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
journalctl -u kuechendisplay-diashow.service -f
```

## MQTT-Schnittstelle

| Topic | Richtung | Payload | Zweck |
|---|---|---|---|
| `kuechendisplay/diashow/set/intervall` | Eingang | Sekunden, z. B. `15` | Anzeigedauer pro Bild aendern (min. 2s) |
| `kuechendisplay/diashow/set/rescan` | Eingang | beliebig, z. B. `1` | Loest einen Neu-Scan des NAS-Ordners aus |
| `kuechendisplay/diashow/set/aktiv` | Eingang | `ON` / `OFF` | Diashow pausieren/fortsetzen |
| `kuechendisplay/diashow/status` (retain) | Ausgang | JSON | Aktueller Zustand fuer Dashboards/Node-RED |

Beispiel fuer einen manuellen Rescan:

```bash
mosquitto_pub -h DEINE-MQTT-BROKER-IP \
  -u DEIN_MQTT_BENUTZER -P DEIN_MQTT_PASSWORT \
  -t kuechendisplay/diashow/set/rescan -m 1
```

Ein Rescan wird beim naechsten Bildwechsel verarbeitet, damit das aktuell
sichtbare Bild nicht abrupt unterbrochen wird.

## Verhalten der Groessenreduktion

- Vor jeder Anzeige wird die Bildgroesse per Pillow geprueft; EXIF-Rotation
  wird zuerst korrigiert.
- Passt das Bild bereits in 1920x1080, passiert nichts.
- Andernfalls wird proportional verkleinert (kein Zuschneiden, kein
  Hochskalieren) und atomar in die Originaldatei zurueckgeschrieben.
