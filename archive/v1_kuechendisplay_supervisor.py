"""
ARCHIV - v1 (erste funktionierende Testversion, veraltet)
==========================================================
Diese Datei wird nicht mehr gepflegt und dient nur der Historie.
Der aktive Supervisor liegt unter supervisor/kuechendisplay_supervisor.py.
==========================================================

kuechendisplay_supervisor.py  -  v0.1.3
"""

from __future__ import annotations

import json
import logging
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

import paho.mqtt.client as mqtt
import pychrome
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("supervisor")

MQTT_BROKER_HOST = "mqtt"
MQTT_BROKER_PORT = 1883
MQTT_BASE_TOPIC = "display/kueche/"

CDP_URL = "http://127.0.0.1:9222"
CDP_WAIT_TIMEOUT_SECONDS = 60
CDP_WAIT_POLL_INTERVAL_SECONDS = 2

YUVOMI_BASE_URL = "http://planer:3000"
YUVOMI_REQUEST_TIMEOUT_SECONDS = 15
YUVOMI_RETRY_DELAY_SECONDS = 3

USER_INACTIVITY_TIMEOUT_SECONDS = 5 * 60
HEARTBEAT_INTERVAL_SECONDS = 30

SECRETS_FILE = Path.home() / ".kuechendisplay" / "secrets.json"
BUTTON_MAP_CACHE_FILE = Path.home() / ".kuechendisplay" / "button_map.json"

DEFAULT_APP_URLS = {
    "yuvomi": YUVOMI_BASE_URL,
    "nodered": "http://nodered:1880/ui",
}

DEFAULT_BUTTON_MAP = {
    "1": {"topic": "cmd/mode", "payload": "slideshow"},
    "2": {"topic": "cmd/wallmode", "payload": "on"},
    "3": {"topic": "cmd/mode", "payload": "sleep"},
    "4": {"topic": "cmd/mode", "payload": "app"},
}


def full_topic(sub_topic: str) -> str:
    return MQTT_BASE_TOPIC + sub_topic


def load_secrets() -> dict:
    if SECRETS_FILE.exists():
        try:
            data = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
            log.info("Zugangsdaten aus %s geladen", SECRETS_FILE)
            return data
        except Exception:
            log.exception("Secrets-Datei %s konnte nicht gelesen werden", SECRETS_FILE)
    else:
        log.warning("Secrets-Datei %s fehlt.", SECRETS_FILE)
    return {}


SECRETS = load_secrets()
FAMILIE_USERNAME = SECRETS.get("familie_username", "familie")
FAMILIE_PASSWORD = SECRETS.get("familie_password", "PLATZHALTER_BITTE_SECRETS_JSON_ANLEGEN")


class KioskController:
    def __init__(self, cdp_url: str = CDP_URL) -> None:
        self.cdp_url = cdp_url
        self.browser = pychrome.Browser(url=cdp_url)
        self.tab: Optional[pychrome.Tab] = None
        self._wait_for_cdp_and_attach()

    def _wait_for_cdp_and_attach(self) -> None:
        deadline = time.time() + CDP_WAIT_TIMEOUT_SECONDS
        last_error = None
        while time.time() < deadline:
            try:
                self._attach_to_page_tab()
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                log.warning("CDP-Port noch nicht erreichbar (%s) - warte %ss", exc, CDP_WAIT_POLL_INTERVAL_SECONDS)
                time.sleep(CDP_WAIT_POLL_INTERVAL_SECONDS)
        raise RuntimeError(f"Chromium-CDP-Port unter {self.cdp_url} nicht erreichbar - {last_error}")

    def _attach_to_page_tab(self) -> None:
        tabs = self.browser.list_tab()
        page_tabs = [t for t in tabs if t._kwargs.get("type") == "page"]
        if not page_tabs:
            resp = requests.put(f"{self.cdp_url}/json/new?about:blank", timeout=5)
            resp.raise_for_status()
            tabs = self.browser.list_tab()
            page_tabs = [t for t in tabs if t._kwargs.get("type") == "page"]

        self.tab = page_tabs[0]
        self.tab.start()
        self.tab.Page.enable()
        self.tab.Runtime.enable()
        self.tab.Network.enable()
        log.info("Kiosk-Controller an Tab %s angehaengt", self.tab.id)

    def navigate(self, url: str) -> None:
        self.tab.Page.navigate(url=url)

    def evaluate(self, expression: str) -> dict:
        return self.tab.Runtime.evaluate(expression=expression, returnByValue=True)

    def set_local_storage(self, key: str, value: Optional[str]) -> None:
        if value is None:
            expr = f"window.localStorage.removeItem({json.dumps(key)})"
        else:
            expr = f"window.localStorage.setItem({json.dumps(key)}, {json.dumps(value)})"
        self.evaluate(expr)

    def set_cookies(self, cookies: list) -> None:
        for cookie in cookies:
            try:
                self.tab.Network.setCookie(**cookie)
            except Exception:
                log.exception("Network.setCookie Fehler fuer: %s", cookie)

    def get_cookies(self, urls=None) -> list:
        if urls:
            return self.tab.Network.getCookies(urls=urls).get("cookies", [])
        return self.tab.Network.getCookies().get("cookies", [])

    def reload(self) -> None:
        self.tab.Page.reload(ignoreCache=False)


