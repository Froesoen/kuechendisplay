"""hardware_fingerprint.py - Fingerabdruck-Erkennung (GROW R503) via GPIO4-
WAKEUP-Trigger, kapazitiv geschalteter VCC (BC327-High-Side-Transistor an
GPIO27) und dem Rohprotokoll-Befehl AutoIdentify (0x32).

Ablauf pro Erkennung:
  WAKEUP faellt (Finger beruehrt den Sensor - die Touch-Power-Versorgung
  (weisse Ader) haengt IMMER dauerhaft an 3,3V, nur die Haupt-VCC (rote
  Ader) wird ueber den Transistor geschaltet, siehe docs/hardware.md)
    -> Kindersicherung aktiv? -> ja: Sensor bleibt stromlos, nur Notify
    -> Mindestabschaltzeit (FINGERPRINT_POWER_MIN_OFF_SECONDS) noch nicht
       erreicht? -> WAKEUP wird ignoriert (Schutz lt. R503-Datenblatt)
    -> GPIO27 auf LOW (BC327 leitet, Sensor-VCC an)
    -> FINGERPRINT_POWER_ON_DELAY_SECONDS warten (Sensor-Bootzeit lt.
       Datenblatt ca. 50ms)
    -> Verbindung oeffnen, verify_password()
    -> auto_identify() (Sensor bricht intern nach ca. 10s ohne Finger von
       selbst ab, siehe R503-Datenblatt zu AutoIdentify/0x32)
    -> Template-ID -> Name (config.FINGERPRINT_MAPPING)
    -> Person mit hinterlegten individuellen Zugangsdaten -> individueller Login
    -> sonst (kein Match oder fehlende Zugangsdaten) -> Familie
    -> Verbindung schliessen, GPIO27 auf HIGH (Sensor-VCC aus)
"""

from __future__ import annotations

import logging
import struct
import threading
import time
from typing import Callable, Optional

import serial
import adafruit_fingerprint
from gpiozero import Button, OutputDevice

from config import (
    FINGERPRINT_WAKEUP_GPIO,
    FINGERPRINT_POWER_GPIO,
    FINGERPRINT_POWER_ON_DELAY_SECONDS,
    FINGERPRINT_POWER_MIN_OFF_SECONDS,
    FINGERPRINT_UART_PORT,
    FINGERPRINT_UART_BAUDRATE,
    AUTOIDENTIFY_SECURITY_LEVEL,
    AUTOIDENTIFY_START_POS,
    AUTOIDENTIFY_END_POS,
    AUTOIDENTIFY_RETURN_KEY_STEPS,
    AUTOIDENTIFY_SEARCH_ERROR_RETRIES,
    INDIVIDUAL_USER_CREDENTIALS,
    FINGERPRINT_MAPPING,
)

log = logging.getLogger("supervisor.hardware_fingerprint")

HEADER = b"\xEF\x01"
DEFAULT_ADDRESS = b"\xFF\xFF\xFF\xFF"
PROTOCOL_READ_TIMEOUT_SECONDS = 12.0


def _checksum(pid: int, length_bytes: bytes, content: bytes) -> int:
    return (pid + sum(length_bytes) + sum(content)) & 0xFFFF


def build_auto_identify_packet(
    security_level: int,
    start_pos: int,
    end_pos: int,
    return_key_steps: int,
    search_error_retries: int,
    address: bytes = DEFAULT_ADDRESS,
) -> bytes:
    content = bytes(
        [0x32, security_level, start_pos, end_pos, return_key_steps, search_error_retries]
    )
    length_bytes = struct.pack(">H", len(content) + 2)
    checksum = _checksum(0x01, length_bytes, content)
    return HEADER + address + bytes([0x01]) + length_bytes + content + struct.pack(">H", checksum)


def read_ack_packet(uart: serial.Serial, deadline: float) -> dict:
    preamble = b""
    while len(preamble) < 9:
        if time.time() > deadline:
            raise TimeoutError("Kein Antwortpaket vom Sensor erhalten (Preamble)")
        chunk = uart.read(9 - len(preamble))
        if chunk:
            preamble += chunk

    header, pid = preamble[0:2], preamble[6]
    if header != HEADER:
        raise ValueError(f"Unerwarteter Paket-Header: {header!r}")
    length = struct.unpack(">H", preamble[7:9])[0]

    body = b""
    while len(body) < length:
        if time.time() > deadline:
            raise TimeoutError("Kein vollstaendiges Antwortpaket erhalten (Body)")
        chunk = uart.read(length - len(body))
        if chunk:
            body += chunk

    result = {"pid": pid, "confirmation_code": body[0]}
    if length == 8:
        result["step"] = body[1]
        result["template_id"] = struct.unpack(">H", body[2:4])[0]
        result["score"] = struct.unpack(">H", body[4:6])[0]
    return result


