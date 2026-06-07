"""The corrector agent: corrections → a generalized preference block (P1).

``propose_preference_block(corrections, current_block, ...)`` is the generative
step of the per-user learning loop. It asks Gemini to
turn a user's accumulated corrections into a short, **generalized** profile of
their logging style — *category-level rules* ("preworkout carbs run high"), not
per-meal fixes ("less apple") — under a token cap, with a one-line rationale per
rule for observability.

Mirrors ``interpret_feedback.py``:
- Injectable client so tests never hit Vertex (offline + mocked).
- ``response_schema=ProposedBlock`` so Gemini returns schema-valid JSON.
- Fail-soft on every axis (model error, no text, non-JSON, wrong shape) → returns
  ``None`` so the caller keeps the current block unchanged.

The output is *proposed*, never shipped here — the gate decides (P3).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from dietrace.llm.config import GEMINI_MODEL

_PROMPT_PATH = Path(__file__).parent / "corrector_prompt.md"

# Rough words→tokens budget guard (defensive; the prompt also asks for brevity).
_DEFAULT_TOKEN_CAP = 220


class PreferenceRule(BaseModel):
    """One generalized rule in the preference block."""

    rule: str
    rationale: str = ""
    from_feedback: list[int] = []


class ProposedBlock(BaseModel):
    """The corrector's proposed preference block + its per-rule provenance."""

    block_text: str
    rules: list[PreferenceRule] = []


def _format_corrections(corrections: list[dict[str, Any]]) -> str:
    """Render the feedback set (with ids + emphasis) for the prompt."""
    lines = []
    for c in corrections:
        cid = c.get("id", "?")
        weight = float(c.get("weight", 1.0) or 1.0)
        emphasis = f" [emphasis x{weight:g}]" if weight != 1.0 else ""
        meal = c.get("meal_text")
        ctx = f" (on: {meal})" if meal else ""
        lines.append(f"- #{cid}{emphasis}: {c.get('feedback_text', '')}{ctx}")
    return "\n".join(lines) if lines else "(none)"


def _prompt(
    corrections: list[dict[str, Any]],
    current_block: str,
    token_cap: int,
    user_profile: str,
) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return (
        template.replace("{corrections}", _format_corrections(corrections))
        .replace("{current_block}", current_block or "(none yet)")
        .replace("{user_profile}", user_profile.strip() or "(not provided)")
        .replace("{token_cap}", str(token_cap))
    )


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _enforce_cap(text: str, token_cap: int) -> str:
    """Defensive truncation — keep the block under ~token_cap words (≈ tokens)."""
    words = text.split()
    if len(words) <= token_cap:
        return text
    return " ".join(words[:token_cap]).rstrip() + " …"


def _structured_config() -> Any:
    from google import genai

    return genai.types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=ProposedBlock,
    )


def _default_client() -> Any:
    from google import genai

    from dietrace.llm.config import GEMINI_LOCATION, GEMINI_PROJECT

    return genai.Client(vertexai=True, project=GEMINI_PROJECT, location=GEMINI_LOCATION)


def propose_preference_block(
    corrections: list[dict[str, Any]],
    current_block: str = "",
    token_cap: int = _DEFAULT_TOKEN_CAP,
    client: Any | None = None,
    user_profile: str = "",
) -> ProposedBlock | None:
    """Propose an updated preference block from *corrections* via Gemini.

    *corrections* is a list of ``{id, feedback_text, weight, meal_text?}`` (the
    FeedbackLog rows). *user_profile* is the user's freeform "goals + eating
    style" — standing context so the generalized rules reflect who they are, not
    just the meals they've fixed. Returns a :class:`ProposedBlock`, or ``None`` on
    any failure — the caller keeps *current_block* unchanged. The returned block
    is capped to ~``token_cap`` words defensively even if the model overruns.
    """
    if not corrections:
        return None
    if client is None:
        client = _default_client()

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=_prompt(corrections, current_block, token_cap, user_profile),
            config=_structured_config(),
        )
    except Exception:
        return None

    raw_text = getattr(response, "text", None)
    if not raw_text:
        return None

    try:
        payload = json.loads(_strip_fences(raw_text))
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(payload, dict) or "block_text" not in payload:
        return None

    try:
        proposed = ProposedBlock.model_validate(payload)
    except ValidationError:
        return None

    proposed.block_text = _enforce_cap(proposed.block_text, token_cap)
    return proposed
