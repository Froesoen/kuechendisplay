"""
state.py - Zustandsmodell des Kuechendisplays.

Trennt die frueher in einem einzigen 'mode'-Feld vermischten Dimensionen
(Anzeigezustand, App, Nutzer, Wall Mode, Display-Power, Kindersicherung) in
unabhaengige, einzeln aenderbare Felder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class DisplayState:
    display_power: str = "on"     # on | off
    display_mode: str = "app"     # app | slideshow
    active_app: str = "yuvomi"    # yuvomi | nodered | custom:<url>
    active_user: str = "Familie"  # Familie | person_c | person_d
    wall_mode: bool = False
    child_lock: bool = False      # Kindersicherung: sperrt Taster/Fingerprint/Touch

    def as_dict(self) -> dict:
        return {
            "display_power": self.display_power,
            "display_mode": self.display_mode,
            "active_app": self.active_app,
            "active_user": self.active_user,
            "wall_mode": self.wall_mode,
            "child_lock": self.child_lock,
        }


@dataclass
class StateStore:
    """Haelt den DisplayState und benachrichtigt bei jeder Aenderung."""

    on_change: Optional[Callable[[], None]] = None
    state: DisplayState = field(default_factory=DisplayState)

    def _notify(self) -> None:
        if self.on_change:
            self.on_change()

    def update(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if not hasattr(self.state, key):
                raise ValueError(f"Unbekanntes State-Feld: {key}")
            setattr(self.state, key, value)
        self._notify()
