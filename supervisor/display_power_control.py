#!/usr/bin/env python3
"""display_power_control.py - Physische Display-Ein/Ausschaltung per wlopm.

Eigener Prozess (statt Teil des Supervisors), weil 'wlopm' Zugriff auf
den Wayland-Socket der grafischen Sitzung braucht - der systemd-Supervisor
hat das nicht. Gestartet ueber ~/.config/labwc/autostart."""

from __future__ import annotations

import socket
import subprocess
import time

import paho.mqtt.client as mqtt

MQTT_BROKER_HOST = "mqtt"
MQTT_BROKER_PORT = 1883
MQTT_BASE_TOPIC = "display/kueche/"
MQTT_CONNECT_RETRY_DELAY_SECONDS = 5

WLOPM_OUTPUT_NAME = "HDMI-A-1"  # verifiziert

_state = {"on": True}


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


def set_power(powered_on: bool) -> None:
    flag = "--on" if powered_on else "--off"
    try:
        subprocess.run(["wlopm", flag, WLOPM_OUTPUT_NAME], check=True, timeout=5)
        _state["on"] = powered_on
        print(f"Display-Power {'an' if powered_on else 'aus'} ({WLOPM_OUTPUT_NAME})")
    except Exception as exc:  # noqa: BLE001
        print(f"wlopm-Aufruf fehlgeschlagen: {exc}")


def on_connect(client, userdata, flags, rc, properties=None) -> None:
    client.subscribe(full_topic("cmd/display/power"))


def on_message(client, userdata, msg) -> None:
    sub_topic = msg.topic[len(MQTT_BASE_TOPIC):] if msg.topic.startswith(MQTT_BASE_TOPIC) else msg.topic
    if sub_topic != "cmd/display/power":
        return
    payload = msg.payload.decode("utf-8", errors="replace").strip().lower()
    if payload == "toggle":
        set_power(not _state["on"])
    else:
        set_power(payload == "on")


def main() -> None:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    connect_with_retry(client, MQTT_BROKER_HOST, MQTT_BROKER_PORT)
    client.loop_forever()


if __name__ == "__main__":
    main()
