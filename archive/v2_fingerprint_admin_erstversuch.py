"""
ARCHIV - erster Test-Ansatz fuer die Fingerabdruck-Verwaltung (CLI)
=====================================================================
Diese Datei wird nicht mehr gepflegt. Die aktive, produktive Version ist
die Tkinter-GUI unter fingerprint-admin/ (main.py / gui_app.py).
=====================================================================

Fingerabdruck-Verwaltungstool - interaktives CLI-Menue zum Einlernen und
Testen von Fingerabdruecken auf dem GROW R503 Sensor.
"""

import sys
import time

import serial
import adafruit_fingerprint

from fingerprint_mapping import FINGER_MAP, get_user_for_id, all_users


UART_PORT = "/dev/serial0"
UART_BAUDRATE = 57600


def connect():
    uart = serial.Serial(UART_PORT, baudrate=UART_BAUDRATE, timeout=2)
    time.sleep(0.1)
    finger = adafruit_fingerprint.Adafruit_Fingerprint(uart)
    if finger.verify_password() != adafruit_fingerprint.OK:
        print("FEHLER: Passwort-Verifikation gegen den Sensor fehlgeschlagen. Abbruch.")
        sys.exit(1)
    return finger


def print_mapping_table():
    print("\nBekannte Zuordnung (ID-Bereich -> Name):")
    for name, id_range in FINGER_MAP.items():
        print(f"  {id_range.start:>3}-{id_range.stop - 1:<3}  {name}")
    print("  40-199  (frei / nicht zugeordnet)")


def ask_template_id(prompt="Template-ID eingeben: "):
    while True:
        raw = input(prompt).strip()
        if not raw.isdigit():
            print("Bitte eine Zahl eingeben.")
            continue
        template_id = int(raw)
        if not (0 <= template_id <= 199):
            print("ID muss zwischen 0 und 199 liegen (Sensorkapazitaet 200).")
            continue
        return template_id


def confirm_id_usage(template_id):
    owner = get_user_for_id(template_id)
    if owner:
        print(f"ID {template_id} gehoert laut Zuordnung zu: {owner}")
    else:
        print(f"ID {template_id} ist keinem Namen zugewiesen (gueltiger Bereich: 0-39).")
    return owner


def enroll(finger, template_id):
    print(f"\n--- Enrollment fuer Template-ID {template_id} ---")
    print("Warte auf Finger (1. Aufnahme)...")
    while finger.get_image() != adafruit_fingerprint.OK:
        pass
    if finger.image_2_tz(1) != adafruit_fingerprint.OK:
        print("Fehler bei Merkmalserzeugung 1. Abgebrochen.")
        return False

    print("Finger jetzt abheben...")
    while finger.get_image() != adafruit_fingerprint.NOFINGER:
        pass

    print("Warte auf Finger (2. Aufnahme, gleicher Finger)...")
    while finger.get_image() != adafruit_fingerprint.OK:
        pass
    if finger.image_2_tz(2) != adafruit_fingerprint.OK:
        print("Fehler bei Merkmalserzeugung 2. Abgebrochen.")
        return False

    if finger.create_model() != adafruit_fingerprint.OK:
        print("Fehler beim Zusammenfuehren. Abgebrochen.")
        return False

    if finger.store_model(template_id) != adafruit_fingerprint.OK:
        print("Fehler beim Speichern. Abgebrochen.")
        return False

    print("Erfolgreich gespeichert!")
    return True


def identify(finger):
    print("\n--- Erkennungstest ---")
    print("Lege einen Finger auf den Sensor...")
    while finger.get_image() != adafruit_fingerprint.OK:
        pass
    if finger.image_2_tz(1) != adafruit_fingerprint.OK:
        print("Konnte kein Merkmal erzeugen.")
        return
    if finger.finger_search() != adafruit_fingerprint.OK:
        print("Kein passender Finger gefunden.")
        return
    template_id = finger.finger_id
    score = finger.confidence
    owner = get_user_for_id(template_id)
    print(f"Finger erkannt! ID {template_id} -> {owner or 'kein Name zugeordnet'} (Score {score})")


def delete_template(finger, template_id):
    if finger.delete_model(template_id) == adafruit_fingerprint.OK:
        print("Geloescht.")
    else:
        print("Fehler beim Loeschen.")


def show_status(finger):
    if finger.read_sysparam() == adafruit_fingerprint.OK:
        print(f"Speicherkapazitaet: {finger.library_size}")
    if finger.count_templates() == adafruit_fingerprint.OK:
        print(f"Belegte Templates: {finger.template_count}")


def menu():
    print_mapping_table()
    finger = connect()

    while True:
        print("\n1) Einlernen 2) Testen 3) Loeschen 4) Status 5) Zuordnung 0) Beenden")
        choice = input("Auswahl: ").strip()

        if choice == "1":
            template_id = ask_template_id()
            confirm_id_usage(template_id)
            if input("Fortfahren? (j/n): ").strip().lower() == "j":
                enroll(finger, template_id)
        elif choice == "2":
            identify(finger)
        elif choice == "3":
            template_id = ask_template_id("ID zum Loeschen: ")
            confirm_id_usage(template_id)
            if input("Wirklich loeschen? (j/n): ").strip().lower() == "j":
                delete_template(finger, template_id)
        elif choice == "4":
            show_status(finger)
        elif choice == "5":
            print_mapping_table()
        elif choice == "0":
            break


if __name__ == "__main__":
    menu()
