"""MonitorAgent — node `monitor.scan` (ops/llm_routing.md #1).

Reads every sensor via mcp-sensor-server, judges against fixed thresholds, and
emits the LOCKED AnomalyRecord schema (Hard Constraint #10) — never free-text
diagnosis. On an anomaly it opens an incident via mcp-ticket-server.

Routing: LOCAL tier (Qwen3-8B in prod; dev override → deepseek-v4-flash). A
deterministic Python threshold check backs the LLM up: if the model is
unavailable or returns malformed JSON, the rules in sensing/thresholds.py
produce the same AnomalyRecord, so the monitoring loop never silently stalls
(ops/llm_routing.md #1 fallback).
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from pydantic import ValidationError

from agents.prompt_loader import load_prompt
from core.logging import get_logger
from core.router import Router, RouterExhausted
from core.state import AnomalyRecord, IncidentStatus, MainIncidentState
from mcp_servers.client import call_tool
from mcp_servers.sensor.server import mcp as sensor_server
from mcp_servers.ticket.server import mcp as ticket_server
from sensing.override import is_live_world
from sensing.thresholds import THRESHOLDS, rules_text

log = get_logger("monitor")


class MonitorAgent:
    def __init__(self, router: Router | None = None) -> None:
        self.router = router or Router()
        self._template = load_prompt("monitor")

    def run(self, state: MainIncidentState) -> dict[str, Any]:
        readings = call_tool(sensor_server, "read_sensors")
        self._reconcile_recovered(readings)
        record = self._judge(readings)
        if not record.anomaly:
            log.info("monitor_no_anomaly", **readings)
            return {"anomaly": record, "status": IncidentStatus.CLOSED}
        existing = call_tool(ticket_server, "active_incident_for_sensor", sensor=record.sensor)
        if existing:
            # Dedup: this sensor already has an unresolved incident, so a persistent
            # anomaly does not spawn a new one each scan. No incident_id set → END.
            log.info(
                "monitor_anomaly_suppressed",
                sensor=record.sensor,
                value=record.value,
                existing=existing,
            )
            return {"anomaly": record}
        incident_id = call_tool(
            ticket_server,
            "create_incident",
            sensor=record.sensor,
            value=record.value,
            rule_violated=record.rule_violated,
        )
        structlog.contextvars.bind_contextvars(incident_id=incident_id)
        log.info("monitor_anomaly", sensor=record.sensor, value=record.value)
        return {"anomaly": record, "incident_id": incident_id, "status": IncidentStatus.PLANNING}

    def _reconcile_recovered(self, readings: dict[str, float]) -> None:
        """Live-world only: close any active incident whose sensor has returned to band — the
        real world recovered on its own (a window opened, the room emptied). The graph never
        runs an actuator on the live exhibit (advisory path), so recovery is the only way a
        real incident closes. Gated on is_live_world(): in sim/injection the Verifier closes
        the loop, and an injected demo reads the simulator (untouched sensors sit in band),
        so without the gate it would wrongly close a real incident on another sensor."""
        if not is_live_world():
            return
        for sensor, t in THRESHOLDS.items():
            existing = call_tool(ticket_server, "active_incident_for_sensor", sensor=sensor)
            if not existing:
                continue
            value = readings.get(sensor)
            if value is None or self._violated(value, t):
                continue
            call_tool(
                ticket_server,
                "update_incident",
                incident_id=existing,
                status=IncidentStatus.CLOSED.value,
                action_taken=f"auto-closed: {sensor} back in band ({value} {t['unit']})",
            )
            log.info("monitor_recovered", sensor=sensor, value=value, incident_id=existing)

    @staticmethod
    def _violated(value: float, t: Any) -> bool:
        """True if `value` breaches threshold `t` (above high or below low)."""
        if t["high"] is not None and value > t["high"]:
            return True
        return bool(t["low"] is not None and value < t["low"])

    def _judge(self, readings: dict[str, float]) -> AnomalyRecord:
        prompt = self._template.safe_substitute(rules=rules_text(), readings=json.dumps(readings))
        try:
            raw = self.router.complete(
                "monitor.scan",
                [{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            return AnomalyRecord.model_validate_json(raw)
        except (RouterExhausted, ValidationError, ValueError) as exc:
            log.warning("monitor_llm_fallback", error=str(exc))
            return self._threshold_fallback(readings)

    def _threshold_fallback(self, readings: dict[str, float]) -> AnomalyRecord:
        """Deterministic backstop — the source of truth the LLM must agree with."""
        for sensor, t in THRESHOLDS.items():
            value = readings.get(sensor)
            if value is None:
                continue
            if t["high"] is not None and value > t["high"]:
                return AnomalyRecord(
                    anomaly=True, sensor=sensor, value=value, rule_violated=t["rule"]
                )
            if t["low"] is not None and value < t["low"]:
                return AnomalyRecord(
                    anomaly=True, sensor=sensor, value=value, rule_violated=t["rule"]
                )
        return AnomalyRecord(
            anomaly=False, sensor="co2", value=readings.get("co2", 0.0), rule_violated="none"
        )
