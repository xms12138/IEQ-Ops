# Figures

Diagrams and photographs referenced from the top-level README, generated with
AI-assisted charting from the JSON results in [`eval/results/`](../../eval/results/)
or drawn/photographed directly. PNG is the display copy; SVG (where present) is
the vector source.

| Figure | What it shows |
|---|---|
| `fig-01-problem-sdc.png` | The problem framing: invisible risk → cognitive load → hallucination risk → passive, memory-less tooling |
| `fig-02-system-architecture.png` | The three LangGraphs + shared subgraph over Postgres/Qdrant, end to end |
| `fig-03-deployment-photos.jpg` | The physical exhibit unit: kiosk front, 3D-printed enclosure rear, sensor face |
| `fig-04-sensing-pipeline.png` | MKR1010 → MQTT → Mosquitto → Postgres data flow |
| `fig-05-rag-pipeline.png` | BM25 + dense retrieval → reranker → contextual-prefix pipeline |
| `fig-06-eval-protocol.png` | Evaluation protocol: conditions × metrics × dual LLM-judge × deterministic anchors |
| `fig-07-real-sensor-trace.png` | One full day of real CO₂/temp/RH/light/sound readings from the deployed hardware |
| `fig-08-sim-vs-real.png` | Simulator-vs-real calibration check, per channel (RMSE / r) |
| `fig-09-closedbook-prescreen.png` | Closed-book accuracy per question type (screens out questions the base model already knows) |
| `fig-10-h1-ablation.png` | H1: no-RAG vs. RAG-grounded accuracy |
| `fig-11-retrieval-metrics.png` | Recall@k / nDCG@k across the retrieval pipeline stages |
| `fig-12-rag-pipeline-ablation.png` | Per-stage contribution to recall@5 (reranker jump, contextual-prefix regression) |
| `fig-13-recall-accuracy-lift.png` | Plan-level recall lift from episodic memory, by domain |
| `fig-14-plan-sharpening-example.png` | A worked example: the same incident's plan with memory recall off vs. on |
| `fig-15-detection-coverage.png` | Proactive vs. reactive incident-detection coverage |
| `fig-16-lead-time.png` | Detection lead-time distribution |
| `fig-17-raw-vs-nl.png` | Raw multi-sensor readings vs. the system's natural-language diagnosis / butler answer, with kiosk screenshots |
| `fig-18-judge-agreement.png` | Inter-judge agreement between the two LLM judges and a deterministic grader |
| `fig-19-edge-retrieval-breakdown.png` | Where retrieval latency goes on a Raspberry Pi 4 CPU |
| `fig-20-edge-candidate-latency.png` | Candidate-pool size vs. reranking latency on-device |
| `fig-21-closed-loop-replan.png` | A traced incident where the critic rejects a diagnosis and the loop fails safe |
| `fig-22-memory-macrolift.png` | Memory-ablation macro-lift across iterations |
| `fig-23-diagnosis-level-lift.png` | H2a: diagnosis-level accuracy, memory off vs. on |
| `fig-24-memory-specificity.png` | Negative control: false-recall rate on novel, non-recurring incidents |
| `fig-25-closed-loop-success.png` | Full closed-loop run: autonomy-tier outcomes across domains |
| `fig-26-ieq-bench-aggregate.png` | IEQ-Bench pass rate by capability layer |
| `fig-27-kiosk-incident-lifecycle.png` | One incident's lifecycle as shown on the kiosk UI |
| `fig03-device-*.jpg`, `fig17-kiosk-*.jpg` | Source photographs composited into fig-03 / fig-17 |
| `fig28-presenter-at-exhibition.jpg` | Presenting IEQ-Ops in person at the CASA end-of-year show |
| `fig29-node-closeup.jpg` | Close-up of the node: touchscreen, carry handle, USB conferencing speakerphone for the voice butler |
