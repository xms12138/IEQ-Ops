"""rag/ingest.py — build the Qdrant retrieval corpus (chunk → embed → upsert).

Phase 2 `--sample` (default): reads rag/sample_corpus.py placeholder excerpts.
Real corpus (TODO): read rag/corpus/*.pdf, extract text per standard, same downstream.

Pipeline:
    passages → RecursiveCharacterTextSplitter(500/50) → chunks
             → embed_text = ctx_prefix + text   (prefix="" for now — see TODO)
             → BGE-M3 encode (GPU, shared loader with retrieve so vectors match)
             → Qdrant upsert {vector, payload: text, embed_text, source, domain, chunk_idx}

TODO (next step): Anthropic Contextual Retrieval prefix — node #10 in
ops/llm_routing.md (cloud V4-Flash + KV cache). That is the ONLY LLM in ingest,
it is build-time, and it lives here, not in mcp-rag-server (Hard Constraint #9 is
about the server). The sample path below has no LLM at all.
"""

from __future__ import annotations

import argparse

from core.config import get_settings
from core.logging import configure_logging, get_logger
from rag.retrieve import COLLECTION, EMBED_DIM, load_embedder
from rag.sample_corpus import SAMPLES

log = get_logger("rag_ingest")

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def chunk_passages(passages: list[dict[str, str]]) -> list[dict]:
    """Split each passage with the same splitter douluo used. The short sample
    excerpts mostly stay one chunk each; real PDF sections will fan out. chunk_idx
    is a global running id (also the Qdrant point id)."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", "; ", ", ", " ", ""],
        length_function=len,
    )
    chunks: list[dict] = []
    for p in passages:
        for piece in splitter.split_text(p["text"]):
            chunks.append(
                {
                    "text": piece,
                    "embed_text": piece,  # TODO: ctx_prefix + piece once #10 lands
                    "source": p["source"],
                    "domain": p["domain"],
                }
            )
    for i, c in enumerate(chunks):
        c["chunk_idx"] = i
    return chunks


def ingest(device: str, fp16: bool) -> None:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    settings = get_settings()
    chunks = chunk_passages(SAMPLES)
    log.info("ingest_chunks", n=len(chunks))

    embedder = load_embedder(device, fp16)
    vectors = embedder.encode(
        [c["embed_text"] for c in chunks], normalize_embeddings=True, batch_size=32
    )

    client = QdrantClient(url=settings.qdrant_url)
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
    )
    client.upsert(
        collection_name=COLLECTION,
        points=[
            PointStruct(
                id=c["chunk_idx"],
                vector=[float(x) for x in vectors[i]],
                payload={
                    "text": c["text"],
                    "embed_text": c["embed_text"],
                    "source": c["source"],
                    "domain": c["domain"],
                    "chunk_idx": c["chunk_idx"],
                },
            )
            for i, c in enumerate(chunks)
        ],
    )
    count = client.count(COLLECTION).count
    log.info("ingest_done", collection=COLLECTION, points=count)
    print(f"ingested {count} chunks into '{COLLECTION}'  (dim={EMBED_DIM}, cosine)")


def main() -> None:
    configure_logging(get_settings().log_level)
    ap = argparse.ArgumentParser(description="Build the IEQ standards retrieval corpus in Qdrant.")
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    ap.add_argument("--no-fp16", action="store_true", help="fp32 (use with --device cpu)")
    args = ap.parse_args()
    ingest(args.device, fp16=not args.no_fp16)


if __name__ == "__main__":
    main()
