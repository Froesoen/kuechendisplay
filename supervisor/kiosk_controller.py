"""
kiosk_controller.py - Chromium-Steuerung per Chrome DevTools Protocol (CDP),
Wall-Mode-Steuerung. Display-Power-Steuerung erfolgt NICHT mehr hier,
sondern im separaten Prozess display_power_control.py.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

import pychrome
import requests

from config import CDP_URL, CDP_WAIT_TIMEOUT_SECONDS, CDP_WAIT_POLL_INTERVAL_SECONDS

log = logging.getLogger("supervisor.kiosk")

# Wird per CDP bei jedem Seitenaufbau automatisch injiziert (ueberlebt also
# auch Reloads durch Wall-Mode-Umschaltung), damit der Supervisor echte
# Browser-Nutzung (nicht nur MQTT/Taster) fuer den Inaktivitaets-Timeout
# sehen kann (siehe yuvomi_users._browser_activity_loop).
ACTIVITY_TRACKER_SCRIPT = """
(function() {
  window.__kuechendisplayLastActivity = Date.now();
  ["click", "touchstart", "keydown", "scroll", "mousemove"].forEach(function(evt) {
    window.addEventListener(evt, function() {
      window.__kuechendisplayLastActivity = Date.now();
    }, {passive: true, capture: true});
  });
})();
"""


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
                log.warning(
                    "CDP-Port noch nicht erreichbar (%s) - warte %ss und versuche erneut",
                    exc, CDP_WAIT_POLL_INTERVAL_SECONDS,
                )
                time.sleep(CDP_WAIT_POLL_INTERVAL_SECONDS)
        raise RuntimeError(
            f"Chromium-CDP-Port unter {self.cdp_url} nach {CDP_WAIT_TIMEOUT_SECONDS}s "
            f"immer noch nicht erreichbar - letzter Fehler: {last_error}"
        )

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
        self._install_activity_tracker()
        log.info("Kiosk-Controller an Tab %s angehaengt", self.tab.id)

    def _install_activity_tracker(self) -> None:
        try:
            self.tab.Page.addScriptToEvaluateOnNewDocument(source=ACTIVITY_TRACKER_SCRIPT)
            self.evaluate(ACTIVITY_TRACKER_SCRIPT)
        except Exception:
            log.exception("Activity-Tracker-Skript konnte nicht installiert werden")

    def get_browser_last_activity_ms(self) -> Optional[int]:
        """Liest window.__kuechendisplayLastActivity aus der aktuellen Seite.

        Liefert None, wenn der Wert (noch) nicht gelesen werden kann (z. B.
        waehrend eines Reloads) - der Aufrufer soll das dann einfach beim
        naechsten Poll erneut versuchen.
        """
        try:
            result = self.evaluate("window.__kuechendisplayLastActivity || 0")
            value = result.get("result", {}).get("value")
            return int(value) if value else None
        except Exception:
            log.debug("Browser-Aktivitaet konnte nicht gelesen werden", exc_info=True)
            return None

    def navigate(self, url: str) -> None:
        log.info("Navigiere zu %s", url)
        self.tab.Page.navigate(url=url)

    def evaluate(self, expression: str) -> dict:
        return self.tab.Runtime.evaluate(expression=expression, returnByValue=True)

    def set_local_storage(self, key: str, value: Optional[str]) -> None:
        if value is None:
            expr = f"window.localStorage.removeItem({json.dumps(key)})"
        else:
            expr = f"window.localStorage.setItem({json.dumps(key)}, {json.dumps(value)})"
        self.evaluate(expr)

    def set_cookies(self, cookies: list[dict]) -> None:
        for cookie in cookies:
            try:
                response = self.tab.Network.setCookie(**cookie)
            except Exception:
                log.exception("Network.setCookie hat eine Exception geworfen fuer: %s", cookie)
                continue
            if not response.get("success"):
                log.error(
                    "Chromium hat das Cookie ABGELEHNT (success=false). Payload: %s | Antwort: %s",
                    cookie, response,
                )
            else:
                log.info("Cookie erfolgreich gesetzt: %s (domain=%s)", cookie["name"], cookie["domain"])

    def get_cookies(self, urls: Optional[list[str]] = None) -> list[dict]:
        if urls:
            return self.tab.Network.getCookies(urls=urls).get("cookies", [])
        return self.tab.Network.getCookies().get("cookies", [])

    def clear_browser_cookies(self) -> None:
        self.tab.Network.clearBrowserCookies()
        log.info("Alle Browser-Cookies geloescht")

    def reload(self) -> None:
        self.tab.Page.reload(ignoreCache=False)


WALL_MODE_KEY = "yuvomi-wall-mode"


class WallModeController:
    def __init__(self, kiosk: KioskController) -> None:
        self.kiosk = kiosk

    def set(self, enabled: bool) -> None:
        self.kiosk.set_local_storage(WALL_MODE_KEY, "1" if enabled else None)
        self.kiosk.reload()
        log.info("Wall Mode %s", "aktiviert" if enabled else "deaktiviert")


def apply_display_preferences(kiosk: KioskController, preferences: dict) -> None:
    for key, value in preferences.items():
        kiosk.set_local_storage(key, value)
    kiosk.reload()
    log.info("Display-Praeferenzen gesetzt: %s", preferences)
