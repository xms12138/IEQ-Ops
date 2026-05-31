"""Load + validate IEQ-Bench tasks from `tasks/*.jsonl`.

One JSON object per line (JSONL). Blank lines and `#`-prefixed lines are skipped
so a task file can carry human annotation comments. A malformed line fails loud
with its file:line — a silently dropped task would quietly shrink the benchmark.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from eval.ieq_bench.schema import BenchTask, Capability, Layer

TASKS_DIR = Path(__file__).parent / "tasks"


def load_tasks(
    *,
    capability: Capability | None = None,
    layer: Layer | None = None,
    tasks_dir: Path = TASKS_DIR,
) -> list[BenchTask]:
    """Read every `*.jsonl` under `tasks_dir`, optionally filtered to one
    capability and/or layer. Returns tasks in (filename, line) order so a run is
    reproducible."""
    tasks: list[BenchTask] = []
    for jf in sorted(tasks_dir.glob("*.jsonl")):
        for line_no, raw in enumerate(jf.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                tasks.append(BenchTask.model_validate_json(line))
            except ValidationError as exc:
                raise ValueError(f"{jf.name}:{line_no} invalid BenchTask: {exc}") from exc
    if capability is not None:
        tasks = [t for t in tasks if t.capability == capability]
    if layer is not None:
        tasks = [t for t in tasks if t.layer == layer]
    return tasks
