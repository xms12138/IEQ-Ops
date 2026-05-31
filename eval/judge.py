"""LLM-as-judge — scores the dimensions deterministic metrics can't: groundedness,
plan quality, end-to-end answer text.

Starts on deepseek-v4-flash (the only key configured). `model` is a constructor
parameter and the call site is `Judge.score(...)`, so swapping to the GPT-4o +
Claude Sonnet 4.6 dual-judge later is a wiring change, not a rewrite — build two
Judge instances and average, the scorer signature is unchanged.

The judge prompt HARD-CODES "only compare to expected, do not use prior knowledge"
(ops/llm_routing.md #11). Without it, judges leak world knowledge into partial
credit and the benchmark stops measuring the system.

Returns the same `(passed, score, detail)` shape as eval/metrics.py so the runner
treats deterministic and LLM scorers identically.
"""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI, OpenAIError

from core.config import get_settings
from core.logging import get_logger

log = get_logger("judge")

# deepseek v4 returns reasoning_content; disable thinking for stable JSON + speed.
# DEEPSEEK-SPECIFIC — drop this extra_body when the judge moves to GPT-4o / Claude.
_NO_THINK: dict[str, Any] = {"thinking": {"type": "disabled"}}

_SYSTEM = (
    "You are a strict evaluation judge for an indoor-environmental-quality (IEQ) "
    "operations system.\n"
    "Score the CANDIDATE answer ONLY against the EXPECTED reference and the RUBRIC.\n\n"
    "HARD RULES:\n"
    "- Compare ONLY to EXPECTED. Do NOT use prior knowledge or world facts to award "
    "or deny credit.\n"
    "- A candidate claim that EXPECTED does not support earns no credit, even if it "
    "sounds correct.\n"
    "- Be terse and decisive.\n\n"
    'Output STRICT JSON only: {"verdict": "hit" | "partial" | "miss", '
    '"score": <0.0-1.0>, "reason": "<one sentence>"}'
)


class Judge:
    """One judge model. Construct with a different `model`/`client` for the future
    dual-judge; the scorer interface stays identical."""

    def __init__(self, model: str | None = None, client: OpenAI | None = None) -> None:
        s = get_settings()
        self.model = model or s.deepseek_model_flash
        self.client = client or OpenAI(api_key=s.deepseek_api_key, base_url=s.deepseek_base_url)

    def score(
        self, candidate: str, expected: str, rubric: str = ""
    ) -> tuple[bool, float, dict[str, Any]]:
        user = (
            f"RUBRIC:\n{rubric or '(treat EXPECTED as the rubric)'}\n\n"
            f"EXPECTED:\n{expected}\n\n"
            f"CANDIDATE:\n{candidate}"
        )
        try:
            raw = (
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user", "content": user},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.0,
                    extra_body=_NO_THINK,
                )
                .choices[0]
                .message.content
                or "{}"
            )
            data = json.loads(raw)
            verdict = str(data.get("verdict", "miss"))
            score = float(data.get("score", 1.0 if verdict == "hit" else 0.0))
            return (
                verdict == "hit",
                round(max(0.0, min(1.0, score)), 3),
                {
                    "verdict": verdict,
                    "reason": str(data.get("reason", "")),
                    "judge_model": self.model,
                },
            )
        except (OpenAIError, json.JSONDecodeError, ValueError, KeyError) as exc:
            log.warning("judge_failed", error=str(exc), model=self.model)
            return False, 0.0, {"verdict": "error", "reason": str(exc), "judge_model": self.model}