def auto_identify(uart: serial.Serial, **kwargs) -> dict:
    packet = build_auto_identify_packet(**kwargs)
    uart.write(packet)
    deadline = time.time() + PROTOCOL_READ_TIMEOUT_SECONDS
    while True:
        ack = read_ack_packet(uart, deadline)
        step = ack.get("step")
        if step == 3 or step is None:
            return ack


class FingerprintController:
    def __init__(
        self,
        on_identified: Callable[[Optional[str]], None],
        is_child_lock_active: Callable[[], bool] = lambda: False,
        on_child_lock_blocked: Callable[[], None] = lambda: None,
    ) -> None:
        self.on_identified = on_identified
        self.is_child_lock_active = is_child_lock_active
        self.on_child_lock_blocked = on_child_lock_blocked
        self._busy = threading.Lock()

        # Aktiv LOW: initial_value=False -> physisch HIGH -> BC327 gesperrt,
        # Sensor bleibt beim Start der Software sicher stromlos.
        self._power = OutputDevice(FINGERPRINT_POWER_GPIO, active_high=False, initial_value=False)
        self._last_power_off_monotonic = time.monotonic() - FINGERPRINT_POWER_MIN_OFF_SECONDS

        self._wakeup = Button(FINGERPRINT_WAKEUP_GPIO, pull_up=True)
        self._wakeup.when_pressed = self._on_wakeup

    def _on_wakeup(self) -> None:
        if self.is_child_lock_active():
            log.info("WAKEUP waehrend aktiver Kindersicherung ignoriert - Sensor bleibt stromlos")
            self.on_child_lock_blocked()
            return

        since_off = time.monotonic() - self._last_power_off_monotonic
        if since_off < FINGERPRINT_POWER_MIN_OFF_SECONDS:
            log.debug(
                "WAKEUP ignoriert - Mindestabschaltzeit von %.1fs noch nicht erreicht (erst %.1fs vergangen)",
                FINGERPRINT_POWER_MIN_OFF_SECONDS, since_off,
            )
            return

        if not self._busy.acquire(blocking=False):
            log.warning("Fingerabdruck-Erkennung laeuft bereits, WAKEUP ignoriert")
            return
        threading.Thread(target=self._run_identification, daemon=True).start()

    def _run_identification(self) -> None:
        try:
            self._identify_once()
        except Exception:
            log.exception("Fehler bei Fingerabdruck-Erkennung")
        finally:
            self._power.off()
            self._last_power_off_monotonic = time.monotonic()
            self._busy.release()

    def _identify_once(self) -> None:
        self._power.on()
        time.sleep(FINGERPRINT_POWER_ON_DELAY_SECONDS)

        uart = serial.Serial(FINGERPRINT_UART_PORT, baudrate=FINGERPRINT_UART_BAUDRATE, timeout=2)
        try:
            finger = adafruit_fingerprint.Adafruit_Fingerprint(uart)
            if finger.verify_password() != adafruit_fingerprint.OK:
                log.error("Passwort-Verifikation gegen den Sensor fehlgeschlagen")
                return

            result = auto_identify(
                uart,
                security_level=AUTOIDENTIFY_SECURITY_LEVEL,
                start_pos=AUTOIDENTIFY_START_POS,
                end_pos=AUTOIDENTIFY_END_POS,
                return_key_steps=AUTOIDENTIFY_RETURN_KEY_STEPS,
                search_error_retries=AUTOIDENTIFY_SEARCH_ERROR_RETRIES,
            )

            if result["confirmation_code"] != 0x00:
                log.info("Kein Match / Fehler: Code 0x%02X", result["confirmation_code"])
                self.on_identified(None)
                return

            template_id = result["template_id"]
            name = FINGERPRINT_MAPPING.get_user_for_id(template_id)
            log.info("Finger erkannt: Template-ID %s -> %s (Score %s)", template_id, name, result["score"])
            self.on_identified(name)
        finally:
            uart.close()


def resolve_login_target(name: Optional[str]) -> Optional[tuple[str, str, str]]:
    if name not in INDIVIDUAL_USER_CREDENTIALS:
        return None

    username, password = INDIVIDUAL_USER_CREDENTIALS[name]
    if not username or not password:
        log.warning(
            "Fuer '%s' sind noch keine Zugangsdaten in secrets.json hinterlegt - "
            "falle auf Familie zurueck", name,
        )
        return None

    return name, username, password
