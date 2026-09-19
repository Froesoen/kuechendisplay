"""kuechendisplay_supervisor.py - Hauptorchestrator des Kuechendisplay-Supervisors (v2).

Fuehrt alle Module zusammen: Kiosk/CDP, Yuvomi-Session/-User, Zustandsmodell,
Button-Mapper, Taster- und Fingerabdruck-Hardware, Display-Praeferenzen.

Display-Power (wlopm) wird NICHT hier ausgefuehrt, sondern im separaten
Prozess display_power_control.py.

Hinweis zum Dateinamen: Diese Datei heisst bewusst identisch zur
Vorgaengerversion (v1), weil der Dateiname im labwc-Autostart bzw. im
systemd-Unit kuechendisplay-supervisor.service fest verdrahtet ist.
"""

from __future__ import annotations

import json
import logging
import signal
import sys
import threading
import time

import paho.mqtt.client as mqtt

from config import (
    MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_BASE_TOPIC,
    YUVOMI_BASE_URL, DEFAULT_APP_URLS, HEARTBEAT_INTERVAL_SECONDS,
    SLIDESHOW_INACTIVITY_TIMEOUT_SECONDS, DISPLAY_PREFERENCES,
)
from state import StateStore
from kiosk_controller import KioskController, WallModeController, apply_display_preferences
from yuvomi_session import YuvomiSessionManager
from yuvomi_users import YuvomiUserManager
from button_mapper import ButtonMapper
from hardware_buttons import HardwareButtons
from hardware_fingerprint import FingerprintController, resolve_login_target

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("supervisor")


def full_topic(sub_topic: str) -> str:
    return MQTT_BASE_TOPIC + sub_topic


