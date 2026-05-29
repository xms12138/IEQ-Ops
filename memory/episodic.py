"""episodic.py — Qdrant-backed incident trajectories (memory tier 1).

What an episode is: one incident the system saw through to a verified end —
anomaly → diagnosis → action → measured outcome. The verifier writes it when the
incident closes (verdict "met" OR "missed": a failed attempt is as instructive as
a success), and the planner recalls similar ones BEFORE planning the next one.

Asymmetric embedding — the key design choice (author-approved 2026-05-29):
a trajectory is recalled at PLANNING time, when the only thing known about the new
incident is its anomaly (sensor, value, rule). So the similarity vector is anchored
on the ANOMALY signature alone — the identical text shape is available both at
write time and at recall time, keeping query and document in one vector space. The
hard-won experience (diagnosis, action taken, verdict) rides in the PAYLOAD: it
never drives similarity, it is what recall hands back to the planner as context.

Hard Constraint #3: this module is the only writer. The verifier node calls
save_trajectory(); it does not upsert itself. Every write and recall emits a
structured audit log line.

Embedding is CPU BGE-M3 (memory/embedding.py) — see that module for the VRAM
rationale. Recall on a cold/empty store returns [] so the planner runs normally.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from pydantic import BaseModel

from core.config import get_settings
from core.logging import get_logger
from core.state import IncidentStatus, MainIncidentState, VerifierVerdict
from memory.embedding import EMBED_DIM, embed

log = get_logger("episodic")

COLLECTION = "ieq_incidents"
DEFAULT_TOP_K = 3

# Fixed namespace → deterministic point id from the incident_id string, so
# re-saving the same incident overwrites rather than duplicating. Qdrant point ids
# must be int or UUID; incident_id is a meaningful string, mapped through uuid5.
_NS = uuid.UUID("1e9c0e7a-3b2d-5f4a-9c1e-000000000001")


class EpisodicCase(BaseModel):
    """One recalled trajectory handed to the planner. The anomaly fields locate it;
    diagnosis / action_taken / verdict are the reusable experience; score is the
    cosine similarity of the anomaly signature."""

    incident_id: str
    room: str
    sensor: str
    value: float
    rule_violated: str
    diagnosis: str
    action_taken: str | None
    verdict: str  # "met" | "missed"
    target_metric: str
    target_value: float
    score: float


def _anomaly_text(sensor: str, value: float, rule_violated: str) -> str:
    """The similarity anchor — identical shape at write time and recall time, so a
    new incident's anomaly lands near past incidents of the same kind."""
    return f"{sensor} anomaly: {rule_violated} (observed {value})"


def _room_of(incident_id: str) -> str:
    # incident_id = I-{date}-{room}-{type}-{time} (mcp-ticket-server). Defensive.
    parts = incident_id.split("-")
    return parts[2] if len(parts) >= 5 else "?"


def _point_id(incident_id: str) -> str:
    return str(uuid.uuid5(_NS, incident_id))


@lru_cache(maxsize=1)
def _client() -> Any:
    from qdrant_client import QdrantClient

    return QdrantClient(url=get_settings().qdrant_url)


def _ensure_collection(client: Any) -> None:
    from qdrant_client.models import Distance, VectorParams

    if not client.collection_exists(COLLECTION):
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
        log.info("episodic_collection_created", collection=COLLECTION, dim=EMBED_DIM)


