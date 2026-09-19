"""yuvomi_users.py - Verwaltung des aktiven Yuvomi-Nutzers.

- Lock-Bereich umfasst den GESAMTEN Logout/Login-Ablauf.
- Automatische Wall-Mode-Steuerung: Familie -> an (ausser explizit abgewaehlt), individueller Nutzer -> aus.
- state_store wird per on_wall_mode_change-Callback explizit mitgezogen.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from config import FAMILIE_USERNAME, FAMILIE_PASSWORD, USER_INACTIVITY_TIMEOUT_SECONDS
from yuvomi_session import YuvomiSessionManager
from kiosk_controller import WallModeController

log = logging.getLogger("supervisor.yuvomi_users")


class YuvomiUserManager:
    def __init__(
        self,
        session_manager: YuvomiSessionManager,
        wall_mode: WallModeController,
        on_wall_mode_change: Optional[Callable[[bool], None]] = None,
        on_change: Optional[Callable[[], None]] = None,
    ) -> None:
        self.session_manager = session_manager
        self.wall_mode = wall_mode
        self.on_wall_mode_change = on_wall_mode_change
        self.current_user = FAMILIE_USERNAME
        self.on_change = on_change
        self._last_activity = time.time()
        self._lock = threading.Lock()
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()

    def _notify_change(self) -> None:
        if self.on_change:
            self.on_change()

    def _set_wall_mode(self, enabled: bool) -> None:
        self.wall_mode.set(enabled)
        if self.on_wall_mode_change:
            self.on_wall_mode_change(enabled)
        else:
            self._notify_change()

    def on_activity(self) -> None:
        with self._lock:
            self._last_activity = time.time()

    def ensure_familie_active(self, wall_mode: bool = True) -> None:
        with self._lock:
            previous_user = self.current_user
            if previous_user != FAMILIE_USERNAME:
                log.info("Setze von individuellem Nutzer '%s' zurueck auf '%s'", previous_user, FAMILIE_USERNAME)
            else:
                log.info("Erzwinge frisches Logout+Login als '%s'", FAMILIE_USERNAME)

            self.session_manager.logout()
            self.session_manager.login(FAMILIE_USERNAME, FAMILIE_PASSWORD)
            self.current_user = FAMILIE_USERNAME
            self._last_activity = time.time()

        self._set_wall_mode(wall_mode)

    def switch_user(self, username: str, password: str) -> bool:
        ok = False
        with self._lock:
            if self.current_user == username:
                self._last_activity = time.time()
                return True

            self.session_manager.logout()
            ok = self.session_manager.login(username, password)
            if ok:
                self.current_user = username
                self._last_activity = time.time()
                log.info("Nutzerwechsel zu '%s' erfolgreich", username)
            else:
                log.error("Nutzerwechsel zu '%s' fehlgeschlagen", username)

        if ok:
            self._set_wall_mode(False)
        else:
            self._notify_change()
        return ok

    def _fallback_to_familie(self) -> None:
        with self._lock:
            if self.current_user == FAMILIE_USERNAME:
                return
            previous_user = self.current_user
            log.info(
                "Inaktivitaet %ss ueberschritten - Rueckfall von '%s' zu '%s'",
                USER_INACTIVITY_TIMEOUT_SECONDS, previous_user, FAMILIE_USERNAME,
            )
            self.session_manager.logout()
            self.session_manager.login(FAMILIE_USERNAME, FAMILIE_PASSWORD)
            self.current_user = FAMILIE_USERNAME
            self._last_activity = time.time()

        self._set_wall_mode(True)

    def _watchdog_loop(self) -> None:
        while True:
            time.sleep(10)
            with self._lock:
                is_familie = self.current_user == FAMILIE_USERNAME
                idle_seconds = time.time() - self._last_activity
            if not is_familie and idle_seconds >= USER_INACTIVITY_TIMEOUT_SECONDS:
                self._fallback_to_familie()
