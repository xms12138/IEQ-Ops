"""rag/ingest.py — build the Qdrant retrieval corpus (chunk → embed → upsert).

Source modes (`--source`):
    auto    (default) real PDFs from rag/corpus/ if any are present, else sample
    corpus  real PDFs only — listed in rag/corpus_manifest.json, read via pypdf
    sample  rag/sample_corpus.py placeholder excerpts (committed, no copyright)

The real PDFs (ASHRAE / WELL / EN / WHO) are gitignored under rag/corpus/ for
copyright; corpus_manifest.json maps each file to its (source, domain) and an
optional 1-based page range so only the relevant section is ingested.

Pipeline:
    passages → RecursiveCharacterTextSplitter(500/50) → chunks
             → embed_text = ctx_prefix + text   (prefix added when --contextual)
             → BGE-M3 encode (GPU, shared loader with retrieve so vectors match)
             → Qdrant upsert {vector, payload: text, embed_text, source, domain, chunk_idx}

Contextual prefix (--contextual): Anthropic Contextual Retrieval — node #10 in
ops/llm_routing.md (cloud v4-flash + implicit KV cache). The ONLY LLM in ingest;
build-time, and it lives here, not in mcp-rag-server (Hard Constraint #9 is about
the server). It prepends a 50-100w signpost to each real-corpus chunk's embed_text;
sample placeholders and the plain (no-flag) path stay LLM-free.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from string import Template
from typing import Any

from core.config import get_settings
from core.logging import configure_logging, get_logger
from rag.retrieve import COLLECTION, EMBED_DIM, load_embedder
from rag.sample_corpus import SAMPLES

log = get_logger("rag_ingest")

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
CORPUS_DIR = Path(__file__).parent / "corpus"
MANIFEST_PATH = Path(__file__).parent / "corpus_manifest.json"


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
                    "embed_text": piece,  # contextual prefix prepended later if --contextual (#10)
                    "source": p["source"],
                    "domain": p["domain"],
                }
            )
    for i, c in enumerate(chunks):
        c["chunk_idx"] = i
    return chunks


def parse_page_spec(spec: str | None, n_pages: int) -> list[int]:
    """1-based inclusive page spec ("30-70", "12", "1-5,10-12") -> 0-based indices,
    clamped to the document. None / "" selects every page."""
    if not spec:
        return list(range(n_pages))
    idxs: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(part)
        idxs.extend(p - 1 for p in range(start, end + 1) if 1 <= p <= n_pages)
    return idxs


def collapse_repeated_lines(text: str) -> str:
    """WELL's PDF double-renders heading/label lines: extract_text emits each one
    twice back-to-back ("Intent:\\nIntent:\\n ..."). Fold runs of identical adjacent
    lines to one. Body lines are untouched — they don't repeat verbatim line-for-line."""
    out: list[str] = []
    prev: str | None = None
    for line in text.split("\n"):
        if line != prev:
            out.append(line)
        prev = line
    return "\n".join(out)


def read_corpus_pdfs() -> list[dict[str, str]]:
    """Read the real (gitignored) PDFs listed in corpus_manifest.json, returning
    passages shaped like sample_corpus.SAMPLES. Missing files are warned and
    skipped, so a partially-filled corpus still ingests whatever is present."""
    from pypdf import PdfReader

    if not MANIFEST_PATH.exists():
        log.warning("corpus_manifest_missing", path=str(MANIFEST_PATH))
        return []
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    passages: list[dict[str, str]] = []
    for doc in manifest.get("documents", []):
        path = CORPUS_DIR / doc["file"]
        if not path.exists():
            log.warning("corpus_pdf_missing", file=doc["file"], source=doc.get("source"))
            continue
        reader = PdfReader(str(path))
        spec = doc.get("pages")
        idxs = parse_page_spec(str(spec) if spec is not None else None, len(reader.pages))
        raw = "\n".join((reader.pages[i].extract_text() or "") for i in idxs)
        text = collapse_repeated_lines(raw).strip()
        if not text:
            log.warning("corpus_pdf_empty_text", file=doc["file"])
            continue
        passages.append({"domain": doc["domain"], "source": doc["source"], "text": text})
        log.info(
            "corpus_pdf_read",
            source=doc["source"],
            domain=doc["domain"],
            pages=len(idxs),
            chars=len(text),
        )
    return passages


