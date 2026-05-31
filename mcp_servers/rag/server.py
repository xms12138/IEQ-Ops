"""mcp-rag-server — FastMCP wrapper over rag/retrieve.py. NO LLM (Hard Constraint #9).

A deterministic retrieval primitive: BM25 + BGE-M3 dual recall → bge-reranker-v2-m3
rerank, restricted to one domain's standards slice. Every bit of Agentic RAG
intelligence — decompose / grade / rewrite / generate — lives in the calling
Specialist subgraph, never here. Putting an LLM in this server is forbidden:
query rewriting and self-reflective grading belong to the Specialist (CLAUDE.md #9).

The server holds ONE RetrievalStack for its lifetime: the 4.0 GB fp16 GPU footprint
and the in-memory BM25 index are built once on the first call, then reused across
every retrieve. Phase 5 swaps the transport (in-memory → stdio/HTTP) without
touching this body — the tool contract (name + RetrievedChunk shape) stays fixed.
"""

from __future__ import annotations

import os

from fastmcp import FastMCP

from core.config import get_settings
from rag.retrieve import FINAL_TOP_K, RetrievalStack, RetrievedChunk

mcp = FastMCP("mcp-rag-server")

_stack: RetrievalStack | None = None


def _get_stack() -> RetrievalStack:
    """Lazy singleton — load BGE-M3 + reranker (GPU) + BM25 index on first use, not
    at import, so importing this server (in-memory transport, tests) does not eagerly
    seize the GPU. IEQ_RAG_DEVICE=cpu forces fp32/CPU for a machine without the card."""
    global _stack
    if _stack is None:
        device = os.getenv("IEQ_RAG_DEVICE", "cuda")
        _stack = RetrievalStack(get_settings().qdrant_url, device=device, fp16=(device == "cuda"))
    return _stack


@mcp.tool
def retrieve(query: str, domain: str, top_k: int = FINAL_TOP_K) -> list[RetrievedChunk]:
    """Dual-path retrieve + rerank over one domain's standards slice.

    Args:
        query: a single sub-query (the Specialist's decompose node splits first).
        domain: airquality | thermal | lighting | acoustic — selects the corpus slice.
        top_k: number of reranked chunks to return.

    Returns the reranked chunks. Judging whether they suffice is the Specialist's
    grade node, not this server's job.
    """
    return _get_stack().retrieve(query, domain, final_k=top_k)
