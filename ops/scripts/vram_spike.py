"""6 GB VRAM coexistence spike — TECH_STACK.md Phase 0 item.

Measures, on the real RTX 3060 (6 GB, shared between Windows and WSL2), whether
BGE-M3 + bge-reranker-v2-m3 can stay resident on the GPU, and at what latency the
CPU fallback (the strategy douluo already uses) runs the retrieve workload.

These two local embedders are the only thing dev-phase needs on the GPU, because
routing override B sends Qwen to cloud flash until Phase 6. Qwen3-8B's own VRAM
(via Windows ollama) is sampled separately by the shell — see the runbook at the
bottom — because it lives in a different process/runtime.

Run both, compare:
    cd ~/projects/rag/douluo            # borrow its torch+cu121 venv
    uv run python ~/projects/dissertation/ops/scripts/vram_spike.py --device cpu
    uv run python ~/projects/dissertation/ops/scripts/vram_spike.py --device cuda --half

Reranker is driven via plain transformers (AutoModelForSequenceClassification),
not sentence-transformers CrossEncoder or FlagReranker — both high-level wrappers
break against this venv's transformers/tokenizer versions. The manual path is the
most portable. Reads the shared HF cache (BAAI/bge-m3, BAAI/bge-reranker-v2-m3).
"""

from __future__ import annotations

import argparse
import subprocess
import time

EMBED_MODEL = "BAAI/bge-m3"
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"

# A realistic IEQ retrieve workload: one diagnosis query against a candidate pool
# the reranker would receive after BM25+dense fusion (douluo uses CANDIDATE_TOP_K=30).
QUERY = "室内 CO2 浓度持续超过 1000 ppm,应如何处置并恢复到合规范围?"
DOCS = [
    "ASHRAE 62.1 规定办公空间每人最小新风量为 8.5 L/s,CO2 可作为通风是否充足的间接指标。",
    "当 CO2 浓度超过 1000 ppm 时,应提高机械通风量或开窗,直至浓度回落至 800 ppm 以下。",
    "WELL v2 Air 概念要求室内 CO2 不超过室外 +800 ppm,并对高占用空间提出动态通风要求。",
    "EN 16798-1 将 CO2 增量分级,Category II 对应室外 +800 ppm 的设计目标。",
    "新风系统的响应延迟通常为 10–20 分钟,验证干预效果时应预留足够的稳定时间窗。",
    "DHT22 测得的温湿度异常与 CO2 超标可能同源于通风不足,需结合多传感器交叉判断。",
    "夜间无人时段 CO2 自然回落,清晨复占用后浓度快速上升是典型的通风不足曲线。",
    "提高新风阀开度 20% 后,中等占用房间的 CO2 一般在 15 分钟内下降 150–300 ppm。",
] * 4  # → 32 候选,贴近 reranker 的真实输入规模


def gpu_used_mib() -> int:
    """Physical-card used VRAM in MiB (captures Windows desktop + ollama too)."""
    out = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"]
    )
    return int(out.decode().strip().splitlines()[0])


def main() -> None:
    ap = argparse.ArgumentParser(description="6GB VRAM coexistence spike")
    ap.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    ap.add_argument("--half", action="store_true", help="fp16 on GPU (deployment precision)")
    args = ap.parse_args()
    dev, half = args.device, args.half and args.device == "cuda"

    import torch
    from sentence_transformers import SentenceTransformer
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    print(f"=== VRAM spike · device={dev} · fp16={half} ===")
    print(f"[baseline]            physical GPU used = {gpu_used_mib():>5} MiB")

    # ---- BGE-M3 embedder (force safetensors: torch<2.6 refuses .bin, CVE-2025-32434) ----
    t = time.time()
    embedder = SentenceTransformer(EMBED_MODEL, device=dev, model_kwargs={"use_safetensors": True})
    if half:
        embedder = embedder.half()
    print(f"[+BGE-M3]   load {time.time() - t:4.1f}s  physical GPU used = {gpu_used_mib():>5} MiB")

    # ---- reranker via plain transformers (only safetensors present → no CVE block) ----
    t = time.time()
    rr_tok = AutoTokenizer.from_pretrained(RERANKER_MODEL)
    rr_model = (
        AutoModelForSequenceClassification.from_pretrained(
            RERANKER_MODEL, torch_dtype=(torch.float16 if half else torch.float32)
        )
        .to(dev)
        .eval()
    )
    print(f"[+reranker] load {time.time() - t:4.1f}s  physical GPU used = {gpu_used_mib():>5} MiB")

    @torch.no_grad()
    def rerank(pairs: list[list[str]]) -> list[float]:
        inp = rr_tok(
            [p[0] for p in pairs],
            [p[1] for p in pairs],
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        ).to(dev)
        return rr_model(**inp).logits.view(-1).float().tolist()

    # Warm up (CUDA context / kernels), then time the steady-state retrieve.
    pairs = [[QUERY, d] for d in DOCS]
    embedder.encode([QUERY], normalize_embeddings=True)
    rerank(pairs[:2])

    t = time.time()
    embedder.encode([QUERY], normalize_embeddings=True)
    enc_ms = (time.time() - t) * 1000

    t = time.time()
    rerank(pairs)
    rr_ms = (time.time() - t) * 1000

    print(f"[latency]   BGE-M3 encode 1 query     = {enc_ms:5.0f} ms")
    print(f"[latency]   rerank {len(pairs):>2} (query,doc) pairs = {rr_ms:5.0f} ms")
    print(f"[latency]   retrieve total            = {enc_ms + rr_ms:5.0f} ms  (budget <500 ms)")
    print(
        f"[peak]                physical GPU used = {gpu_used_mib():>5} MiB  (card total 6144 MiB)"
    )


if __name__ == "__main__":
    main()

# --- Ollama qwen3:8b VRAM runbook (Qwen lives in Windows ollama, sampled here) ---
# 1. Force-load + pin:
#      curl -s http://localhost:11434/api/generate \
#        -d '{"model":"qwen3:8b","prompt":"hi /no_think","keep_alive":"5m","stream":false}' \
#        >/dev/null
# 2. Physical-card VRAM while resident + ollama's own accounting:
#      nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits
#      curl -s http://localhost:11434/api/ps   # compare size vs size_vram → CPU offload
# Measured 2026-05-25: resident = 5638/6144 MiB; size 6.6GB, size_vram 4.5GB
# → Qwen3-8B already CPU-offloads ~2.1GB to fit 6GB. No room for any co-resident model.
