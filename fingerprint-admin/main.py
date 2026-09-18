"""main.py - Einstiegspunkt der Produktivversion.

Aufruf: python3 main.py

Voraussetzungen:
    - UART aktiviert, Sensor verkabelt (siehe docs/hardware.md)
    - fingerprint_mapping.py (liegt lokal in diesem Ordner)
    - Abhaengigkeiten: pyserial, adafruit-circuitpython-fingerprint
    - tkinter (sudo apt install python3-tk falls es fehlt)
"""

from gui_app import main

if __name__ == "__main__":
    main()
