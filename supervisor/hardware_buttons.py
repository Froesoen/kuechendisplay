"""hardware_buttons.py - GPIO-Ansteuerung der 4 physischen Taster mit
Unterscheidung kurzer/langer Tastendruck."""

from __future__ import annotations

import logging
from time import monotonic
from typing import Callable, Iterable

from gpiozero import Button

from config import BUTTON_GPIO_PINS, BUTTON_PHYSICAL_PINS, LONG_PRESS_THRESHOLD_SECONDS

log = logging.getLogger("supervisor.hardware_buttons")


class HardwareButtons:
    def __init__(
        self,
        on_event: Callable[[int, str], None],
        active_buttons: Iterable[int] = (1, 2, 3, 4),
    ) -> None:
        self.on_event = on_event
        self._press_start: dict[int, float] = {}
        self._buttons: dict[int, Button] = {}

        for nr in active_buttons:
            pin = BUTTON_GPIO_PINS[nr]
            button = Button(pin, pull_up=True)
            button.when_pressed = self._make_press_handler(nr)
            button.when_released = self._make_release_handler(nr)
            self._buttons[nr] = button
            log.info(
                "Taster %s initialisiert: GPIO%s (physischer Pin %s)",
                nr, pin, BUTTON_PHYSICAL_PINS[nr],
            )

    def _make_press_handler(self, button_nr: int) -> Callable[[], None]:
        def _on_pressed() -> None:
            self._press_start[button_nr] = monotonic()
        return _on_pressed

    def _make_release_handler(self, button_nr: int) -> Callable[[], None]:
        def _on_released() -> None:
            start = self._press_start.pop(button_nr, None)
            if start is None:
                return
            duration = monotonic() - start
            press_type = "long" if duration >= LONG_PRESS_THRESHOLD_SECONDS else "short"
            self.on_event(button_nr, press_type)
        return _on_released
