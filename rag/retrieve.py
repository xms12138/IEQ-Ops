"""rag/retrieve.py — deterministic dual-path retrieval stack (NO LLM).

The retrieval primitive behind mcp-rag-server (Hard Constraint #9: the RAG MCP
server contains no LLM — decompose/grade/rewrite/generate all stay in the
Specialist). Ported from the douluo A4 stack (contextual_rag.py) with the choices
TECH_STACK explicitly overturns for IEQ-Ops:

  douluo (A4)                       IEQ-Ops (here)
  ───────────────────────────────── ────────────────────────────────────────────
  bge-small-zh-v1.5 dense, FAISS    BGE-M3 dense, Qdrant (persistent + payload filter)
  CrossEncoder(device="cpu")        AutoModelForSequenceClassification, cuda fp16
  jieba (Chinese) BM25              regex word-split (English standards corpus)
  one corpus                        domain-sliced (airquality|thermal|lighting|acoustic)

Pipeline (per sub-query — identical algorithm to douluo, only the dense source
is swapped FAISS→Qdrant):

    query
      → BGE-M3 encode → Qdrant dense top-20 (filtered to `domain`)
      → BM25 sparse top-20 (in-memory index over the same domain slice)
      → RRF fuse → top-30 candidates
      → bge-reranker-v2-m3 (query, embed_text) → top-5

`embed_text` (= ctx_prefix + text) drives dense/BM25/rerank; only `text` is
returned for the LLM prompt. Prefix is a retrieval signpost, not answer material —
letting it into the prompt forms a "model reads its own summary" echo that
amplifies a hallucinated prefix into a hallucinated answer (douluo's rationale).

Resources (BGE-M3 + reranker on GPU, Qdrant client, BM25 index) load once in
__init__; mcp-rag-server holds one RetrievalStack for its lifetime, so the 4.0 GB
fp16 footprint (VRAM spike, 2026-05-25) is paid once, not per query.
"""

from __future__ import annotations

import re
import threading
from typing import Any

from pydantic import BaseModel

EMBED_MODEL = "BAAI/bge-m3"
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
COLLECTION = "ieq_standards"
EMBED_DIM = 1024  # BGE-M3 dense dimension

DENSE_TOP_K = 20
SPARSE_TOP_K = 20
CANDIDATE_TOP_K = 30
FINAL_TOP_K = 5
RRF_K = 60


class RetrievedChunk(BaseModel):
    """One reranked chunk returned to the Specialist (mcp-rag-server tool output).

    `text` is the raw standard text for the LLM prompt; `score` is the reranker
    logit. The retrieval-only `embed_text` (ctx_prefix + text) never leaves here.
    """

    text: str
    source: str  # e.g. "ashrae-62.1"
    domain: str  # airquality | thermal | lighting | acoustic
    chunk_idx: int
    score: float  # bge-reranker-v2-m3 logit
    fusion_source: str  # "both" | "dense" | "sparse" — which path surfaced it


def tokenize(text: str) -> list[str]:
    """BM25 tokenizer for the English standards corpus (douluo used jieba for
    Chinese). Lowercase + split on non-alphanumerics. The dense path carries
    semantics; BM25 carries exact terms ('co2', 'ppm', 'ashrae')."""
    return [t for t in re.split(r"[^0-9a-z]+", text.lower()) if t]


def rrf(dense_ids: list[int], sparse_ids: list[int], k: int = RRF_K) -> dict[int, float]:
    """Reciprocal Rank Fusion (verbatim from douluo). Uses rank position, not raw
    score, so dense cosine and BM25 magnitudes never need normalising."""
    scores: dict[int, float] = {}
    for rank, idx in enumerate(dense_ids):
        scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)
    for rank, idx in enumerate(sparse_ids):
        scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return scores


def load_embedder(device: str = "cuda", fp16: bool = True) -> Any:
    """Load BGE-M3 exactly as ops/scripts/vram_spike.py — the one config verified
    on this 6 GB card. Shared by ingest (encodes the corpus) and retrieve (encodes
    the query) so document and query vectors come from an identical model/precision."""
    from sentence_transformers import SentenceTransformer

    embedder = SentenceTransformer(
        EMBED_MODEL, device=device, model_kwargs={"use_safetensors": True}
    )
    if fp16 and device == "cuda":
        embedder = embedder.half()
    return embedder


