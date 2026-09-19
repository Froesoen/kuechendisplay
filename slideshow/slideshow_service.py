#!/usr/bin/env python3
"""Kuechendisplay - Diashow-Modul.

Durchsucht rekursiv einen Bilderordner (NAS-Mount), zeigt die Bilder in
zufaelliger Reihenfolge an und stellt Steuerung/Status per MQTT bereit.

Vor jeder Anzeige wird geprueft, ob ein Bild bereits auf max. 1920x1080
verkleinert ist. Falls nicht, wird es proportional verkleinert und die
Originaldatei ueberschrieben (im Quellordner liegen laut Vorgabe nur Kopien,
ein Ueberschreiben ist also unkritisch).

Manueller Rescan sowie Anzeigegeschwindigkeit sind per MQTT steuerbar.
"""

from __future__ import annotations

import os
import json
import time
import random
import shutil
import logging
import datetime
import threading
from pathlib import Path
from typing import Optional, List

from PIL import Image, ImageOps
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("diashow")

CONFIG_PATH = Path(os.environ.get("DIASHOW_CONFIG", "/home/christoph/kuechendisplay/slideshow/config.json"))


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

        self.interval = float(config.get("default_interval", 10.0))
        self.playlist: List[Path] = []
        self.index = 0
        self.last_scan: Optional[str] = None
        self.active = True

        self.rescan_requested = threading.Event()
        self.stop_requested = threading.Event()

        prefix = config["mqtt"]["topic_prefix"].rstrip("/")
        self.topic_prefix = prefix
        self.topic_set_interval = f"{prefix}/set/intervall"
        self.topic_set_rescan = f"{prefix}/set/rescan"
        self.topic_set_active = f"{prefix}/set/aktiv"
        self.topic_status = f"{prefix}/status"

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

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        log.info("MQTT verbunden (reason_code=%s)", reason_code)
        client.subscribe(f"{self.topic_prefix}/set/#")
        self._publish_status()

    def _on_message(self, client, userdata, msg):
        payload = msg.payload.decode(errors="ignore").strip()
        if msg.topic == self.topic_set_interval:
            try:
                self.interval = max(2.0, float(payload))
                log.info("Neues Intervall: %.1fs", self.interval)
                self._publish_status()
            except ValueError:
                log.warning("Ungueltiger Intervall-Payload: %r", payload)
        elif msg.topic == self.topic_set_rescan:
            log.info("Manueller Rescan ueber MQTT angefordert")
            self.rescan_requested.set()
        elif msg.topic == self.topic_set_active:
            self.active = payload.upper() not in ("OFF", "0", "FALSE")
            log.info("Diashow aktiv=%s", self.active)
            self._publish_status()

    def _publish_status(self):
        data = {
            "intervall": self.interval,
            "anzahl_bilder": len(self.playlist),
            "letzter_scan": self.last_scan,
            "aktiv": self.active,
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

    def scan_images(self) -> List[Path]:
        files = [
            p for p in self.image_root.rglob("*")
            if p.is_file() and p.suffix.lower() in self.VALID_EXT
        ]
        random.shuffle(files)
        log.info("Scan abgeschlossen: %d Bilder gefunden", len(files))
        return files

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

    def publish_current(self, path: Path) -> None:
        target = self.output_dir / "current.jpg"
        tmp = self.output_dir / "current.tmp.jpg"
        try:
            with Image.open(path) as img:
                img = ImageOps.exif_transpose(img)
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                img.save(tmp, format="JPEG", quality=self.jpeg_quality, optimize=True)
            os.replace(tmp, target)
        except Exception:
            log.exception("Fehler beim Erzeugen von %s", target)
            return
        self._publish_status()

    def run(self):
        self.client.connect(self.cfg["mqtt"]["host"], int(self.cfg["mqtt"].get("port", 1883)))
        self.client.loop_start()

        while not self.stop_requested.is_set():
            need_new_scan = (
                self.rescan_requested.is_set()
                or not self.playlist
                or self.index >= len(self.playlist)
            )
            if need_new_scan:
                self.playlist = self.scan_images()
                self.index = 0
                self.last_scan = datetime.datetime.now().isoformat(timespec="seconds")
                self.rescan_requested.clear()
                self._publish_status()

            if not self.active:
                time.sleep(1)
                continue

            if self.playlist:
                current = self.playlist[self.index]
                self.ensure_scaled(current)
                self.publish_current(current)
                self.index += 1

            time.sleep(self.interval)


def main():
    config = load_config()
    service = DiashowService(config)
    try:
        service.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
