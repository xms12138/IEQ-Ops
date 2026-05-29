"""CPU BGE-M3 embedding for the memory tiers (episodic now, semantic next).

Why CPU, not GPU (author decision, 2026-05-29): the dev-phase GPU is already
saturated by mcp-rag-server's RetrievalStack — BGE-M3 + reranker, 4.0 GB, a lazy
singleton living in the SAME graph process (mcp_servers/client.py is in-memory
transport, so `call_tool(rag_server, ...)` runs the stack in-process). Opening a
second BGE-M3 on the 6 GB card would OOM. Memory recall is NOT on the RAG <500 ms
budget — it runs inside the planner node, itself a REASONING-tier (multi-second)
call — so a few-hundred-ms CPU encode is free. fp16 is auto-disabled on CPU by
load_embedder (half precision is a GPU-only win).

Same model + loader as RAG (rag.retrieve.load_embedder) so the project maintains
ONE embedding stack; only the device differs. The episodic Qdrant collection is
separate from the RAG corpus, so it only needs to be self-consistent (the same
model encodes both write and recall), which it is.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from core.logging import get_logger
from rag.retrieve import EMBED_DIM, load_embedder

log = get_logger("memory-embed")

__all__ = ["EMBED_DIM", "embed", "embed_batch"]


@lru_cache(maxsize=1)
def _embedder() -> Any:
    """Load BGE-M3 on CPU once, on first use (not at import) so the graph process
    pays nothing until a memory read/write actually happens."""
    log.info("memory_embedder_load", model="BAAI/bge-m3", device="cpu")
    return load_embedder(device="cpu", fp16=False)


def embed(text: str) -> list[float]:
    """Encode one string to a normalised 1024-d vector (cosine-ready)."""
    vec = _embedder().encode([text], normalize_embeddings=True)
    return [float(x) for x in vec[0]]


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Encode many strings (used by the reflection consolidation pass later)."""
    if not texts:
        return []
    vecs = _embedder().encode(texts, normalize_embeddings=True, batch_size=16)
    return [[float(x) for x in v] for v in vecs]
