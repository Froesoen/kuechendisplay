"""sensor_core.py
Low-Level-Wrapper um adafruit_fingerprint fuer den GROW R503.

Kapselt Verbindungsaufbau, Status/Belegung, Enrollment mit Bugfix,
Identifikation, Export/Import einzelner Templates, Passwortaenderung.

Hinweis zur Passwortaenderung: adafruit_fingerprint bietet keine
oeffentliche set_password()-Methode. Der R503 unterstuetzt PS_SetPwd
(0x12) auf Protokollebene - deshalb wird hier bewusst auf die internen
Hilfsmethoden der Bibliothek zurueckgegriffen."""

import struct
import time

import serial
import adafruit_fingerprint

from config import UART_PORT, UART_BAUDRATE, get_sensor_password
from logging_setup import get_logger

logger = get_logger(__name__)

_SET_PASSWORD_CMD = 0x12


class SensorError(Exception):
    """Wird bei jedem Fehler in der Kommunikation mit dem Sensor ausgeloest."""


class FingerprintSensor:
    def __init__(self, port: str = UART_PORT, baudrate: int = UART_BAUDRATE,
                 password: int = None):
        self.port = port
        self.baudrate = baudrate
        self.password = password if password is not None else get_sensor_password()
        self.finger = None

    def connect(self):
        try:
            uart = serial.Serial(self.port, baudrate=self.baudrate, timeout=2)
        except serial.SerialException as exc:
            raise SensorError(f"UART {self.port} konnte nicht geoeffnet werden: {exc}") from exc

        time.sleep(0.1)
        pw_bytes = tuple(struct.pack(">I", self.password))

        try:
            finger = adafruit_fingerprint.Adafruit_Fingerprint(uart, passwd=pw_bytes)
        except RuntimeError as exc:
            raise SensorError(
                "Verbindung zum Sensor fehlgeschlagen. Moegliche Ursachen: "
                "falsches Passwort in sensor_config.json, falsche Verkabelung "
                f"oder falscher Port ({self.port})."
            ) from exc

        if finger.verify_password() != adafruit_fingerprint.OK:
            raise SensorError(
                "Passwort-Verifikation gegen den Sensor fehlgeschlagen. "
                "Ist das in sensor_config.json hinterlegte Passwort korrekt?"
            )

        self.finger = finger
        logger.info("Verbindung zum Sensor hergestellt (Port %s).", self.port)
        return finger

    def disconnect(self):
        if self.finger is not None:
            try:
                self.finger.close_uart()
            except Exception:  # pylint: disable=broad-except
                pass
            self.finger = None
            logger.info("Verbindung zum Sensor getrennt.")

    def _require_connection(self):
        if self.finger is None:
            raise SensorError("Nicht mit dem Sensor verbunden.")

    def status(self) -> dict:
        self._require_connection()
        f = self.finger
        if f.read_sysparam() != adafruit_fingerprint.OK:
            raise SensorError("Konnte Systemparameter nicht lesen.")
        if f.count_templates() != adafruit_fingerprint.OK:
            raise SensorError("Konnte Templateanzahl nicht lesen.")
        return {
            "library_size": f.library_size,
            "template_count": f.template_count,
            "security_level": f.security_level,
        }

    def used_ids(self) -> list:
        self._require_connection()
        f = self.finger
        if f.read_templates() != adafruit_fingerprint.OK:
            raise SensorError("Konnte Templateliste nicht lesen.")
        return list(f.templates)

    def is_occupied(self, template_id: int) -> bool:
        return template_id in self.used_ids()

    def enroll(self, template_id: int, overwrite: bool = False,
               progress_cb=None, cancel_event=None) -> bool:
        self._require_connection()
        f = self.finger

        def report(msg):
            logger.info(msg)
            if progress_cb:
                progress_cb(msg)

        def check_cancel():
            if cancel_event is not None and cancel_event.is_set():
                raise SensorError("Vorgang durch Benutzer abgebrochen.")

        if self.is_occupied(template_id):
            if not overwrite:
                raise SensorError(
                    f"ID {template_id} ist bereits belegt. Zum Ersetzen muss "
                    "overwrite=True gesetzt werden."
                )
            report(f"ID {template_id} ist belegt - loesche vorhandenes Template...")
            if f.delete_model(template_id) != adafruit_fingerprint.OK:
                raise SensorError(
                    f"Vorhandenes Template auf ID {template_id} konnte nicht "
                    "geloescht werden. Enrollment abgebrochen, Daten unveraendert."
                )

        report("Finger auflegen (1. Aufnahme)...")
        while f.get_image() != adafruit_fingerprint.OK:
            check_cancel()
            time.sleep(0.05)

        if f.image_2_tz(1) != adafruit_fingerprint.OK:
            raise SensorError("Fehler bei Merkmalserzeugung (1. Aufnahme).")

        report("Finger abheben...")
        while f.get_image() != adafruit_fingerprint.NOFINGER:
            check_cancel()
            time.sleep(0.05)

        report("Finger erneut auflegen (2. Aufnahme, gleicher Finger)...")
        while f.get_image() != adafruit_fingerprint.OK:
            check_cancel()
            time.sleep(0.05)

        if f.image_2_tz(2) != adafruit_fingerprint.OK:
            raise SensorError("Fehler bei Merkmalserzeugung (2. Aufnahme).")

        report("Fuehre Merkmale zusammen...")
        if f.create_model() != adafruit_fingerprint.OK:
            raise SensorError(
                "Zusammenfuehren fehlgeschlagen (evtl. zwei verschiedene "
                "Finger benutzt?)."
            )

        report(f"Speichere Template auf ID {template_id}...")
        if f.store_model(template_id) != adafruit_fingerprint.OK:
            raise SensorError("Speichern des Templates fehlgeschlagen.")

        report("Erfolgreich gespeichert.")
        logger.info("Enrollment auf ID %s abgeschlossen (overwrite=%s).", template_id, overwrite)
        return True

    def delete(self, template_id: int) -> bool:
        self._require_connection()
        if self.finger.delete_model(template_id) != adafruit_fingerprint.OK:
            raise SensorError(f"Loeschen von ID {template_id} fehlgeschlagen (evtl. leer).")
        logger.info("Template ID %s geloescht.", template_id)
        return True

    def identify(self, timeout: float = None, progress_cb=None, cancel_event=None):
        self._require_connection()
        f = self.finger

        def report(msg):
            if progress_cb:
                progress_cb(msg)

        def check_cancel():
            if cancel_event is not None and cancel_event.is_set():
                raise SensorError("Vorgang durch Benutzer abgebrochen.")

        report("Finger auflegen...")
        start = time.time()
        while f.get_image() != adafruit_fingerprint.OK:
            check_cancel()
            if timeout and (time.time() - start) > timeout:
                raise SensorError("Zeitueberschreitung beim Warten auf Finger.")
            time.sleep(0.05)

        if f.image_2_tz(1) != adafruit_fingerprint.OK:
            raise SensorError("Konnte kein Merkmal erzeugen (Finger schlecht aufgelegt?).")

        if f.finger_search() != adafruit_fingerprint.OK:
            return None

        return {"id": f.finger_id, "confidence": f.confidence}

    def export_template(self, template_id: int) -> bytes:
        self._require_connection()
        f = self.finger
        if f.load_model(template_id) != adafruit_fingerprint.OK:
            raise SensorError(f"Template {template_id} konnte nicht geladen werden.")
        data = f.get_fpdata(sensorbuffer="char", slot=1)
        if not data:
            raise SensorError(f"Template {template_id} konnte nicht ausgelesen werden.")
        return bytes(data)

    def import_template(self, template_id: int, raw_bytes: bytes, overwrite: bool = False) -> bool:
        self._require_connection()
        f = self.finger

        if self.is_occupied(template_id):
            if not overwrite:
                raise SensorError(f"ID {template_id} ist auf dem Ziel-Sensor bereits belegt.")
            if f.delete_model(template_id) != adafruit_fingerprint.OK:
                raise SensorError(f"Vorhandenes Template {template_id} konnte nicht geloescht werden.")

        ok = f.send_fpdata(list(raw_bytes), sensorbuffer="char", slot=1)
        if not ok:
            raise SensorError(f"Uebertragung der Templatedaten fuer ID {template_id} fehlgeschlagen.")
        if f.store_model(template_id) != adafruit_fingerprint.OK:
            raise SensorError(f"Speichern des importierten Templates {template_id} fehlgeschlagen.")

        logger.info("Template ID %s importiert (overwrite=%s).", template_id, overwrite)
        return True

    def change_password(self, new_password: int) -> bool:
        self._require_connection()
        f = self.finger

        pw_bytes = list(struct.pack(">I", new_password))
        # pylint: disable=protected-access
        f._send_packet([_SET_PASSWORD_CMD] + pw_bytes)
        response = f._get_packet(12)

        if response[0] != adafruit_fingerprint.OK:
            raise SensorError("Passwortaenderung wurde vom Sensor abgelehnt.")

        f.password = tuple(pw_bytes)
        self.password = new_password

        if f.verify_password() != adafruit_fingerprint.OK:
            raise SensorError(
                "Passwort wurde laut Sensor geaendert, die erneute "
                "Verifikation schlug jedoch fehl. Sensor ggf. neu verbinden "
                "und Passwort in sensor_config.json pruefen."
            )

        logger.info("Sensor-Passwort erfolgreich geaendert (Wert nicht geloggt).")
        return True
