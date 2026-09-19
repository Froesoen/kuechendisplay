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
- **Webserver**: liefert den `www`-Ordner (z. B. via `python3 -m http.server`
  auf Port 8090) fuer den Kiosk-Browser aus.

Der Kiosk-Controller kann die Diashow wie jede andere Ansicht (z. B. den
Familienplaner) einfach ueber die URL `http://localhost:8090/` einbinden.

## Einrichtung

### 1. NAS-Mount

```bash
NAS="192.168.178.3"      # IP/Hostname des NAS anpassen
SHARE="08_kuechendisplay"
MOUNT="/mnt/diashow"
USER="kuechendisplay"
PASS="kuechendisplay"

sudo apt install -y cifs-utils smbclient dos2unix
sudo mkdir -p "$MOUNT"

sudo tee /etc/diashow_credentials >/dev/null <<EOF
username=$USER
password=$PASS
EOF
sudo chmod 600 /etc/diashow_credentials

sudo cp /etc/fstab /etc/fstab.bak.$(date +%F-%H%M)
echo "//$NAS/$SHARE $MOUNT cifs credentials=/etc/diashow_credentials,vers=2.0,uid=$(id -u),gid=$(id -g),noperm,x-systemd.automount,noauto,_netdev,nofail 0 0" | sudo tee -a /etc/fstab >/dev/null

sudo systemctl daemon-reload
sudo systemctl restart remote-fs.target
```

Bilder duerfen direkt im Ordner `08_kuechendisplay` oder in beliebig tiefen
Unterordnern liegen; der Scan durchsucht rekursiv (`Path.rglob`).

### 2. Python-Abhaengigkeiten

```bash
pip install paho-mqtt Pillow
```

### 3. Konfiguration

`slideshow/config.example.json` nach `/opt/kuechendisplay/slideshow/config.json`
kopieren und Werte anpassen (NAS-Mountpfad, MQTT-Broker, Zugangsdaten,
Standard-Intervall).

### 4. Dienste einrichten

```bash
sudo cp slideshow/systemd/kuechendisplay-diashow.service /etc/systemd/system/
sudo cp slideshow/systemd/kuechendisplay-diashow-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kuechendisplay-diashow.service
sudo systemctl enable --now kuechendisplay-diashow-web.service
```

## MQTT-Schnittstelle

| Topic | Richtung | Payload | Zweck |
|---|---|---|---|
| `kuechendisplay/diashow/set/intervall` | Eingang | Sekunden, z. B. `15` | Anzeigedauer pro Bild aendern (min. 2s) |
| `kuechendisplay/diashow/set/rescan` | Eingang | beliebig, z. B. `1` | Loest sofortigen Neu-Scan des NAS-Ordners aus |
| `kuechendisplay/diashow/set/aktiv` | Eingang | `ON` / `OFF` | Diashow pausieren/fortsetzen |
| `kuechendisplay/diashow/status` (retain) | Ausgang | JSON `{"intervall": 15, "anzahl_bilder": 234, "letzter_scan": "...", "aktiv": true}` | aktueller Zustand fuer Dashboards/Node-RED |

Beispiel fuer einen manuellen Rescan von Hand:

```bash
mosquitto_pub -h 192.168.178.10 -u kuechendisplay -P changeme \
  -t kuechendisplay/diashow/set/rescan -m 1
```

Ein Rescan wirkt erst beim naechsten Bildwechsel, damit das aktuell gezeigte
Bild nicht abrupt unterbrochen wird.

## Verhalten der Groessenreduktion

- Vor jeder Anzeige wird die Bildgroesse per Pillow geprueft (EXIF-Rotation
  wird zuerst korrigiert).
- Passt das Bild bereits in 1920x1080, passiert nichts.
- Andernfalls wird proportional verkleinert (kein Zuschneiden, kein
  Hochskalieren) und ueber eine temporaere Datei atomar in die Originaldatei
  zurueckgeschrieben (`os.replace`), sodass nie eine unvollstaendige Datei
  gelesen werden kann.
