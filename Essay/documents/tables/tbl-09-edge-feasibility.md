**Table 9. Edge-deployment feasibility of the closed-loop retrieval stack on a Raspberry Pi 4 (8 GB).**
Source: measured — `ops/scripts/{vram_spike,pi_retrieve_spike}.py`, DEVLOG P-001 / P-023.

| Configuration | End-to-end retrieval | Peak RAM | Note |
|---|---|---|---|
| Dev GPU resident (Qwen3-8B) | CPU retrieve 3.76 s | 5.6 GB VRAM | CPU path overruns the 500 ms budget 7.5× → GPU mandatory on dev box |
| Pi 4 CPU, candidate pool = 30 (default) | **189 s** | 3.8–4.0 GiB, **zero swap** | reranker = 187 s ≈ **99%** of the time (~6 s/candidate, linear) |
| Pi 4 CPU, candidate pool = 5 (tuned) | **24.4 s** | ~3.5 GiB | **7.7× speed-up**; weights mmap'd (safetensors), load peak only 1.1 GiB |

**Speed-up levers tested (only one worked):** cutting the candidate pool ✓ (linear); `max_length 512→256` ✗ (chunks ≈125 tokens, dynamic padding never hit the 512 cap); multithreading already saturated (load 3.97/4 cores).

**Degradation boundary (stated honestly):** at candidate = 5 == `FINAL_TOP_K`, the reranker degenerates to "rank the 5 given" rather than selecting from a large pool; airquality top-1 drifts toward a ventilation clause instead of the CO₂ threshold. The chosen operating point trades a small precision loss for a 7.7× latency win, acceptable because the closed loop fires only occasionally.
