#!/usr/bin/env python3
"""notification_overlay.py - Minimales Notification-Overlay als eigener
Wayland-Layer-Shell-Prozess.

WICHTIG:
- Benoetigt 'gir1.2-gtk4layershell-1.0' (GTK4), NICHT 'gir1.2-gtklayershell-0.1' (GTK3).
- Muss mit LD_PRELOAD gestartet werden:
    LD_PRELOAD=/usr/lib/aarch64-linux-gnu/libgtk4-layer-shell.so.0 \\
        python3 ~/kuechendisplay/supervisor/notification_overlay.py
- Laeuft mit System-Python (nicht der venv).
- Gestartet ueber ~/.config/labwc/autostart.
"""

from __future__ import annotations

import socket
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")

from gi.repository import Gtk, GLib, Gtk4LayerShell as LayerShell  # noqa: E402
import paho.mqtt.client as mqtt  # noqa: E402

MQTT_BROKER_HOST = "mqtt"
MQTT_BROKER_PORT = 1883
MQTT_BASE_TOPIC = "display/kueche/"
MQTT_CONNECT_RETRY_DELAY_SECONDS = 5

NOTIFY_DISPLAY_SECONDS: int | None = None
NOTIFY_WIDTH_PX = 960  # verifiziert: haelfte von 1920x1080

CSS_TEMPLATE = """
.notification-label {{
    background-color: rgba(20, 20, 20, 0.9);
    color: white;
    padding: 32px;
    font-size: 32px;
    border-radius: 12px;
    min-width: {width}px;
}}
"""


def full_topic(sub_topic: str) -> str:
    return MQTT_BASE_TOPIC + sub_topic


def connect_with_retry(client: mqtt.Client, host: str, port: int, keepalive: int = 60) -> None:
    while True:
        try:
            client.connect(host, port, keepalive=keepalive)
            return
        except (socket.gaierror, OSError) as exc:
            print(f"MQTT-Verbindung fehlgeschlagen ({exc}) - erneuter Versuch in {MQTT_CONNECT_RETRY_DELAY_SECONDS}s")
            time.sleep(MQTT_CONNECT_RETRY_DELAY_SECONDS)


class NotificationOverlay(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="de.kuechendisplay.notify")
        self.window: Gtk.ApplicationWindow | None = None
        self.label: Gtk.Label | None = None
        self._hide_timeout_id: int | None = None

    def do_activate(self) -> None:
        self.window = Gtk.ApplicationWindow(application=self)

        LayerShell.init_for_window(self.window)
        LayerShell.set_layer(self.window, LayerShell.Layer.OVERLAY)
        LayerShell.set_keyboard_mode(self.window, LayerShell.KeyboardMode.NONE)

        self.label = Gtk.Label(label="")
        self.label.set_wrap(True)
        self.label.set_justify(Gtk.Justification.CENTER)
        self.label.set_halign(Gtk.Align.CENTER)
        self.label.add_css_class("notification-label")
        self.window.set_child(self.label)

        click_gesture = Gtk.GestureClick()
        click_gesture.connect("pressed", self._on_clicked)
        self.window.add_controller(click_gesture)

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS_TEMPLATE.format(width=NOTIFY_WIDTH_PX).encode("utf-8"))
        Gtk.StyleContext.add_provider_for_display(
            self.window.get_display(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.window.set_visible(False)

    def _on_clicked(self, gesture, n_press, x, y) -> None:
        self._hide_now_ui()

    def show_notification(self, text: str) -> None:
        GLib.idle_add(self._show_notification_ui, text)

    def _show_notification_ui(self, text: str) -> bool:
        self.label.set_text(text)
        self.window.set_visible(True)

        if self._hide_timeout_id is not None:
            GLib.source_remove(self._hide_timeout_id)
            self._hide_timeout_id = None

        if NOTIFY_DISPLAY_SECONDS is not None:
            self._hide_timeout_id = GLib.timeout_add_seconds(
                NOTIFY_DISPLAY_SECONDS, self._auto_hide
            )
        return False

    def _auto_hide(self) -> bool:
        self.window.set_visible(False)
        self._hide_timeout_id = None
        return False

    def hide_now(self) -> None:
        GLib.idle_add(self._hide_now_ui)

    def _hide_now_ui(self) -> bool:
        if self.window is not None:
            self.window.set_visible(False)
        if self._hide_timeout_id is not None:
            GLib.source_remove(self._hide_timeout_id)
            self._hide_timeout_id = None
        return False


def main() -> None:
    app = NotificationOverlay()

    def on_connect(client, userdata, flags, rc, properties=None) -> None:
        client.subscribe(full_topic("cmd/notify"))
        client.subscribe(full_topic("cmd/notify/clear"))

    def on_message(client, userdata, msg) -> None:
        sub_topic = msg.topic[len(MQTT_BASE_TOPIC):] if msg.topic.startswith(MQTT_BASE_TOPIC) else msg.topic
        payload = msg.payload.decode("utf-8", errors="replace")
        if sub_topic == "cmd/notify":
            app.show_notification(payload)
        elif sub_topic == "cmd/notify/clear":
            app.hide_now()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    connect_with_retry(client, MQTT_BROKER_HOST, MQTT_BROKER_PORT)
    client.loop_start()

    app.run(None)


if __name__ == "__main__":
    main()
