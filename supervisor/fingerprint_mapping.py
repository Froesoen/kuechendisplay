"""fingerprint_mapping.py - Fingerprint-ID-Zuordnung fuer Kuechendisplay mit
Familienplaner.

Ordnet Template-IDs des GROW R503 (Kapazitaet 200, IDs 0-199) einzelnen
Familienmitgliedern zu. Je 10 IDs reserviert pro Person.

Hinweis: Namen sind fuer das oeffentliche Repository anonymisiert
(person_a-person_d). Auf dem produktiven Geraet durch echte Namen ersetzen,
konsistent mit config.py (INDIVIDUAL_USER_CREDENTIALS)."""

FINGER_MAP = {
    "person_a": range(0, 10),   # Elternteil 1 - faellt auf Familie-Login zurueck
    "person_b": range(10, 20),  # Elternteil 2 - faellt auf Familie-Login zurueck
    "person_c": range(20, 30),  # Kind 1 - individueller Login
    "person_d": range(30, 40),  # Kind 2 - individueller Login
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