class YuvomiSessionManager:
    def __init__(self, base_url: str, kiosk: KioskController) -> None:
        self.base_url = base_url.rstrip("/")
        self.kiosk = kiosk
        self.session = requests.Session()
        self._real_host = urlparse(self.base_url).hostname

    def login(self, username: str, password: str, _retry: bool = True) -> bool:
        try:
            resp = self.session.post(
                f"{self.base_url}/api/v1/auth/login",
                json={"username": username, "password": password},
                timeout=YUVOMI_REQUEST_TIMEOUT_SECONDS,
            )
        except requests.exceptions.RequestException as exc:
            log.error("Yuvomi-Login: Netzwerkfehler (%s)", exc)
            if _retry:
                time.sleep(YUVOMI_RETRY_DELAY_SECONDS)
                return self.login(username, password, _retry=False)
            return False

        if resp.status_code != 200:
            return False
        data = resp.json()
        if data.get("twoFactorRequired"):
            return False

        self._apply_cookies_to_kiosk()
        self.kiosk.navigate(self.base_url)
        return True

    def logout(self, _retry: bool = True) -> bool:
        csrf_token = self.session.cookies.get("csrf-token")
        try:
            resp = self.session.post(
                f"{self.base_url}/api/v1/auth/logout",
                headers={"X-CSRF-Token": csrf_token} if csrf_token else {},
                timeout=YUVOMI_REQUEST_TIMEOUT_SECONDS,
            )
        except requests.exceptions.RequestException:
            if _retry:
                time.sleep(YUVOMI_RETRY_DELAY_SECONDS)
                return self.logout(_retry=False)
            self.session.cookies.clear()
            return False

        ok = resp.status_code == 200
        self.session.cookies.clear()
        return ok

    def _apply_cookies_to_kiosk(self) -> None:
        page_url = f"{self.base_url}/"
        cookies_payload = []
        for cookie in self.session.cookies:
            cookies_payload.append({
                "name": cookie.name, "value": cookie.value, "url": page_url,
                "domain": self._real_host, "path": cookie.path or "/", "secure": False,
                "sameSite": "Lax",
            })
        self.kiosk.set_cookies(cookies_payload)


WALL_MODE_KEY = "yuvomi-wall-mode"


class WallModeController:
    def __init__(self, kiosk: KioskController) -> None:
        self.kiosk = kiosk

    def set(self, enabled: bool) -> None:
        self.kiosk.set_local_storage(WALL_MODE_KEY, "1" if enabled else None)
        self.kiosk.reload()


class YuvomiUserManager:
    def __init__(self, session_manager: YuvomiSessionManager, on_change=None) -> None:
        self.session_manager = session_manager
        self.current_user = FAMILIE_USERNAME
        self.on_change = on_change
        self._last_activity = time.time()
        self._lock = threading.Lock()
        threading.Thread(target=self._watchdog_loop, daemon=True).start()

    def on_activity(self) -> None:
        with self._lock:
            self._last_activity = time.time()

    def ensure_familie_active(self) -> None:
        with self._lock:
            self.current_user = FAMILIE_USERNAME
        self.session_manager.logout()
        self.session_manager.login(FAMILIE_USERNAME, FAMILIE_PASSWORD)
        self.on_activity()
        if self.on_change:
            self.on_change()

    def switch_user(self, username: str, password: str) -> bool:
        with self._lock:
            if self.current_user == username:
                self.on_activity()
                return True
        self.session_manager.logout()
        ok = self.session_manager.login(username, password)
        if ok:
            with self._lock:
                self.current_user = username
            self.on_activity()
        if self.on_change:
            self.on_change()
        return ok

    def _fallback_to_familie(self) -> None:
        with self._lock:
            if self.current_user == FAMILIE_USERNAME:
                return
            self.current_user = FAMILIE_USERNAME
        self.session_manager.logout()
        self.session_manager.login(FAMILIE_USERNAME, FAMILIE_PASSWORD)
        self.on_activity()
        if self.on_change:
            self.on_change()

    def _watchdog_loop(self) -> None:
        while True:
            time.sleep(10)
            with self._lock:
                is_familie = self.current_user == FAMILIE_USERNAME
                idle_seconds = time.time() - self._last_activity
            if not is_familie and idle_seconds >= USER_INACTIVITY_TIMEOUT_SECONDS:
                self._fallback_to_familie()


