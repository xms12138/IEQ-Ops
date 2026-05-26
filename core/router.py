"""Per-node LLM router — implements ops/llm_routing.md.

Routing is per LangGraph node, not per agent (CLAUDE.md Principle #7). Each node
maps to a capability tier; the tier maps to a concrete DeepSeek model plus one
fallback. On exhaustion the caller is expected to raise a Tier 3 incident
("Planner offline, manual triage required") — the router never silently drops work.

ACTIVE OVERRIDES (ops/llm_routing.md header, 2026-05-25):
  (A) DeepSeek-V3 retired upstream -> REASONING tier = deepseek-v4-pro (permanent).
  (B) Dev-phase: LOCAL-tier nodes (#1 monitor, #4d rewrite, #5 critic, #6 verifier)
      run on deepseek-v4-flash instead of Qwen3-8B. MUST revert to local before
      Phase 6 (breaches Hard Constraint #1 in the monitoring hot path — accepted
      in dev only). The local client is therefore not wired here yet.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

# TracedOpenAI is langfuse.openai's drop-in client: it traces every completion
# (model, tokens_in/out, latency) to LangFuse — the single point all LLM calls pass,
# exactly where the CLAUDE.md per-invocation log contract belongs. It ships no
# py.typed, so it's bound to the real OpenAI type below to keep the router fully
# type-checked (langfuse.* is ignore_missing_imports in pyproject).
from langfuse.openai import OpenAI as TracedOpenAI
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from core.config import Settings, get_settings
from core.logging import get_logger

log = get_logger("router")


class ModelTier(StrEnum):
    REASONING = "reasoning"  # deepseek-v4-pro — multi-fact induction, causal reasoning
    FAST = "fast"  # deepseek-v4-flash — decompose/grade/generate, conversational
    LOCAL = "local"  # Qwen3-8B in prod; flash in dev (override B)


# Node -> tier. Keys are "<agent>.<node>". Numbers reference ops/llm_routing.md.
NODE_TIERS: dict[str, ModelTier] = {
    "monitor.scan": ModelTier.LOCAL,  # #1  dev->flash; revert pre-Phase 6
    "planner.plan": ModelTier.REASONING,  # #3
    "specialist.decompose": ModelTier.FAST,  # #4a
    "specialist.grade": ModelTier.FAST,  # #4c  mandatory cloud — never local (#11)
    "specialist.rewrite": ModelTier.LOCAL,  # #4d  dev->flash
    "specialist.generate": ModelTier.FAST,  # #4e  mandatory cloud — never local (#11)
    "critic.validate": ModelTier.LOCAL,  # #5   numeric local; inductive escalates at call site
    "verifier.check": ModelTier.LOCAL,  # #6
    "reflector.semantic": ModelTier.REASONING,  # #7   mandatory pro — never local (#12)
    "reflector.procedural": ModelTier.REASONING,  # #8   mandatory pro — never local (#12)
    "conversational.respond": ModelTier.FAST,  # #9  escalate to pro on low conf (call site)
}

# Transient cloud failures that justify trying the fallback model.
_RETRYABLE = (APITimeoutError, APIConnectionError)


class RouterExhausted(RuntimeError):
    """Primary and fallback both failed. Caller should raise a Tier 3 incident."""


class Router:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: OpenAI = TracedOpenAI(
            api_key=self.settings.deepseek_api_key,
            base_url=self.settings.deepseek_base_url,
        )

    def _tier_models(self, tier: ModelTier) -> tuple[str, str]:
        """(primary, fallback) model names for a tier, honouring the dev override."""
        pro = self.settings.deepseek_model_pro
        flash = self.settings.deepseek_model_flash
        if tier is ModelTier.REASONING:
            return pro, flash  # #3/#7/#8: pro -> retry once on flash -> Tier 3
        if tier is ModelTier.FAST:
            return flash, pro  # flash -> escalate to pro
        # LOCAL
        if self.settings.is_dev:
            return flash, pro  # override B: dev runs local nodes on flash
        raise NotImplementedError(
            "Local Qwen3-8B client not wired yet — required before Phase 6 (override B revert)."
        )

    def resolve(self, node: str) -> tuple[str, str]:
        """Return (primary_model, fallback_model) for a node."""
        try:
            tier = NODE_TIERS[node]
        except KeyError as exc:
            raise KeyError(f"unknown routing node {node!r}; add it to NODE_TIERS") from exc
        return self._tier_models(tier)

    def complete(self, node: str, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Chat-complete for a node with one fallback. Raises RouterExhausted on total failure."""
        primary, fallback = self.resolve(node)
        for attempt, model in enumerate((primary, fallback)):
            try:
                resp = self._client.chat.completions.create(
                    model=model,
                    messages=messages,  # type: ignore[arg-type]
                    **kwargs,
                )
                return resp.choices[0].message.content or ""
            except _RETRYABLE as exc:
                log.warning("route_retry", node=node, model=model, attempt=attempt, error=str(exc))
            except APIStatusError as exc:
                if exc.status_code < 500:
                    raise  # client error (bad request / auth) — don't burn the fallback
                log.warning(
                    "route_retry", node=node, model=model, attempt=attempt, status=exc.status_code
                )
        raise RouterExhausted(f"both models failed for node {node!r} ({primary} -> {fallback})")
