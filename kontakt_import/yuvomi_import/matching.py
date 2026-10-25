"""Namensabgleich Tabelle <-> yuvomi.

Titel wie 'Oma' oder 'Opa' werden ignoriert. Zwei Kontakte gelten als gleich, wenn ihre Namens-Token
identisch sind oder die Token des einen vollstaendig im anderen enthalten sind (mind. 2 Token),
z. B. 'Oma Brigitte Giese' == 'Brigitte Giese' oder 'Susanne (Susi) Stephan' == 'Susanne Stephan'.
"""
from __future__ import annotations

import re
from typing import Any

TITLE_TOKENS = frozenset({"oma", "opa", "noch", "mama", "papa", "onkel", "tante"})


def name_key(first: str, last: str) -> frozenset[str]:
    tokens = frozenset(re.findall(r"\w+", f"{first} {last}".casefold()))
    return (tokens - TITLE_TOKENS) or tokens


def names_match(a: frozenset[str], b: frozenset[str]) -> bool:
    return a == b or (min(len(a), len(b)) >= 2 and (a <= b or b <= a))


def find_existing(existing: dict[frozenset[str], Any], key: frozenset[str]) -> Any:
    if key in existing:
        return existing[key]
    for k, contact in existing.items():
        if names_match(k, key):
            return contact
    return None