def select_passages(mode: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Returns (passages, corpus_passages). passages is what gets ingested;
    corpus_passages is the real-PDF subset (each carries its full-document text)
    so contextual prefixing can run on real chunks and skip sample filler.

    sample: committed placeholder excerpts (all domains), no corpus.
    corpus: real PDFs for the domains they cover + sample excerpts filling any
            domain no PDF covers yet (hard-fail if no PDF is present at all). The
            gradual-migration path: a real airquality PDF replaces only airquality
            samples, leaving thermal/lighting/acoustic on placeholders.
    auto:   corpus behaviour if any PDF is present, else all sample."""
    if mode == "sample":
        return SAMPLES, []
    corpus = read_corpus_pdfs()
    if not corpus:
        if mode == "corpus":
            raise SystemExit(
                "no corpus PDFs found — put files in rag/corpus/ per "
                "rag/corpus_manifest.json, or run with --source sample"
            )
        log.info("ingest_source", mode="sample_fallback", passages=len(SAMPLES))
        return SAMPLES, []
    covered = {p["domain"] for p in corpus}
    filler = [s for s in SAMPLES if s["domain"] not in covered]
    log.info(
        "ingest_source",
        mode="corpus+filler",
        corpus=len(corpus),
        covered=sorted(covered),
        sample_filler=len(filler),
    )
    return corpus + filler, corpus


def make_contextual_prefix(router: Any, template: Template, document: str, chunk: str) -> str:
    """Node #10 (build-time, cloud v4-flash + implicit KV cache): a 50-100w signpost
    situating one chunk in its document (Anthropic Contextual Retrieval). The
    document goes first in the prompt so DeepSeek's prefix cache is reused across a
    document's chunks. A failed call degrades to "" (chunk keeps plain-text embed)."""
    content = template.substitute(document=document, chunk=chunk)
    try:
        out = router.complete(
            "ingest.contextual_prefix",
            [{"role": "user", "content": content}],
            temperature=0,
        )
    except Exception as exc:  # noqa: BLE001 — build-time; one bad chunk must not abort ingest
        log.warning("contextual_prefix_failed", error=str(exc))
        return ""
    return " ".join(out.split())


def apply_contextual_prefixes(chunks: list[dict], doc_by_source: dict[str, str]) -> None:
    """Prepend a contextual prefix to every chunk whose source is a real document,
    mutating only `embed_text` (the retrieval signal); `text` stays the raw clause
    fed to the Specialist. Concurrent — build-time, hundreds of flash calls."""
    from concurrent.futures import ThreadPoolExecutor

    from agents.prompt_loader import load_prompt
    from core.router import Router

    targets = [c for c in chunks if c["source"] in doc_by_source]
    if not targets:
        return
    router = Router()
    template = load_prompt("ingest/contextual_prefix")

    def worker(c: dict) -> None:
        prefix = make_contextual_prefix(router, template, doc_by_source[c["source"]], c["text"])
        if prefix:
            c["embed_text"] = prefix + "\n\n" + c["text"]

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(worker, targets))
    applied = sum(1 for c in targets if c["embed_text"] != c["text"])
    log.info("contextual_prefixes", targets=len(targets), applied=applied)


def ingest(
    device: str, fp16: bool, source_mode: str, contextual: bool, collection: str = COLLECTION
) -> None:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    settings = get_settings()
    passages, corpus_passages = select_passages(source_mode)
    chunks = chunk_passages(passages)
    log.info("ingest_chunks", n=len(chunks), passages=len(passages))
    if contextual and corpus_passages:
        apply_contextual_prefixes(chunks, {p["source"]: p["text"] for p in corpus_passages})

    embedder = load_embedder(device, fp16)
    vectors = embedder.encode(
        [c["embed_text"] for c in chunks], normalize_embeddings=True, batch_size=32
    )

    client = QdrantClient(url=settings.qdrant_url)
    if client.collection_exists(collection):
        client.delete_collection(collection)
    client.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
    )
    client.upsert(
        collection_name=collection,
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
    count = client.count(collection).count
    log.info("ingest_done", collection=collection, points=count)
    print(f"ingested {count} chunks into '{collection}'  (dim={EMBED_DIM}, cosine)")


def main() -> None:
    configure_logging(get_settings().log_level)
    ap = argparse.ArgumentParser(description="Build the IEQ standards retrieval corpus in Qdrant.")
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    ap.add_argument("--no-fp16", action="store_true", help="fp32 (use with --device cpu)")
    ap.add_argument(
        "--source",
        default="auto",
        choices=["auto", "sample", "corpus"],
        help="auto: real corpus if present else sample; corpus: real only; sample: placeholders",
    )
    ap.add_argument(
        "--contextual",
        action="store_true",
        help="add contextual-retrieval prefixes to real-corpus chunks (node #10, v4-flash)",
    )
    ap.add_argument(
        "--collection",
        default=COLLECTION,
        help="Qdrant collection name (default: the production collection). Use a side "
        "collection (e.g. ieq_standards_ctx) to build a contextual-prefix variant for "
        "an eval ablation without touching the production corpus.",
    )
    args = ap.parse_args()
    ingest(
        args.device,
        fp16=not args.no_fp16,
        source_mode=args.source,
        contextual=args.contextual,
        collection=args.collection,
    )


if __name__ == "__main__":
    main()
