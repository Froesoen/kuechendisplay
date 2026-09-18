"""button_mapper.py - Tastenbelegung, konfigurierbar per MQTT (cmd/button/map)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from config import BUTTON_MAP_CACHE_FILE, MQTT_BASE_TOPIC

log = logging.getLogger("supervisor.button_mapper")

KEY_PATTERN = re.compile(r"^[1-4]_(short|long)$")

DEFAULT_BUTTON_MAP = {
    "1_short": {"topic": "cmd/app", "payload": "yuvomi"},
    "1_long": {"topic": "cmd/display/power", "payload": "toggle"},
    "2_short": {"topic": "cmd/mode", "payload": "slideshow"},
    "3_short": {"topic": "cmd/app", "payload": "nodered"},
    "4_short": {"topic": "cmd/notify/clear", "payload": ""},
}


def full_topic(sub_topic: str) -> str:
    return MQTT_BASE_TOPIC + sub_topic


@dataclass
class ButtonMapper:
    publish_fn: Callable[[str, str, bool], None]
    current_map: dict = field(default_factory=lambda: dict(DEFAULT_BUTTON_MAP))

    def __post_init__(self) -> None:
        cached = self._load_cache()
        if cached:
            self.current_map.update(cached)

    def _load_cache(self) -> Optional[dict]:
        try:
            if BUTTON_MAP_CACHE_FILE.exists():
                return json.loads(BUTTON_MAP_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("Button-Map-Cache konnte nicht geladen werden: %s", exc)
        return None

    def _save_cache(self) -> None:
        try:
            BUTTON_MAP_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            BUTTON_MAP_CACHE_FILE.write_text(json.dumps(self.current_map), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            log.warning("Button-Map-Cache konnte nicht geschrieben werden: %s", exc)

    def publish_full_map(self) -> None:
        self.publish_fn(full_topic("status/button/map"), json.dumps(self.current_map), True)

    def on_config_message(self, payload: str) -> None:
        try:
            entry = json.loads(payload)
        except json.JSONDecodeError as exc:
            log.error("Ungueltiges JSON in Button-Map-Nachricht: %s", exc)
            return

        key = entry.get("key")
        topic = entry.get("topic")
        entry_payload = entry.get("payload")

        if not isinstance(key, str) or not KEY_PATTERN.match(key):
            log.error("Ungueltiger oder fehlender Key in Button-Map-Nachricht: %r", key)
            return
        if not isinstance(topic, str) or not isinstance(entry_payload, str):
            log.error("topic/payload muessen Strings sein: %r", entry)
            return

        self.current_map[key] = {"topic": topic, "payload": entry_payload}
        self._save_cache()
        self.publish_full_map()
        log.info("Button-Map aktualisiert: %s -> %s", key, self.current_map[key])

    def on_button_event(self, button_nr: int, press_type: str) -> None:
        key = f"{button_nr}_{press_type}"
        entry = self.current_map.get(key)
        if entry is None:
            log.warning("Keine Belegung fuer %s", key)
            return
        self.publish_fn(full_topic(entry["topic"]), entry["payload"], False)
