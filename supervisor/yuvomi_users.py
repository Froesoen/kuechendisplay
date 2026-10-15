"""yuvomi_users.py - Verwaltung des aktiven Yuvomi-Nutzers.

- Lock-Bereich umfasst den GESAMTEN Logout/Login-Ablauf.
- Automatische Wall-Mode-Steuerung: Familie -> an (ausser explizit abgewaehlt), individueller Nutzer -> aus.
- state_store wird per on_wall_mode_change-Callback explizit mitgezogen.
- Der Inaktivitaets-Timeout individueller Nutzer wird NUR durch echte
  Touch-Beruehrungen im Kiosk-Browser (CDP-Polling, siehe
  kiosk_controller.KioskController.get_browser_last_activity_ms) sowie durch
  Nutzerwechsel zurueckgesetzt. MQTT-Nachrichten und Taster zaehlen nicht.
- Jeder Touch wird zusaetzlich ueber on_touch an den Diashow-Timer des
  Supervisors gemeldet.
- LOGOUT_WARNING_LEAD_SECONDS vor dem automatischen Rueckfall auf Familie wird
  einmalig eine Bildschirm-Benachrichtigung ausgeloest (on_notify), die bei
  erneutem Touch sofort wieder zurueckgenommen wird (on_notify_clear).
- logout_individual_user() meldet einen individuellen Nutzer sofort ab
  (z. B. beim Wechsel zur Diashow oder zu einer anderen App).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from config import FAMILIE_USERNAME, FAMILIE_PASSWORD, USER_INACTIVITY_TIMEOUT_SECONDS
from yuvomi_session import YuvomiSessionManager
from kiosk_controller import KioskController, WallModeController

log = logging.getLogger("supervisor.yuvomi_users")

BROWSER_ACTIVITY_POLL_INTERVAL_SECONDS = 5
LOGOUT_WARNING_LEAD_SECONDS = 10


class YuvomiUserManager:
    def __init__(
        self,
        session_manager: YuvomiSessionManager,
        wall_mode: WallModeController,
        kiosk: Optional[KioskController] = None,
        on_wall_mode_change: Optional[Callable[[bool], None]] = None,
        on_change: Optional[Callable[[], None]] = None,
        on_notify: Optional[Callable[[str], None]] = None,
        on_notify_clear: Optional[Callable[[], None]] = None,
        on_touch: Optional[Callable[[], None]] = None,
    ) -> None:
        self.session_manager = session_manager
        self.wall_mode = wall_mode
        self.kiosk = kiosk
        self.on_wall_mode_change = on_wall_mode_change
        self.on_notify = on_notify
        self.on_notify_clear = on_notify_clear
        self.on_touch = on_touch
        self.current_user = FAMILIE_USERNAME
        self.on_change = on_change
        self._last_activity = time.time()
        self._last_seen_browser_activity_ms: Optional[int] = None
        self._pending_logout_warned = False
        self._lock = threading.Lock()
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()

        if self.kiosk is not None:
            self._browser_activity_thread = threading.Thread(
                target=self._browser_activity_loop, daemon=True
            )
            self._browser_activity_thread.start()

    def _notify_change(self) -> None:
        if self.on_change:
            self.on_change()

    def _set_wall_mode(self, enabled: bool) -> None:
        self.wall_mode.set(enabled)
        if self.on_wall_mode_change:
            self.on_wall_mode_change(enabled)
        else:
            self._notify_change()

    def _clear_pending_logout_warning(self) -> None:
        with self._lock:
            was_warned = self._pending_logout_warned
            self._pending_logout_warned = False
        if was_warned and self.on_notify_clear:
            self.on_notify_clear()

    def on_activity(self) -> None:
        with self._lock:
            self._last_activity = time.time()
        self._clear_pending_logout_warning()

    def reset_browser_activity_baseline(self) -> None:
        """Nach Supervisor-initiierter Navigation aufrufen.

        Der naechste gelesene Touch-Zeitstempel zaehlt dann wieder als Aktivitaet.
        """
        self._last_seen_browser_activity_ms = None

    def _browser_activity_loop(self) -> None:
        while True:
            time.sleep(BROWSER_ACTIVITY_POLL_INTERVAL_SECONDS)
            try:
                current_ms = self.kiosk.get_browser_last_activity_ms()
            except Exception:
                log.exception("Browser-Aktivitaet konnte nicht abgefragt werden")
                continue

            # None = noch keine Touch-Beruehrung auf der aktuellen Seite (Wert 0)
            # oder Wert gerade nicht lesbar.
            if current_ms is None:
                continue

            if (
                self._last_seen_browser_activity_ms is None
                or current_ms > self._last_seen_browser_activity_ms
            ):
                self._last_seen_browser_activity_ms = current_ms
                self.on_activity()
                if self.on_touch:
                    self.on_touch()

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

        self._clear_pending_logout_warning()
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
            self._clear_pending_logout_warning()
            self._set_wall_mode(False)
        else:
            self._notify_change()
        return ok

    def logout_individual_user(self, reason: str = "Seitenwechsel") -> bool:
        """Meldet einen individuellen Nutzer sofort ab (Rueckfall auf Familie).

        Liefert False, wenn bereits Familie aktiv war (nichts zu tun).
        """
        with self._lock:
            if self.current_user == FAMILIE_USERNAME:
                return False
            log.info("Direkter Logout von '%s' (%s)", self.current_user, reason)
        self._fallback_to_familie(reason=reason)
        return True

    def _fallback_to_familie(self, reason: str = "Inaktivitaet") -> None:
        with self._lock:
            if self.current_user == FAMILIE_USERNAME:
                return
            previous_user = self.current_user
            log.info(
                "Rueckfall von '%s' zu '%s' (Grund: %s, Inaktivitaets-Timeout %ss)",
                previous_user, FAMILIE_USERNAME, reason, USER_INACTIVITY_TIMEOUT_SECONDS,
            )
            self.session_manager.logout()
            self.session_manager.login(FAMILIE_USERNAME, FAMILIE_PASSWORD)
            self.current_user = FAMILIE_USERNAME
            self._last_activity = time.time()

        self._clear_pending_logout_warning()
        self._set_wall_mode(True)

    def _watchdog_loop(self) -> None:
        while True:
            time.sleep(10)
            with self._lock:
                is_familie = self.current_user == FAMILIE_USERNAME
                idle_seconds = time.time() - self._last_activity
                already_warned = self._pending_logout_warned

            if is_familie:
                continue

            remaining_seconds = USER_INACTIVITY_TIMEOUT_SECONDS - idle_seconds
            if not already_warned and 0 < remaining_seconds <= LOGOUT_WARNING_LEAD_SECONDS:
                with self._lock:
                    self._pending_logout_warned = True
                log.info("Inaktivitaets-Warnung: automatische Abmeldung in %ss", LOGOUT_WARNING_LEAD_SECONDS)
                if self.on_notify:
                    self.on_notify(f"Automatische Abmeldung in {LOGOUT_WARNING_LEAD_SECONDS}s")

            if idle_seconds >= USER_INACTIVITY_TIMEOUT_SECONDS:
                self._fallback_to_familie()
