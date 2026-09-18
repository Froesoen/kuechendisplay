"""fingerprint_mapping.py - Fingerprint-ID-Zuordnung (lokale Kopie fuer das
eigenstaendige fingerprint-admin-Tool).

ACHTUNG: Dies ist eine EIGENE Kopie, unabhaengig von
supervisor/fingerprint_mapping.py. Bei Aenderungen an der Namenszuordnung
beide Dateien synchron halten, falls beide Tools denselben Sensor nutzen."""

FINGER_MAP = {
    "person_a": range(0, 10),
    "person_b": range(10, 20),
    "person_c": range(20, 30),
    "person_d": range(30, 40),
}


def get_user_for_id(template_id: int):
    for name, id_range in FINGER_MAP.items():
        if template_id in id_range:
            return name
    return None


def get_ids_for_user(name: str):
    return FINGER_MAP.get(name)


def all_users():
    return list(FINGER_MAP.keys())


if __name__ == "__main__":
    for name, id_range in FINGER_MAP.items():
        print(f"{name}: IDs {id_range.start}-{id_range.stop - 1}")
