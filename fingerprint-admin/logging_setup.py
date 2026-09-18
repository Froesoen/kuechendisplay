"""logging_setup.py
Rotierendes Logfile fuer Audit-Trail und Fehlerdiagnose. Passwoerter werden
NIE mitgeloggt, nur der Zeitpunkt der Aenderung."""

import logging
from logging.handlers import RotatingFileHandler

from config import LOG_FILE


def get_logger(name: str = "fingerprint_admin") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=512_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(console_handler)

    return logger