def save_trajectory(
    state: MainIncidentState, *, verdict: VerifierVerdict, status: IncidentStatus
) -> str | None:
    """Persist a finished incident trajectory (Hard Constraint #3: the verifier node
    routes its write through here, with an audit log). The verifier's just-computed
    verdict/status are passed explicitly because they are not yet in `state` —
    LangGraph merges a node's return only after the node finishes."""
    from qdrant_client.models import PointStruct

    primary = state.primary_result()
    if primary is None or state.anomaly is None or state.incident_id is None:
        log.warning("episodic_skip_incomplete", incident_id=state.incident_id)
        return None

    a = state.anomaly
    eo = primary.expected_outcome
    vector = embed(_anomaly_text(a.sensor, a.value, a.rule_violated))
    payload: dict[str, Any] = {
        "incident_id": state.incident_id,
        "room": _room_of(state.incident_id),
        "sensor": a.sensor,
        "value": a.value,
        "rule_violated": a.rule_violated,
        "diagnosis": primary.diagnosis,
        "action_taken": state.action_taken,
        "verdict": verdict.verdict,
        "delta": verdict.delta,
        "target_metric": eo.target_metric,
        "target_value": eo.target_value,
        "target_time_min": eo.target_time_min,
        "status": status.value,
        "created_at": datetime.now(UTC).isoformat(),
    }
    client = _client()
    _ensure_collection(client)
    pid = _point_id(state.incident_id)
    client.upsert(
        collection_name=COLLECTION,
        points=[PointStruct(id=pid, vector=vector, payload=payload)],
    )
    log.info(  # audit
        "episodic_saved",
        incident_id=state.incident_id,
        verdict=verdict.verdict,
        sensor=a.sensor,
        point_id=pid,
    )
    return state.incident_id


def retrieve_similar(
    sensor: str, value: float, rule_violated: str, top_k: int = DEFAULT_TOP_K
) -> list[EpisodicCase]:
    """Recall the most similar past trajectories by anomaly signature. Called INLINE
    from the planner node (CLAUDE.md: memory retrieval is a deterministic Qdrant
    query, not a LangGraph node). Returns [] on a cold/empty store so the planner
    runs normally in early operation."""
    client = _client()
    if not client.collection_exists(COLLECTION):
        log.info("episodic_recall_empty", reason="no collection yet")
        return []
    q = embed(_anomaly_text(sensor, value, rule_violated))
    hits = client.query_points(
        collection_name=COLLECTION, query=q, limit=top_k, with_payload=True
    ).points
    cases: list[EpisodicCase] = []
    for h in hits:
        pl = h.payload or {}
        cases.append(
            EpisodicCase(
                incident_id=pl["incident_id"],
                room=pl.get("room", "?"),
                sensor=pl["sensor"],
                value=pl["value"],
                rule_violated=pl["rule_violated"],
                diagnosis=pl["diagnosis"],
                action_taken=pl.get("action_taken"),
                verdict=pl.get("verdict", "?"),
                target_metric=pl["target_metric"],
                target_value=pl["target_value"],
                score=float(h.score),
            )
        )
    log.info(  # audit
        "episodic_recall",
        query_sensor=sensor,
        n_hits=len(cases),
        hit_ids=[c.incident_id for c in cases],
    )
    return cases


def list_trajectories(since: str | None = None, until: str | None = None) -> list[EpisodicCase]:
    """Every stored trajectory, optionally within the ISO-8601 [since, until]
    window — the weekly Reflector's input. Distinct from retrieve_similar: the
    reflector reads a WHOLE window and inducts across it, so this returns all
    matching cases (sorted by incident id ≈ chronology), not the nearest few by
    similarity. created_at is a UTC isoformat string, so a lexical bound compares
    chronologically. Empty/cold store → []."""
    client = _client()
    if not client.collection_exists(COLLECTION):
        log.info("episodic_list_empty", reason="no collection yet")
        return []
    cases: list[EpisodicCase] = []
    offset: Any = None
    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for p in points:
            pl = p.payload or {}
            created = str(pl.get("created_at", ""))
            if since and created and created < since:
                continue
            if until and created and created > until:
                continue
            cases.append(
                EpisodicCase(
                    incident_id=pl["incident_id"],
                    room=pl.get("room", "?"),
                    sensor=pl["sensor"],
                    value=pl["value"],
                    rule_violated=pl["rule_violated"],
                    diagnosis=pl["diagnosis"],
                    action_taken=pl.get("action_taken"),
                    verdict=pl.get("verdict", "?"),
                    target_metric=pl["target_metric"],
                    target_value=pl["target_value"],
                    score=0.0,  # not a similarity query — window scan
                )
            )
        if offset is None:
            break
    cases.sort(key=lambda c: c.incident_id)
    log.info("episodic_list", n=len(cases), since=since, until=until)  # audit
    return cases
