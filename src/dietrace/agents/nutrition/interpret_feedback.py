"""Free-form feedback interpreter: natural language → StructuredFeedback.

``interpret_feedback(meal_context, feedback_text, client)`` is the generative
step of the feedback loop: it asks Gemini to turn a user's comment about a
logged meal ("the fries are double what I'd eat", "from now on this is my
preworkout, aim for 80g carbs") into a typed action that the deterministic
``apply_feedback`` function can execute without any further LLM involvement.

Mirrors ``agents/nutrition/parse_meal.py``:
- Injectable client so tests never hit Vertex (offline + mocked).
- ``response_schema=StructuredFeedback`` so Gemini returns schema-valid JSON.
- Fail-soft on every axis: model exception, missing text, non-JSON, wrong
  shape — all return ``None`` rather than raising, so the caller can fall back
  gracefully.

``apply_feedback(meal_items, feedback)`` executes the structured action
deterministically (no LLM involvement):
- ``portion_adjust``: scale the target food's grams by the adjustment multiplier.
- ``remove_item``: drop the target food from the list.
- ``add_item``: append a new item with the given grams.
- ``standing_rule``: no modification to this meal's items (the rule is for
  future meals; the caller decides where to store it).
- Any other kind or a ``None`` feedback: return items unchanged (fail-soft).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from dietrace.llm.config import GEMINI_MODEL

_PROMPT_PATH = Path(__file__).parent / "feedback_prompt.md"


class StructuredFeedback(BaseModel):
    """The structured interpretation of a user's free-form meal feedback.

    ``kind`` is the action type:
    - ``portion_adjust``: change a food's portion. Use ``target_grams`` when the
      user gives an absolute amount ("about 30 grams", "two tablespoons");
      use ``adjustment`` (a multiplier) when they give a relative amount
      ("half", "a third", "double"). Absolute wins if both are present.
    - ``remove_item``: drop a food that was not eaten.
    - ``add_item``: append a food that was eaten but not logged
      (``adjustment`` = grams, or None if unknown).
    - ``standing_rule``: a preference applying to future meals of this type
      (``adjustment`` = gram target if given).

    ``target_food`` identifies the food the action applies to; empty for
    ``standing_rule``. ``adjustment`` is a multiplier for ``portion_adjust``
    and a gram weight for ``add_item``; ``None`` when not applicable.
    ``target_grams`` is an absolute gram target for ``portion_adjust``; ``None``
    when the user gave a relative amount instead.
    ``scope`` is one of ``this_food``, ``this_meal``, or ``meal_type``.
    ``rationale`` is a plain-English explanation of the user's intent.
    """

    kind: str
    target_food: str = ""
    adjustment: float | None = None
    target_grams: float | None = None
    scope: str = "this_meal"
    rationale: str = ""


def _prompt(meal_context: dict[str, Any], feedback_text: str) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    items = meal_context.get("items", [])
    items_text = ", ".join(
        f"{it.get('food', '?')} ({it.get('grams', 0):.0f}g)" for it in items
    )
    return (
        template.replace("{meal_items}", items_text or "(no items)")
        .replace("{feedback_text}", feedback_text)
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


def _structured_config() -> Any:
    from google import genai

    return genai.types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=StructuredFeedback,
    )


def _default_client() -> Any:
    from google import genai

    from dietrace.llm.config import GEMINI_LOCATION, GEMINI_PROJECT

    return genai.Client(vertexai=True, project=GEMINI_PROJECT, location=GEMINI_LOCATION)


def interpret_feedback(
    meal_context: dict[str, Any],
    feedback_text: str,
    client: Any | None = None,
) -> StructuredFeedback | None:
    """Parse free-form *feedback_text* into a :class:`StructuredFeedback` via Gemini.

    *meal_context* is a dict with at minimum an ``items`` key (list of
    ``{"food": str, "grams": float}``). *client* is a ``google.genai`` client
    (a mock in tests); when omitted a Vertex client is built lazily.

    Returns ``None`` on any failure (model exception, no text, non-JSON, wrong
    schema) — the caller should treat ``None`` as "no action" and leave the
    meal unchanged.
    """
    if client is None:
        client = _default_client()

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=_prompt(meal_context, feedback_text),
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

    if not isinstance(payload, dict) or "kind" not in payload:
        return None

    try:
        return StructuredFeedback.model_validate(payload)
    except ValidationError:
        return None


def apply_feedback(
    meal_items: list[dict[str, Any]],
    feedback: StructuredFeedback | None,
) -> list[dict[str, Any]]:
    """Deterministically apply *feedback* to *meal_items*.

    Returns a new list of items with the action applied. Returns *meal_items*
    unchanged when *feedback* is ``None`` or has an unrecognised kind
    (fail-soft). Does not raise; the caller is always left with a valid list.
    """
    if feedback is None:
        return meal_items

    if feedback.kind == "portion_adjust":
        return _apply_portion_adjust(meal_items, feedback)
    if feedback.kind == "remove_item":
        return _apply_remove_item(meal_items, feedback)
    if feedback.kind == "add_item":
        return _apply_add_item(meal_items, feedback)
    return meal_items


# Sane caps so a degenerate / injected LLM number can't poison a meal's totals.
_MAX_MULTIPLIER = 20.0
_MAX_ADD_GRAMS = 5000.0


def _finite_or_none(value: float | None) -> float | None:
    """Return *value* if it is a finite number, else None — a non-finite LLM-supplied
    number (NaN/Infinity) is treated as not given rather than clamped to a cap.
    """
    if value is None or not math.isfinite(value):
        return None
    return value


def _target_indices(items: list[dict[str, Any]], target: str) -> set[int]:
    """Indices of items matching *target*. Prefer exact (case-insensitive) matches;
    fall back to substring ONLY when it matches exactly one item — so "rice" never
    silently hits both "fried rice" and "brown rice cake" and corrupts the wrong food.
    """
    if not target:
        return set()
    t = target.strip().lower()
    exact = {i for i, it in enumerate(items) if it.get("food", "").strip().lower() == t}
    if exact:
        return exact
    subs = {i for i, it in enumerate(items) if t in it.get("food", "").lower()}
    return subs if len(subs) == 1 else set()


def _apply_portion_adjust(
    items: list[dict[str, Any]], feedback: StructuredFeedback
) -> list[dict[str, Any]]:
    if not feedback.target_food:
        return items
    # json.loads admits the literal NaN/Infinity and a pydantic float field accepts
    # them, so a garbled LLM number could reach here; drop a non-finite value rather
    # than letting min/max clamp it silently to the MAX cap (poisoning the grams).
    target_grams = _finite_or_none(feedback.target_grams)
    adjustment = _finite_or_none(feedback.adjustment)
    # An absolute gram target ("about 30 grams") sets the portion directly;
    # otherwise fall back to the relative multiplier ("half", "a third").
    absolute = target_grams is not None
    if not absolute and adjustment is None:
        return items
    idxs = _target_indices(items, feedback.target_food)
    result = []
    for i, item in enumerate(items):
        if i in idxs:
            item = dict(item)
            if absolute:
                item["grams"] = max(0.0, min(_MAX_ADD_GRAMS, target_grams))
            else:
                multiplier = max(0.0, min(_MAX_MULTIPLIER, adjustment))
                item["grams"] = max(0.0, item.get("grams", 0.0) * multiplier)
        result.append(item)
    return result


def _apply_remove_item(
    items: list[dict[str, Any]], feedback: StructuredFeedback
) -> list[dict[str, Any]]:
    if not feedback.target_food:
        return items
    idxs = _target_indices(items, feedback.target_food)
    return [item for i, item in enumerate(items) if i not in idxs]


def _apply_add_item(
    items: list[dict[str, Any]], feedback: StructuredFeedback
) -> list[dict[str, Any]]:
    # A non-finite gram weight (NaN/Infinity) degrades to 0 g (unknown), not the cap.
    grams = max(0.0, min(_MAX_ADD_GRAMS, _finite_or_none(feedback.adjustment) or 0.0))
    new_item = {"food": feedback.target_food, "grams": grams}
    return list(items) + [new_item]
