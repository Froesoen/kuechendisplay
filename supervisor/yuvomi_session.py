"""yuvomi_session.py - HTTP-Login/-Logout gegen Yuvomi und Cookie-Uebertragung
in den Chromium-Kiosk."""

from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

import requests

from config import YUVOMI_REQUEST_TIMEOUT_SECONDS, YUVOMI_RETRY_DELAY_SECONDS
from kiosk_controller import KioskController

log = logging.getLogger("supervisor.yuvomi_session")


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
                log.info("Login-Versuch schlaegt fehl, erneuter Versuch in %ss", YUVOMI_RETRY_DELAY_SECONDS)
                time.sleep(YUVOMI_RETRY_DELAY_SECONDS)
                return self.login(username, password, _retry=False)
            log.error("Yuvomi-Login endgueltig fehlgeschlagen nach Retry")
            return False

        if resp.status_code != 200:
            log.error("Yuvomi-Login fehlgeschlagen: %s %s", resp.status_code, resp.text)
            return False

        data = resp.json()
        if data.get("twoFactorRequired"):
            log.error("Yuvomi verlangt 2FA - im Standard-Setup nicht unterstuetzt")
            return False

        self._apply_cookies_to_kiosk()
        self.kiosk.navigate(self.base_url)
        log.info("Yuvomi-Login erfolgreich fuer Nutzer %s", username)
        return True

    def logout(self, _retry: bool = True) -> bool:
        csrf_token = self.session.cookies.get("csrf-token")
        try:
            resp = self.session.post(
                f"{self.base_url}/api/v1/auth/logout",
                headers={"X-CSRF-Token": csrf_token} if csrf_token else {},
                timeout=YUVOMI_REQUEST_TIMEOUT_SECONDS,
            )
        except requests.exceptions.RequestException as exc:
            log.error("Yuvomi-Logout: Netzwerkfehler (%s)", exc)
            if _retry:
                time.sleep(YUVOMI_RETRY_DELAY_SECONDS)
                return self.logout(_retry=False)
            self.session.cookies.clear()
            self.kiosk.clear_browser_cookies()
            return False

        ok = resp.status_code == 200
        if ok:
            log.info("Yuvomi-Logout erfolgreich")
        else:
            log.warning("Yuvomi-Logout mit Status %s (evtl. bereits abgemeldet)", resp.status_code)

        self.session.cookies.clear()
        self.kiosk.clear_browser_cookies()
        return ok

    def _apply_cookies_to_kiosk(self) -> None:
        page_url = f"{self.base_url}/"
        cookies_payload = []
        for cookie in self.session.cookies:
            same_site = "Lax"
            rest = getattr(cookie, "_rest", {}) or {}
            for key, value in rest.items():
                if key.lower() == "samesite" and value:
                    same_site = value
                    break
            cookies_payload.append({
                "name": cookie.name,
                "value": cookie.value,
                "url": page_url,
                "domain": self._real_host,
                "path": cookie.path or "/",
                "secure": False,
                "sameSite": same_site,
                "httpOnly": bool(cookie.has_nonstandard_attr("HttpOnly")) if hasattr(cookie, "has_nonstandard_attr") else False,
            })
        self.kiosk.set_cookies(cookies_payload)
