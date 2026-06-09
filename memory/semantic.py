"""semantic.py — building-specific facts (memory tier 2).

A semantic fact is a durable, building-specific generalisation distilled from
MANY episodes — e.g. "Room R1 CO2 exceeds 1000 ppm within ~40 min whenever 5+
people meet with ventilation on low". It is NOT one incident (that is episodic);
it is an induction ACROSS incidents, minted weekly by the Reflector (cloud
deepseek-v4-pro — Hard Constraint #12, never local: local 8B fabricates
generalisations wholesale, A4.5).

Storage: Qdrant collection `ieq_semantic_facts`, one point per fact. The fact text
is embedded with the SAME CPU BGE-M3 stack as episodic (memory/embedding.py) so
facts can later be recalled by similarity — by the Conversational agent's
memory-first dispatch and a future planner enrichment. The structured record
(incident type generalised, evidence incident ids, ISO week minted) rides in the
payload.

Hard Constraint #3: this module is the ONLY writer. The Reflector produces fact
DRAFTS (text + evidence ids, no id); save_facts() — called from the
ReflectionGraph's `consolidate` node — assigns the SF-{year}-W{week}-{seq} id
(CLAUDE.md memory ids), embeds, upserts, and emits an audit log line. Agent nodes
never upsert here. seq is assigned serially by the single consolidate node (the
fan-out reflect branches only produce drafts), so there is no concurrent-id hazard.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field

from core.config import get_settings
from core.logging import get_logger
from memory.embedding import EMBED_DIM, embed, embed_batch

log = get_logger("semantic")

COLLECTION = "ieq_semantic_facts"
DEFAULT_TOP_K = 5
# Defensive upper bound on how many points list_facts scrolls before sorting; facts
# grow slowly, so this is never reached in practice — it just caps an unbounded scroll.
_LIST_SCAN_CAP = 1000

# Distinct namespace from episodic — a fact id and an incident id must never map to
# the same Qdrant point uuid.
_NS = uuid.UUID("1e9c0e7a-3b2d-5f4a-9c1e-000000000002")


class SemanticFactDraft(BaseModel):
    """A fact as the Reflector proposes it — no id yet (assigned at save time)."""

    fact: str
    incident_type: str  # airquality | thermal | lighting | acoustic
    evidence_ids: list[str] = Field(default_factory=list)


class SemanticFact(BaseModel):
    """A persisted building fact, handed back on recall (score = cosine sim)."""

    fact_id: str
    fact: str
    incident_type: str
    evidence_ids: list[str]
    week: str
    score: float = 0.0


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
        log.info("semantic_collection_created", collection=COLLECTION, dim=EMBED_DIM)


def _point_id(fact_id: str) -> str:
    return str(uuid.uuid5(_NS, fact_id))


def _next_seq(client: Any, week: str) -> int:
    """Next sequence for SF ids minted this ISO week. Called serially by the
    consolidate node, so an exact count is race-free."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    flt = Filter(must=[FieldCondition(key="week", match=MatchValue(value=week))])
    n = client.count(collection_name=COLLECTION, count_filter=flt, exact=True).count
    return int(n) + 1


def save_facts(drafts: list[SemanticFactDraft], *, week: str) -> list[str]:
    """Persist a batch of reflector-proposed facts (Hard Constraint #3: the only
    writer, with an audit log). Assigns SF-{week}-{seq} ids, batch-embeds the fact
    text, upserts. Returns the assigned fact ids. An empty draft list is a no-op."""
    if not drafts:
        log.info("semantic_save_empty", week=week)
        return []
    from qdrant_client.models import PointStruct

    client = _client()
    _ensure_collection(client)
    vectors = embed_batch([d.fact for d in drafts])
    seq0 = _next_seq(client, week)
    now = datetime.now(UTC).isoformat()
    points: list[Any] = []
    fact_ids: list[str] = []
    for i, (d, vec) in enumerate(zip(drafts, vectors, strict=True)):
        fact_id = f"SF-{week}-{seq0 + i:03d}"  # week == "YYYY-Wnn" → SF-2026-W22-001
        points.append(
            PointStruct(
                id=_point_id(fact_id),
                vector=vec,
                payload={
                    "fact_id": fact_id,
                    "fact": d.fact,
                    "incident_type": d.incident_type,
                    "evidence_ids": d.evidence_ids,
                    "week": week,
                    "created_at": now,
                },
            )
        )
        fact_ids.append(fact_id)
    client.upsert(collection_name=COLLECTION, points=points)
    log.info("semantic_saved", week=week, n=len(fact_ids), fact_ids=fact_ids)  # audit
    return fact_ids


def retrieve_facts(
    query: str, top_k: int = DEFAULT_TOP_K, incident_type: str | None = None
) -> list[SemanticFact]:
    """Recall building facts by semantic similarity (optionally scoped to one
    incident type). Empty/cold store → []. Future readers: the Conversational
    memory-first dispatch and a planner enrichment."""
    client = _client()
    if not client.collection_exists(COLLECTION):
        log.info("semantic_recall_empty", reason="no collection yet")
        return []
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    flt = (
        Filter(must=[FieldCondition(key="incident_type", match=MatchValue(value=incident_type))])
        if incident_type
        else None
    )
    hits = client.query_points(
        collection_name=COLLECTION,
        query=embed(query),
        query_filter=flt,
        limit=top_k,
        with_payload=True,
    ).points
    facts: list[SemanticFact] = []
    for h in hits:
        pl = h.payload or {}
        facts.append(
            SemanticFact(
                fact_id=pl["fact_id"],
                fact=pl["fact"],
                incident_type=pl.get("incident_type", "?"),
                evidence_ids=pl.get("evidence_ids", []),
                week=pl.get("week", "?"),
                score=float(h.score),
            )
        )
    log.info("semantic_recall", query=query[:40], n_hits=len(facts))  # audit
    return facts


def list_facts(incident_type: str | None = None, limit: int = 5) -> list[SemanticFact]:
    """The most RECENT `limit` facts (newest first by created_at), optionally scoped
    to one incident type, via Qdrant scroll — NO vector search, so no embedding
    model/key is needed (RPi-friendly). The Q&A butler puts only this small recent
    slice into the LLM context, so context size stays bounded as facts accrue over a
    long deployment; `score` is 0.0 (not a similarity result). Empty/cold store → []."""
    client = _client()
    if not client.collection_exists(COLLECTION):
        log.info("semantic_list_empty", reason="no collection yet")
        return []
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    flt = (
        Filter(must=[FieldCondition(key="incident_type", match=MatchValue(value=incident_type))])
        if incident_type
        else None
    )
    # Pull up to a defensive cap, then sort newest-first and keep `limit`. Facts accrue
    # slowly (a few per weekly reflection), so the cap is never hit in practice — it just
    # bounds the scroll if the store ever grows large. ISO timestamps sort chronologically.
    points, _ = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=flt,
        limit=_LIST_SCAN_CAP,
        with_payload=True,
        with_vectors=False,
    )
    points.sort(key=lambda p: str((p.payload or {}).get("created_at", "")), reverse=True)
    facts: list[SemanticFact] = []
    for p in points[:limit]:
        pl = p.payload or {}
        facts.append(
            SemanticFact(
                fact_id=pl["fact_id"],
                fact=pl["fact"],
                incident_type=pl.get("incident_type", "?"),
                evidence_ids=pl.get("evidence_ids", []),
                week=pl.get("week", "?"),
                score=0.0,
            )
        )
    log.info("semantic_list", n=len(facts), incident_type=incident_type or "all")  # audit
    return facts
