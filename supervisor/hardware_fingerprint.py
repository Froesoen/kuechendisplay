"""hardware_fingerprint.py - Fingerabdruck-Erkennung (GROW R503) via GPIO4-
WAKEUP-Trigger und dem Rohprotokoll-Befehl AutoIdentify (0x32).

Ablauf pro Erkennung:
  WAKEUP faellt (Finger aufgelegt)
    -> Verbindung oeffnen, verify_password()
    -> auto_identify()
    -> Template-ID -> Name (config.FINGERPRINT_MAPPING)
    -> Person mit hinterlegten individuellen Zugangsdaten -> individueller Login
    -> sonst (kein Match oder fehlende Zugangsdaten) -> Familie
    -> Verbindung schliessen
"""

from __future__ import annotations

import logging
import struct
import threading
import time
from typing import Callable, Optional

import serial
import adafruit_fingerprint
from gpiozero import Button

from config import (
    FINGERPRINT_WAKEUP_GPIO,
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
    def __init__(self, on_identified: Callable[[Optional[str]], None]) -> None:
        self.on_identified = on_identified
        self._busy = threading.Lock()

        self._wakeup = Button(FINGERPRINT_WAKEUP_GPIO, pull_up=True)
        self._wakeup.when_pressed = self._on_wakeup

    def _on_wakeup(self) -> None:
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
            self._busy.release()

    def _identify_once(self) -> None:
        uart = serial.Serial(FINGERPRINT_UART_PORT, baudrate=FINGERPRINT_UART_BAUDRATE, timeout=2)
        try:
            time.sleep(0.1)
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