@dataclass
class ButtonMapper:
    publish_fn: Callable[[str, str, bool], None]
    current_map: dict = field(default_factory=lambda: dict(DEFAULT_BUTTON_MAP))

    def on_config_message(self, payload: str) -> None:
        try:
            new_map = json.loads(payload)
        except json.JSONDecodeError:
            return
        self.current_map = new_map
        self.publish_fn(full_topic("status/button/map"), json.dumps(self.current_map), True)

    def on_button_pressed(self, button_nr: str) -> None:
        entry = self.current_map.get(button_nr)
        if entry is None:
            return
        self.publish_fn(full_topic(entry["topic"]), entry["payload"], False)


class StateMachine:
    VALID_MODES = {"app", "slideshow", "idle-slideshow", "sleep", "off"}

    def __init__(self, kiosk, yuvomi_users, on_change=None) -> None:
        self.kiosk = kiosk
        self.yuvomi_users = yuvomi_users
        self.on_change = on_change
        self.mode = "app"
        self.current_app = "yuvomi"

    def set_mode(self, mode: str) -> None:
        if mode not in self.VALID_MODES:
            return
        self.mode = mode
        if mode == "app":
            self.set_app(self.current_app)
            return
        if self.on_change:
            self.on_change()

    def set_app(self, app: str) -> None:
        if app == "yuvomi":
            self.current_app = app
            self.yuvomi_users.ensure_familie_active()
            return
        url = DEFAULT_APP_URLS.get(app)
        if url is None and app.startswith("custom:"):
            url = app.split("custom:", 1)[1]
        if url is None:
            return
        self.current_app = app
        self.kiosk.navigate(url)
        if self.on_change:
            self.on_change()


class Supervisor:
    def __init__(self) -> None:
        self.kiosk = KioskController()
        self.yuvomi_session = YuvomiSessionManager(YUVOMI_BASE_URL, self.kiosk)
        self.yuvomi_users = YuvomiUserManager(self.yuvomi_session, on_change=self._publish_state)
        self.state_machine = StateMachine(self.kiosk, self.yuvomi_users, on_change=self._publish_state)
        self.wall_mode = WallModeController(self.kiosk)
        self.button_mapper = ButtonMapper(publish_fn=self._publish)
        self._shutdown_event = threading.Event()

        will_payload = json.dumps({"online": False, "reason": "connection_lost"})
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_client.will_set(full_topic("status/health"), will_payload, retain=True, qos=1)
        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_message = self._on_message

        signal.signal(signal.SIGTERM, self._handle_shutdown_signal)
        signal.signal(signal.SIGINT, self._handle_shutdown_signal)

    def _publish(self, topic: str, payload: str, retain: bool) -> None:
        self.mqtt_client.publish(topic, payload, retain=retain, qos=1)

    def _publish_state(self) -> None:
        state = {"mode": self.state_machine.mode, "app": self.state_machine.current_app,
                 "user": self.yuvomi_users.current_user}
        self._publish(full_topic("status/state"), json.dumps(state), True)

    def _publish_heartbeat(self) -> None:
        self._publish(full_topic("status/health"), json.dumps({"online": True, "ts": time.time()}), True)

    def _heartbeat_loop(self) -> None:
        while not self._shutdown_event.is_set():
            self._publish_heartbeat()
            self._shutdown_event.wait(HEARTBEAT_INTERVAL_SECONDS)

    def _handle_shutdown_signal(self, signum, frame) -> None:
        self._shutdown_event.set()
        try:
            self._publish(full_topic("status/health"), json.dumps({"online": False, "reason": "clean_shutdown"}), True)
            self.mqtt_client.disconnect()
        except Exception:
            pass
        sys.exit(0)

    def _on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        client.subscribe(full_topic("cmd/#"))
        self._publish_heartbeat()
        self._publish_state()

    def _on_message(self, client, userdata, msg) -> None:
        topic = msg.topic
        payload = msg.payload.decode("utf-8", errors="replace")
        self.yuvomi_users.on_activity()
        sub_topic = topic[len(MQTT_BASE_TOPIC):] if topic.startswith(MQTT_BASE_TOPIC) else topic
        try:
            if sub_topic == "cmd/mode":
                self.state_machine.set_mode(payload)
            elif sub_topic == "cmd/app":
                self.state_machine.set_app(payload)
            elif sub_topic == "cmd/wallmode":
                self.wall_mode.set(payload.strip().lower() == "on")
            elif sub_topic == "cmd/button/map":
                self.button_mapper.on_config_message(payload)
            elif sub_topic == "cmd/user":
                if ":" in payload:
                    username, password = payload.split(":", 1)
                    self.yuvomi_users.switch_user(username, password)
        except Exception:
            log.exception("Fehler bei Verarbeitung von %s", topic)

    def run(self) -> None:
        self.mqtt_client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=60)
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        self.mqtt_client.loop_forever()


if __name__ == "__main__":
    Supervisor().run()
