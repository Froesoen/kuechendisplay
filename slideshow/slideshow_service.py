#!/usr/bin/env python3
"""Kuechendisplay - Diashow-Modul.

Durchsucht rekursiv einen Bilderordner (NAS-Mount), zeigt die Bilder in
zufaelliger Reihenfolge an und stellt Steuerung/Status per MQTT bereit.

Vor jeder Anzeige wird geprueft, ob ein Bild bereits auf max. 1920x1080
verkleinert ist. Falls nicht, wird es proportional verkleinert und die
Originaldatei ueberschrieben (im Quellordner liegen laut Vorgabe nur Kopien,
ein Ueberschreiben ist also unkritisch).

Manueller Rescan, Anzeigegeschwindigkeit sowie Vor-/Zurueckblaettern sind per
MQTT steuerbar. Das Frontend (www/index.html) blaettert per Tippen auf die
linke bzw. rechte Bildschirmseite und haelt die Diashow per Tippen in die
Mitte an bzw. setzt sie fort. Dazu nutzt es einen kleinen lokalen
HTTP-Endpunkt (POST /api/next, /api/prev, /api/toggle auf 127.0.0.1:8091,
konfigurierbar mit api_host/api_port).

Das per MQTT eingestellte Intervall wird in ~/.kuechendisplay/diashow_state.json
(konfigurierbar mit state_file) gespeichert und beim naechsten Start wieder
geladen; es hat Vorrang vor default_interval aus der config.json. Der Zustand
"pausiert" wird bewusst nicht gespeichert.

Findet ein Scan keine Bilder (z. B. NAS nicht gemountet), meldet der Dienst
das per MQTT an das Notification-Overlay (notify_topic, Standard
<Praefix-Basis>/cmd/notify) und hebt die Meldung wieder auf, sobald Bilder
gefunden werden.
"""

from __future__ import annotations

import os
import json
import math
import time
import random
import shutil
import logging
import datetime
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional, List

from PIL import Image, ImageOps
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("diashow")

CONFIG_PATH = Path(os.environ.get("DIASHOW_CONFIG", "/home/christoph/kuechendisplay/slideshow/config.json"))
DEFAULT_STATE_FILE = Path.home() / ".kuechendisplay" / "diashow_state.json"
MIN_INTERVAL_SECONDS = 2.0
EMPTY_NOTIFY_INTERVAL_SECONDS = 600
EMPTY_NOTIFY_TEXT = "Diashow: Keine Bilder gefunden (NAS prüfen)"