class Supervisor:
    def __init__(self) -> None:
        self.kiosk = KioskController()

        apply_display_preferences(self.kiosk, DISPLAY_PREFERENCES)

        self.yuvomi_session = YuvomiSessionManager(YUVOMI_BASE_URL, self.kiosk)
        self.wall_mode = WallModeController(self.kiosk)

        self.state_store = StateStore(on_change=self._publish_state)

        self.yuvomi_users = YuvomiUserManager(
            self.yuvomi_session,
            self.wall_mode,
            on_wall_mode_change=lambda enabled: self.state_store.update(wall_mode=enabled),
        )

        self.button_mapper = ButtonMapper(publish_fn=self._publish)

        self._shutdown_event = threading.Event()
        self._last_general_activity = time.time()

        self.hardware_buttons = HardwareButtons(on_event=self._on_button_event)
        self.fingerprint = FingerprintController(on_identified=self._on_fingerprint_identified)

        will_payload = json.dumps({"online": False, "reason": "connection_lost"})
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_client.will_set(full_topic("status/health"), will_payload, retain=True, qos=1)
        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_message = self._on_message

        signal.signal(signal.SIGTERM, self._handle_shutdown_signal)
        signal.signal(signal.SIGINT, self._handle_shutdown_signal)

        self.kiosk.clear_browser_cookies()
        self.yuvomi_users.ensure_familie_active()

    def _publish(self, topic: str, payload: str, retain: bool) -> None:
        self.mqtt_client.publish(topic, payload, retain=retain, qos=1)

    def _publish_state(self) -> None:
        state = self.state_store.state.as_dict()
        state["active_user"] = self.yuvomi_users.current_user
        self._publish(full_topic("status/state"), json.dumps(state), True)
        log.info("status/state aktualisiert: %s", state)

    def _publish_heartbeat(self) -> None:
        self._publish(full_topic("status/health"), json.dumps({"online": True, "ts": time.time()}), True)

    def _heartbeat_loop(self) -> None:
        while not self._shutdown_event.is_set():
            self._publish_heartbeat()
            self._shutdown_event.wait(HEARTBEAT_INTERVAL_SECONDS)

    def _note_activity(self) -> None:
        self._last_general_activity = time.time()

    def _slideshow_watchdog_loop(self) -> None:
        while not self._shutdown_event.is_set():
            time.sleep(10)
            idle = time.time() - self._last_general_activity
            if self.state_store.state.display_mode == "app" and idle >= SLIDESHOW_INACTIVITY_TIMEOUT_SECONDS:
                log.info(
                    "Inaktivitaet %ss ueberschritten - wechsle automatisch zu Slideshow",
                    SLIDESHOW_INACTIVITY_TIMEOUT_SECONDS,
                )
                self._set_display_mode("slideshow")

    def _set_display_mode(self, mode: str) -> None:
        if mode not in ("app", "slideshow"):
            log.error("Ungueltiger display_mode: %s", mode)
            return
        self.state_store.update(display_mode=mode)
        if mode == "app":
            self._set_active_app(self.state_store.state.active_app)

    def _set_active_app(self, app: str) -> None:
        if app == "yuvomi":
            self.state_store.update(active_app=app, display_mode="app")
            self.yuvomi_users.ensure_familie_active()
            return
        url = DEFAULT_APP_URLS.get(app)
        if url is None and app.startswith("custom:"):
            url = app.split("custom:", 1)[1]
        if url is None:
            log.error("Unbekannte App: %s", app)
            return
        self.state_store.update(active_app=app, display_mode="app")
        self.kiosk.navigate(url)

    def _set_display_power(self, powered_on: bool) -> None:
        self.state_store.update(display_power="on" if powered_on else "off")

    def _on_button_event(self, button_nr: int, press_type: str) -> None:
        self._note_activity()
        self.button_mapper.on_button_event(button_nr, press_type)

    def _on_fingerprint_identified(self, name) -> None:
        self._note_activity()
        self.state_store.update(display_mode="app")

        target = resolve_login_target(name)
        if target is None:
            self.yuvomi_users.ensure_familie_active(wall_mode=False)
            log.info("Fingerabdruck ohne individuelles Konto (%s) - Familie aktiv, Wallmode aus", name)
        else:
            display_name, username, password = target
            self.state_store.update(active_app="yuvomi")
            self.yuvomi_users.switch_user(username, password)
            log.info("Fingerabdruck-Login: %s", display_name)

    def _on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        log.info("MQTT verbunden, rc=%s", rc)
        client.subscribe(full_topic("cmd/#"))
        self._publish_heartbeat()
        self._publish_state()
        self.button_mapper.publish_full_map()

    def _on_message(self, client, userdata, msg) -> None:
        topic = msg.topic
        payload = msg.payload.decode("utf-8", errors="replace")
        log.info("MQTT empfangen: %s = %s", topic, payload)

        self._note_activity()
        self.yuvomi_users.on_activity()

        sub_topic = topic[len(MQTT_BASE_TOPIC):] if topic.startswith(MQTT_BASE_TOPIC) else topic

        try:
            if sub_topic == "cmd/mode":
                self._set_display_mode(payload)
            elif sub_topic == "cmd/app":
                self._set_active_app(payload)
            elif sub_topic == "cmd/display/power":
                normalized = payload.strip().lower()
                if normalized == "toggle":
                    self._set_display_power(self.state_store.state.display_power != "on")
                else:
                    self._set_display_power(normalized == "on")
            elif sub_topic == "cmd/wallmode":
                enabled = payload.strip().lower() == "on"
                self.wall_mode.set(enabled)
                self.state_store.update(wall_mode=enabled)
            elif sub_topic == "cmd/notify":
                log.info("Notification: %s (Anzeige uebernimmt notification_overlay.py)", payload)
            elif sub_topic == "cmd/notify/clear":
                log.info("Notification-Clear empfangen")
            elif sub_topic == "cmd/button/map":
                self.button_mapper.on_config_message(payload)
            elif sub_topic == "cmd/user":
                if ":" in payload:
                    username, password = payload.split(":", 1)
                    self.yuvomi_users.switch_user(username, password)
                else:
                    log.warning("cmd/user erwartet 'username:password' zum Testen")
            else:
                log.warning("Unbekanntes Topic: %s", sub_topic)
        except Exception:
            log.exception("Fehler bei Verarbeitung von %s", topic)

    def _handle_shutdown_signal(self, signum, frame) -> None:
        log.info("Signal %s empfangen - fahre sauber herunter", signum)
        self._shutdown_event.set()
        try:
            self._publish(full_topic("status/health"), json.dumps({"online": False, "reason": "clean_shutdown"}), True)
            self.mqtt_client.disconnect()
        except Exception:
            log.exception("Fehler beim sauberen Herunterfahren")
        sys.exit(0)

    def run(self) -> None:
        self.mqtt_client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=60)
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        threading.Thread(target=self._slideshow_watchdog_loop, daemon=True).start()
        self.mqtt_client.loop_forever()


if __name__ == "__main__":
    Supervisor().run()
