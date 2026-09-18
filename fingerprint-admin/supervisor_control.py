"""supervisor_control.py
Steuerung des systemd-Dienstes kuechendisplay-supervisor.service.

/dev/serial0 kann nur von einem Prozess exklusiv geoeffnet werden - deshalb
wird vor Sensorarbeit der Supervisor gestoppt und danach wieder gestartet.
Benoetigt eine sudoers-Freigabe (siehe sudoers_kuechendisplay_fingerprint.txt.example)."""

import subprocess

from logging_setup import get_logger

logger = get_logger(__name__)

SERVICE_NAME = "kuechendisplay-supervisor.service"


class SupervisorControlError(Exception):
    """Wird ausgeloest, wenn systemctl fehlschlaegt oder nicht erreichbar ist."""


def _run(cmd: list, timeout: int = 15) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise SupervisorControlError(f"Befehl nicht gefunden: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SupervisorControlError(f"Zeitueberschreitung bei: {' '.join(cmd)}") from exc


def is_active() -> bool:
    result = _run(["systemctl", "is-active", SERVICE_NAME], timeout=10)
    return result.stdout.strip() == "active"


def status_text() -> str:
    return "aktiv" if is_active() else "gestoppt"


def stop_supervisor() -> None:
    logger.info("Stoppe %s vor Sensorzugriff...", SERVICE_NAME)
    result = _run(["sudo", "-n", "systemctl", "stop", SERVICE_NAME])
    if result.returncode != 0:
        raise SupervisorControlError(
            "Stoppen fehlgeschlagen: "
            f"{result.stderr.strip() or result.stdout.strip()}\n"
            "Ist die sudoers-Freigabe eingerichtet (siehe README)?"
        )
    logger.info("%s gestoppt.", SERVICE_NAME)


def start_supervisor() -> None:
    logger.info("Starte %s wieder...", SERVICE_NAME)
    result = _run(["sudo", "-n", "systemctl", "start", SERVICE_NAME])
    if result.returncode != 0:
        raise SupervisorControlError(
            "Starten fehlgeschlagen: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    logger.info("%s gestartet.", SERVICE_NAME)