EXIF_ORIENTATION_TAG = 0x0112


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class DiashowService:
    VALID_EXT = {".jpg", ".jpeg", ".png", ".webp"}
    PIL_FORMATS = {
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".png": "PNG",
        ".webp": "WEBP",
    }

    def __init__(self, config: dict):
        self.cfg = config
        self.image_root = Path(config["image_root"])
        self.output_dir = Path(config["output_dir"])
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.target_w = int(config.get("target_width", 1920))
        self.target_h = int(config.get("target_height", 1080))
        self.jpeg_quality = int(config.get("jpeg_quality", 85))

        self.state_file = Path(config.get("state_file", DEFAULT_STATE_FILE)).expanduser()
        self.interval = float(config.get("default_interval", 10.0))
        saved_interval = self._load_interval()
        if saved_interval is not None:
            self.interval = saved_interval
            log.info("Gespeichertes Intervall geladen: %.1fs (%s)", self.interval, self.state_file)
        self.playlist: List[Path] = []
        # Position des aktuell angezeigten Bildes in der Playlist (-1 = noch keins)
        self.pos = -1
        # Dateiname des aktuell angezeigten Bildes (fuer den Status)
        self.current_name: Optional[str] = None
        self.last_scan: Optional[str] = None
        self.active = True
        # Startet bei der Unix-Zeit, damit ein Dienst-Neustart nie einen
        # bereits gesehenen Zaehlerwert wiederholt.
        self.seq = int(time.time())

        self.rescan_requested = threading.Event()
        self.stop_requested = threading.Event()
        self._wake = threading.Event()
        self._nav_lock = threading.Lock()
        self._nav_pending = 0
        # True, sobald mindestens ein manueller Wechsel angefordert wurde
        # (auch wenn sich Vor und Zurueck zu 0 aufheben).
        self._nav_requested = False

        prefix = config["mqtt"]["topic_prefix"].rstrip("/")
        self.topic_prefix = prefix
        self.topic_set_interval = f"{prefix}/set/intervall"
        self.topic_set_rescan = f"{prefix}/set/rescan"
        self.topic_set_active = f"{prefix}/set/aktiv"
        self.topic_set_next = f"{prefix}/set/naechstes"
        self.topic_set_prev = f"{prefix}/set/vorheriges"
        self.topic_status = f"{prefix}/status"

        # Meldungen am Display (Notification-Overlay): Standard ist der
        # Supervisor-Namensraum neben dem Diashow-Praefix, z. B.
        # display/kueche/diashow -> display/kueche/cmd/notify
        default_notify = (prefix.rsplit("/", 1)[0] + "/cmd/notify") if "/" in prefix else None
        self.topic_notify = config.get("notify_topic", default_notify)
        self._empty_warned = False
        self._last_empty_notify: Optional[float] = None

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=config["mqtt"].get("client_id", "kuechendisplay-diashow"),
        )
        user = config["mqtt"].get("username")
        pw = config["mqtt"].get("password")
        if user:
            self.client.username_pw_set(user, pw)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _load_interval(self) -> Optional[float]:
        """Liest das gespeicherte Intervall; None = nichts (Gueltiges) gespeichert."""
        try:
            value = float(json.loads(self.state_file.read_text(encoding="utf-8"))["intervall"])
        except FileNotFoundError:
            return None
        except Exception:
            log.exception("Gespeichertes Intervall konnte nicht gelesen werden - nutze default_interval")
            return None
        if not math.isfinite(value) or value < MIN_INTERVAL_SECONDS:
            log.warning("Gespeichertes Intervall %r ungueltig - nutze default_interval", value)
            return None
        return value

    def _save_interval(self) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_name(self.state_file.name + ".tmp")
            tmp.write_text(json.dumps({"intervall": self.interval}), encoding="utf-8")
            os.replace(tmp, self.state_file)
        except Exception:
            log.exception("Intervall konnte nicht gespeichert werden (%s)", self.state_file)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        log.info("MQTT verbunden (reason_code=%s)", reason_code)
        client.subscribe(f"{self.topic_prefix}/set/#")
        self._publish_status()

    def _on_message(self, client, userdata, msg):
        # Vom Broker wiederholte gespeicherte Nachrichten sind keine neuen
        # Kommandos (verhindert z. B. erneutes Blaettern nach einem Reconnect).
        if msg.retain:
            return
        payload = msg.payload.decode(errors="ignore").strip()
        if msg.topic == self.topic_set_interval:
            try:
                value = float(payload)
                if not math.isfinite(value):
                    raise ValueError(payload)
                self.interval = max(MIN_INTERVAL_SECONDS, value)
                self._save_interval()
                log.info("Neues Intervall: %.1fs", self.interval)
                self._publish_status()
            except ValueError:
                log.warning("Ungueltiger Intervall-Payload: %r", payload)
        elif msg.topic == self.topic_set_rescan:
            log.info("Manueller Rescan ueber MQTT angefordert")
            self.rescan_requested.set()
            self._wake.set()
        elif msg.topic == self.topic_set_active:
            self.active = payload.upper() not in ("OFF", "0", "FALSE")
            log.info("Diashow aktiv=%s", self.active)
            self._publish_status()
            self._wake.set()
        elif msg.topic == self.topic_set_next:
            self.navigate(1)
        elif msg.topic == self.topic_set_prev:
            self.navigate(-1)

    def toggle_active(self) -> None:
        """Haelt die Diashow an bzw. setzt sie fort (Tippen in die Bildmitte)."""
        self.active = not self.active
        log.info("Diashow aktiv=%s (Tipp in die Mitte)", self.active)
        self._publish_status()
        self._wake.set()

    def navigate(self, delta: int) -> None:
        """Blaettert um delta Bilder (positiv = vor, negativ = zurueck).

        Thread-sicher: wird aus dem MQTT-Thread und dem HTTP-Thread aufgerufen.
        Mehrere schnelle Aufrufe werden zusammengefasst. Heben sich Vor und
        Zurueck auf (Summe 0), wird das aktuelle Bild erneut angezeigt und
        nicht automatisch weitergeschaltet.
        """
        with self._nav_lock:
            self._nav_pending += delta
            self._nav_requested = True
        self._wake.set()
        log.info("Manuelle Navigation: %+d", delta)

    def start_api(self) -> None:
        host = str(self.cfg.get("api_host", "127.0.0.1"))
        port = int(self.cfg.get("api_port", 8091))
        service = self

        class Handler(BaseHTTPRequestHandler):
            def _reply(self, code: int) -> None:
                self.send_response(code)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                self.end_headers()

            def do_OPTIONS(self):
                self._reply(204)

            def do_POST(self):
                if self.path == "/api/next":
                    service.navigate(1)
                    self._reply(204)
                elif self.path == "/api/prev":
                    service.navigate(-1)
                    self._reply(204)
                elif self.path == "/api/toggle":
                    service.toggle_active()
                    self._reply(204)
                else:
                    self._reply(404)

            def log_message(self, fmt, *args):
                pass

        try:
            server = ThreadingHTTPServer((host, port), Handler)
        except OSError:
            log.exception("API-Port %s:%s nicht verfuegbar - Bedienung per Tippen deaktiviert", host, port)
            return
        threading.Thread(target=server.serve_forever, daemon=True).start()
        log.info("Navigations-API laeuft auf http://%s:%s", host, port)

    def _publish_status(self):
        data = {
            "intervall": self.interval,
            "anzahl_bilder": len(self.playlist),
            "letzter_scan": self.last_scan,
            "aktiv": self.active,
            "seq": self.seq,
            # 1-basierte Position des angezeigten Bildes, 0 = noch keins
            "index": (self.pos + 1) if (self.pos >= 0 and self.current_name) else 0,
            "datei": self.current_name,
        }
        try:
            self.client.publish(self.topic_status, json.dumps(data), retain=True)
        except Exception:
            log.exception("MQTT-Status konnte nicht publiziert werden")

        try:
            status_file = self.output_dir / "status.json"
            tmp = self.output_dir / "status.json.tmp"
            tmp.write_text(json.dumps(data), encoding="utf-8")
            os.replace(tmp, status_file)
        except Exception:
            log.exception("status.json konnte nicht geschrieben werden")

    def _publish_notify(self, text: str) -> None:
        if not self.topic_notify:
            return
        try:
            self.client.publish(self.topic_notify, text, qos=1)
        except Exception:
            log.exception("Meldung konnte nicht gesendet werden")

    def _clear_notify(self) -> None:
        if not self.topic_notify:
            return
        try:
            self.client.publish(self.topic_notify + "/clear", "", qos=1)
        except Exception:
            log.exception("Meldung konnte nicht aufgehoben werden")

    def scan_images(self) -> List[Path]:
        try:
            files = [
                p for p in self.image_root.rglob("*")
                if p.is_file() and p.suffix.lower() in self.VALID_EXT
            ]
        except OSError:
            log.exception("Bilderordner %s nicht lesbar", self.image_root)
            files = []
        random.shuffle(files)
        log.info("Scan abgeschlossen: %d Bilder gefunden", len(files))
        return files

    def _rescan(self) -> None:
        self.playlist = self.scan_images()
        # Die alte Position gehoert zur alten Reihenfolge und ist ungueltig.
        self.pos = -1
        self.current_name = None
        self.last_scan = datetime.datetime.now().isoformat(timespec="seconds")
        self.rescan_requested.clear()
        self._check_empty_playlist()
        self._publish_status()

    def _check_empty_playlist(self) -> None:
        """Meldet eine leere Playlist am Display und hebt die Meldung wieder auf."""
        if not self.playlist:
            now = time.monotonic()
            if self._last_empty_notify is None or now - self._last_empty_notify >= EMPTY_NOTIFY_INTERVAL_SECONDS:
                self._last_empty_notify = now
                log.warning("Keine Bilder gefunden in %s - NAS-Mount pruefen", self.image_root)
                self._publish_notify(EMPTY_NOTIFY_TEXT)
            self._empty_warned = True
        elif self._empty_warned:
            self._empty_warned = False
            self._last_empty_notify = None
            log.info("Bilder wieder gefunden - Meldung wird aufgehoben")
            self._clear_notify()

    def ensure_scaled(self, path: Path) -> None:
        """Prueft Bildgroesse und verkleinert + ueberschreibt bei Bedarf."""
        suffix = path.suffix.lower()
        try:
            with Image.open(path) as img:
                img = ImageOps.exif_transpose(img)
                w, h = img.size
                if w <= self.target_w and h <= self.target_h:
                    return

                img.thumbnail((self.target_w, self.target_h), Image.LANCZOS)
                tmp = path.with_name(f"{path.stem}.resize-tmp{path.suffix}")
                save_kwargs = {}
                if suffix in (".jpg", ".jpeg"):
                    if img.mode not in ("RGB", "L"):
                        img = img.convert("RGB")
                    save_kwargs = {"quality": self.jpeg_quality, "optimize": True}
                img.save(tmp, format=self.PIL_FORMATS[suffix], **save_kwargs)
                os.replace(tmp, path)
                log.info("Verkleinert: %s (%dx%d -> %s)", path.name, w, h, img.size)
        except Exception:
            log.exception("Fehler beim Verkleinern von %s", path)

    def _can_copy_directly(self, path: Path) -> bool:
        """True, wenn die Datei ohne Neukodierung als current.jpg dienen kann.

        Voraussetzung: JPEG (RGB/Graustufen), passt in die Zielgroesse und hat
        keine EXIF-Drehung.
        """
        if path.suffix.lower() not in (".jpg", ".jpeg"):
            return False
        try:
            with Image.open(path) as img:
                if img.format != "JPEG" or img.mode not in ("RGB", "L"):
                    return False
                w, h = img.size
                if w > self.target_w or h > self.target_h:
                    return False
                return img.getexif().get(EXIF_ORIENTATION_TAG, 1) in (0, 1)
        except Exception:
            return False

    def publish_current(self, path: Path) -> None:
        target = self.output_dir / "current.jpg"
        tmp = self.output_dir / "current.tmp.jpg"
        try:
            if self._can_copy_directly(path):
                shutil.copyfile(path, tmp)
            else:
                with Image.open(path) as img:
                    img = ImageOps.exif_transpose(img)
                    if img.mode not in ("RGB", "L"):
                        img = img.convert("RGB")
                    img.save(tmp, format="JPEG", quality=self.jpeg_quality, optimize=True)
            os.replace(tmp, target)
        except Exception:
            log.exception("Fehler beim Erzeugen von %s", target)
            return
        self.current_name = path.name
        # seq erst nach dem Ersetzen von current.jpg erhoehen: das Frontend
        # laedt das Bild, sobald sich seq in status.json aendert.
        self.seq += 1
        self._publish_status()

    def run(self):
        self.client.connect(self.cfg["mqtt"]["host"], int(self.cfg["mqtt"].get("port", 1883)))
        self.client.loop_start()
        self.start_api()

        while not self.stop_requested.is_set():
            with self._nav_lock:
                delta = self._nav_pending
                manual = self._nav_requested
                self._nav_pending = 0
                self._nav_requested = False

            if self.rescan_requested.is_set() or not self.playlist:
                self._rescan()
                delta = 0
                manual = False

            if not self.active and not manual:
                self._wake.wait(1.0)
                self._wake.clear()
                continue

            if self.playlist:
                count = len(self.playlist)
                if manual:
                    if delta != 0:
                        # manuell: umlaufend vor/zurueck
                        self.pos = (self.pos + delta) % count
                    elif self.pos < 0:
                        self.pos = 0
                    # delta == 0 bei gueltiger Position: aktuelles Bild erneut anzeigen
                else:
                    self.pos += 1
                    if self.pos >= count:
                        # Playlist durch: neu scannen und mischen
                        self._rescan()
                        self.pos = 0 if self.playlist else -1

                if self.playlist and 0 <= self.pos < len(self.playlist):
                    current = self.playlist[self.pos]
                    self.ensure_scaled(current)
                    self.publish_current(current)

            # Wartet bis zum naechsten automatischen Wechsel; ein Tipp oder
            # MQTT-Kommando weckt sofort und startet den Timer damit neu.
            self._wake.wait(timeout=self.interval)
            self._wake.clear()


def main():
    config = load_config()
    service = DiashowService(config)
    try:
        service.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
