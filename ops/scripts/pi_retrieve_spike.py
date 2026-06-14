"""Pi4 CPU retrieval spike — exhibit-deployment phase 0 gate.

Answers the one real unknown of the single-board exhibit plan: can the Pi 4 (8 GB,
no GPU) load BGE-M3 + bge-reranker-v2-m3 in fp32 and run the full retrieve pipeline
(dense + BM25 + RRF + rerank) at an acceptable latency and memory footprint?

The verdict drives the plan's branch: comfortable headroom → fp32 resident is the
final answer; tight → int8 quantisation (ONNX Runtime) or idle-unload in
mcp_servers/rag/server.py. Budget: load peak well under ~7 GB total so the OS and
the kiosk browser keep breathing room; per-retrieve latency 10 s+ is acceptable
because diagnosis sits off the 5-min monitoring hot path.

Run on the Pi (corpus already ingested into the local Qdrant):
    cd ~/dissertation && .venv/bin/python -m ops.scripts.pi_retrieve_spike

Measures with stdlib only (resource.ru_maxrss + /proc/self/status) — no psutil,
nothing to install on the Pi.
"""

from __future__ import annotations

import argparse
import resource
import time

# One realistic diagnosis query per domain, mirroring what a Specialist's
# decompose step feeds retrieve() — exercises each domain's corpus slice.
QUERIES = [
    ("airquality", "What CO2 concentration threshold does the standard set for occupied spaces?"),
    ("thermal", "What indoor temperature range is required for thermal comfort compliance?"),
    ("lighting", "What illuminance level in lux is required for work areas?"),
    ("acoustic", "What maximum indoor noise level in dBA does the standard allow?"),
]


def rss_mib() -> float:
    """Current RSS in MiB from /proc (Linux only, which is all the Pi is)."""
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    return 0.0


def peak_mib() -> float:
    """Process-lifetime peak RSS in MiB (ru_maxrss is KiB on Linux)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def stage_breakdown(stack: object, query: str, domain: str, reps: int) -> None:
    """Time each retrieve() stage separately by mirroring its pipeline, plus the
    rerank forward at candidate pools of 30/10/1 — the 30→10 delta is the data
    behind any CANDIDATE_TOP_K cut, and the 1-pair time is the per-candidate floor."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    from rag.retrieve import CANDIDATE_TOP_K, DENSE_TOP_K, SPARSE_TOP_K, rrf, tokenize

    s = stack  # typed as object to keep the spike decoupled from internals churn
    domain_filter = Filter(must=[FieldCondition(key="domain", match=MatchValue(value=domain))])

    for rep in range(reps):
        t = time.time()
        q_vec = s._embed(query)  # type: ignore[attr-defined]
        t_embed = time.time() - t

        t = time.time()
        hits = s._client.query_points(  # type: ignore[attr-defined]
            collection_name=s.collection,  # type: ignore[attr-defined]
            query=q_vec,
            query_filter=domain_filter,
            limit=DENSE_TOP_K,
            with_payload=False,
        ).points
        t_dense = time.time() - t

        t = time.time()
        bm_scores = s._bm25.get_scores(tokenize(query))  # type: ignore[attr-defined]
        docs = s._docs  # type: ignore[attr-defined]
        domain_pos = [i for i, d in enumerate(docs) if d["domain"] == domain]
        sparse_pos = sorted(domain_pos, key=lambda i: bm_scores[i], reverse=True)[:SPARSE_TOP_K]
        t_bm25 = time.time() - t

        dense_pos = [s._pos_by_id[h.id] for h in hits if h.id in s._pos_by_id]  # type: ignore[attr-defined]
        fused = rrf(dense_pos, sparse_pos)
        cand_pos = sorted(fused, key=lambda i: fused[i], reverse=True)[:CANDIDATE_TOP_K]
        texts = [docs[i]["embed_text"] for i in cand_pos]

        # Print recall stages first (cheap), then each rerank pool size as it lands —
        # the rerank30 figure is the whole point, so flush it the moment it's known.
        print(
            f"[stages r{rep}] embed = {t_embed:6.1f}s · dense = {t_dense:5.2f}s"
            f" · bm25 = {t_bm25:5.2f}s · cand = {len(texts)}",
            flush=True,
        )
        for k in (len(texts), 10, 1):
            t = time.time()
            s._rerank_scores(query, texts[:k])  # type: ignore[attr-defined]
            print(f"[stages r{rep}] rerank{k:<2} = {time.time() - t:6.1f}s", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Pi4 CPU retrieval spike (memory + latency)")
    ap.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    ap.add_argument("--runs", type=int, default=3, help="timed retrieves per domain query")
    ap.add_argument(
        "--stages", action="store_true", help="per-stage timing breakdown instead of e2e runs"
    )
    ap.add_argument(
        "--candidates", type=int, default=30, help="reranker candidate pool (recall↔latency)"
    )
    args = ap.parse_args()

    from core.config import get_settings
    from rag.retrieve import RetrievalStack

    print(f"=== Pi CPU retrieve spike · device={args.device} · fp32 · cand={args.candidates} ===")
    print(f"[baseline]  RSS = {rss_mib():7.0f} MiB")

    t = time.time()
    stack = RetrievalStack(
        get_settings().qdrant_url,
        device=args.device,
        fp16=False,
        candidate_top_k=args.candidates,
    )
    print(
        f"[+stack]    load {time.time() - t:5.1f}s"
        f"  RSS = {rss_mib():7.0f} MiB  peak = {peak_mib():7.0f} MiB"
        f"  (BGE-M3 + reranker + BM25 over {len(stack._docs)} docs)"
    )

    if args.stages:
        # Skip the full ≈3-min warm-up retrieve; a 2-pair rerank + one embed is
        # enough to pay kernel/thread-pool init before the per-stage timing below.
        stack._rerank_scores(QUERIES[0][1], ["warm", "up"])  # type: ignore[attr-defined]
        stack._embed(QUERIES[0][1])  # type: ignore[attr-defined]
        stage_breakdown(stack, QUERIES[0][1], QUERIES[0][0], reps=1)
        print(f"[peak]      process peak RSS = {peak_mib():7.0f} MiB  (Pi total 7.6 GiB)")
        return

    # Warm-up: first call pays tokenizer/thread-pool init; steady state is what
    # an incident actually experiences (the stack is a lazy singleton in rag/server).
    t = time.time()
    stack.retrieve(QUERIES[0][1], QUERIES[0][0])
    print(f"[warm-up]   first retrieve = {time.time() - t:5.1f}s")

    lat: list[float] = []
    for domain, query in QUERIES:
        for _ in range(args.runs):
            t = time.time()
            chunks = stack.retrieve(query, domain)
            dt = time.time() - t
            lat.append(dt)
        top = chunks[0]
        preview = top.text[:90].replace("\n", " ")
        print(
            f"[retrieve]  {domain:<10} last = {dt:5.1f}s  score = {top.score:5.2f}"
            f"  top1: {preview!r}"
        )

    lat.sort()
    n = len(lat)
    print(
        f"[latency]   n={n}  median = {lat[n // 2]:5.1f}s"
        f"  min = {lat[0]:5.1f}s  max = {lat[-1]:5.1f}s"
    )
    print(f"[peak]      process peak RSS = {peak_mib():7.0f} MiB  (Pi total 7.6 GiB)")


if __name__ == "__main__":
    main()
