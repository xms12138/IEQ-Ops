"""sensing/ingest — MQTT → calibrated sensor_readings writer.

The bridge from the Arduino MKR1010 sensor node to the rest of the system. Subscribes to
the Mosquitto broker, calibrates each raw JSON frame (sensing.calibration), and appends a
row to sensor_readings (sensing.history.record_reading) — the SAME table read_sensors reads
under sensor_source=='hardware' and the Q&A butler queries for statistics. This is the only
writer of real readings; on the exhibit it replaces ops/sampler.py (the firmware publishes
every 5 s, a denser series than the sampler produced). No LLM here.

    python -m sensing.ingest        # runs forever; Ctrl-C to stop
"""

from __future__ import annotations

import json
from typing import Any

import paho.mqtt.client as mqtt

from core.config import get_settings
from core.logging import configure_logging, get_logger
from mcp_servers.ticket.server import init_schema
from sensing.calibration import calibrate
from sensing.history import record_reading

log = get_logger("ingest")


def _on_connect(client: mqtt.Client, _userdata: Any, _flags: Any, reason: Any, _props: Any) -> None:
    """(Re)subscribe on every (re)connect so a broker restart re-establishes the feed."""
    topic = get_settings().mqtt_topic
    client.subscribe(topic)
    log.info("ingest_connected", topic=topic, reason=str(reason))


def _on_message(_client: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
    """One raw frame → calibrate → one sensor_readings row. A malformed frame is logged and
    dropped (never crashes the loop), so one bad publish cannot take the feed down."""
    try:
        frame = json.loads(msg.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.warning("ingest_bad_frame", error=str(exc))
        return
    if not isinstance(frame, dict):
        log.warning("ingest_bad_frame", error="payload is not a JSON object")
        return
    reading = calibrate(frame)
    record_reading(reading)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    init_schema()  # ensure sensor_readings exists before the first frame
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = _on_connect
    client.on_message = _on_message
    log.info("ingest_start", host=settings.mqtt_host, port=settings.mqtt_port)
    client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=60)
    try:
        client.loop_forever()  # blocks; handles reconnects internally
    except (KeyboardInterrupt, SystemExit):
        log.info("ingest_stop")
        client.disconnect()
