"""Load versioned prompts from ops/prompts/{agent}/v{n}.md (Hard Constraint #4).

Prompts are never inlined in agent code. To change a prompt, copy v{n}.md to
v{n+1}.md, edit there, and bump the version arg at the agent's call site
(CLAUDE.md prompt-modification workflow). Returns a string.Template so agents
substitute runtime fields ($readings, $anomaly, ...) without clashing with the
JSON braces in the prompt body.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "ops" / "prompts"


def load_prompt(agent: str, version: int = 1) -> Template:
    path = _PROMPTS_DIR / agent / f"v{version}.md"
    return Template(path.read_text(encoding="utf-8"))