class RetrievalStack:
    """BGE-M3 + reranker (GPU) + Qdrant client + an in-memory BM25 index over the
    current collection. One instance per mcp-rag-server process."""

    def __init__(
        self,
        qdrant_url: str,
        *,
        device: str = "cuda",
        fp16: bool = True,
        collection: str = COLLECTION,
    ) -> None:
        # Heavy deps imported here (not at module top) so importing this module
        # stays cheap and never drags torch into the graph process, which never
        # retrieves directly — it goes through mcp-rag-server.
        import torch
        from qdrant_client import QdrantClient
        from rank_bm25 import BM25Okapi
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._torch = torch
        self.collection = collection
        self.device = device
        half = fp16 and device == "cuda"

        # BGE-M3 dense encoder — shared loader, identical config to ingest (so query
        # and document vectors match) and to the verified VRAM spike.
        self._embedder = load_embedder(device, fp16)

        # Reranker via plain transformers — CrossEncoder/FlagReranker break against
        # this venv's transformers/tokenizer versions (vram_spike.py docstring).
        self._rr_tok = AutoTokenizer.from_pretrained(RERANKER_MODEL)
        self._rr_model = (
            AutoModelForSequenceClassification.from_pretrained(
                RERANKER_MODEL,
                torch_dtype=(torch.float16 if half else torch.float32),
            )
            .to(device)
            .eval()
        )

        self._client = QdrantClient(url=qdrant_url)
        self._BM25 = BM25Okapi

        # Serialises the GPU forward passes (embedder + reranker). One shared stack can
        # see concurrent retrieve() calls — the bench fans samples across threads, and a
        # real mcp-rag-server will field concurrent MCP requests — and a concurrent
        # forward on this transformers/torch build corrupts the reranker's dtype state
        # ("expected Half, found Float"). The GPU work is ~50 ms, far under the cloud-LLM
        # cost that actually parallelises, so serialising it costs effectively nothing.
        self._gpu_lock = threading.Lock()

        # dense lives in Qdrant; BM25 is a derived index over the same points,
        # rebuilt in memory at startup.
        self._pos_by_id: dict[Any, int] = {}
        self._docs: list[dict[str, Any]] = self._load_docs()
        self._bm25 = (
            self._BM25([tokenize(d["embed_text"]) for d in self._docs]) if self._docs else None
        )

    def _load_docs(self) -> list[dict[str, Any]]:
        """Scroll every point out of Qdrant once → ordered doc list. The list
        position is the shared id space RRF fuses on: dense returns Qdrant point
        ids (mapped back to position via `_pos_by_id`); sparse returns position
        directly."""
        if not self._client.collection_exists(self.collection):
            return []  # ingest hasn't run yet — retrieve() will return []
        docs: list[dict[str, Any]] = []
        offset = None
        while True:
            points, offset = self._client.scroll(
                collection_name=self.collection,
                with_payload=True,
                with_vectors=False,
                limit=256,
                offset=offset,
            )
            for p in points:
                pl = p.payload or {}
                docs.append(
                    {
                        "point_id": p.id,
                        "text": pl["text"],
                        "embed_text": pl.get("embed_text", pl["text"]),
                        "source": pl["source"],
                        "domain": pl["domain"],
                        "chunk_idx": pl["chunk_idx"],
                    }
                )
            if offset is None:
                break
        self._pos_by_id = {d["point_id"]: i for i, d in enumerate(docs)}
        return docs

    def _embed(self, query: str) -> list[float]:
        with self._gpu_lock:
            vec = self._embedder.encode([query], normalize_embeddings=True)
        return [float(x) for x in vec[0]]

    def _rerank_scores(self, query: str, texts: list[str]) -> list[float]:
        torch = self._torch
        with self._gpu_lock, torch.no_grad():
            inp = self._rr_tok(
                [query] * len(texts),
                texts,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            ).to(self.device)
            return self._rr_model(**inp).logits.view(-1).float().tolist()  # type: ignore[no-any-return]

    def retrieve(self, query: str, domain: str, final_k: int = FINAL_TOP_K) -> list[RetrievedChunk]:
        """Dual-path recall + rerank, restricted to one domain slice."""
        if not self._docs or self._bm25 is None:
            return []
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        domain_filter = Filter(must=[FieldCondition(key="domain", match=MatchValue(value=domain))])

        # ── dense (Qdrant, domain-filtered) → fusion positions ──
        q_vec = self._embed(query)
        hits = self._client.query_points(
            collection_name=self.collection,
            query=q_vec,
            query_filter=domain_filter,
            limit=DENSE_TOP_K,
            with_payload=False,
        ).points
        dense_pos = [self._pos_by_id[h.id] for h in hits if h.id in self._pos_by_id]

        # ── sparse (in-memory BM25, domain-filtered after scoring) → positions ──
        bm_scores = self._bm25.get_scores(tokenize(query))
        domain_pos = [i for i, d in enumerate(self._docs) if d["domain"] == domain]
        sparse_pos = sorted(domain_pos, key=lambda i: bm_scores[i], reverse=True)[:SPARSE_TOP_K]

        # ── RRF fuse → candidate positions ──
        fused = rrf(dense_pos, sparse_pos)
        cand_pos = sorted(fused, key=lambda i: fused[i], reverse=True)[:CANDIDATE_TOP_K]
        if not cand_pos:
            return []
        dense_set, sparse_set = set(dense_pos), set(sparse_pos)

        # ── rerank (query, embed_text) → final_k ──
        scores = self._rerank_scores(query, [self._docs[i]["embed_text"] for i in cand_pos])
        ranked = sorted(zip(cand_pos, scores, strict=True), key=lambda t: t[1], reverse=True)[
            :final_k
        ]

        out: list[RetrievedChunk] = []
        for pos, score in ranked:
            d = self._docs[pos]
            in_d, in_s = pos in dense_set, pos in sparse_set
            out.append(
                RetrievedChunk(
                    text=d["text"],
                    source=d["source"],
                    domain=d["domain"],
                    chunk_idx=d["chunk_idx"],
                    score=float(score),
                    fusion_source="both" if in_d and in_s else ("dense" if in_d else "sparse"),
                )
            )
        return out
