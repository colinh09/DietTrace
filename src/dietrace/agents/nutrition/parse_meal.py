"""LLM parse of free text into structured meal items.

``parse_meal(text, client)`` is the only inherently generative step of the
nutrition pipeline: it asks Gemini to turn free text ("two eggs, half
an avocado, slice of toast") into a list of ``{food, quantity, unit}`` items
that the deterministic tools downstream — ``search_nutrition``,
``estimate_portion``, ``log_entry`` — then act on. Per the search/calculation
split the model only *parses and orchestrates*; it never invents a
nutrient number a tool can look up.

The model is asked for JSON. Real LLM output is unreliable, so parsing is
fail-soft on every axis: missing response text, non-JSON output, an unexpected
shape, or an individual malformed item all degrade to "drop it" rather than
raising — an empty :class:`MealParse` in the worst case — so the agent loop
keeps running. The Gemini client is injectable for tests; the default is built
lazily so importing this module never requires GCP credentials.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from dietrace.llm.config import GEMINI_MODEL

# The meal-parsing prompt lives in a tracked file so the supervisor can propose
# fixes to it (it is the generative step that drives parse accuracy).
_PROMPT_PATH = Path(__file__).parent / "parse_prompt.md"


def _prompt(text: str, examples: list[dict[str, Any]] | None = None) -> str:
    """Render the parse prompt for *text*, prepending the user's few-shot examples.

    *examples* are this user's past corrections (``{text, foods:[{food, grams}]}``);
    showing the model how they like meals broken down steers similar parses — e.g.
    teaching it not to count a composite dish AND its components.
    """
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return _few_shot_block(examples) + template.replace("{text}", text)


def _few_shot_block(examples: list[dict[str, Any]] | None) -> str:
    """Render the user's learned profile + corrections + standing rules (empty if none).

    Each entry is one of: the generalized **preference block**
    (``{preference_block: "..."}``, the primary personalization signal from the
    learning loop), a worked correction (``{text, foods:[{food, grams}]}``), or a
    standing preference (``{rule: "..."}``) — so the model parses meals the way
    this user eats.
    """
    if not examples:
        return ""
    preference = next(
        (e["preference_block"] for e in examples if e.get("preference_block")), ""
    )
    corrections = [
        e for e in examples if not e.get("rule") and not e.get("preference_block")
    ]
    rules = [e["rule"] for e in examples if e.get("rule")]
    blocks: list[str] = []
    if preference:
        blocks.append(
            "This user's learned logging profile. Apply each rule ONLY when the "
            "current meal matches the rule's stated condition (e.g. a pre-workout "
            "rule applies only to a pre-workout meal); log every other meal "
            "normally, exactly as you would without this profile:\n" + preference
        )
    if corrections:
        lines = [
            "This user has corrected past meals. Match how they break meals into foods "
            "(same items, no double-counting a dish and its components):",
        ]
        for example in corrections:
            foods = ", ".join(f.get("food", "") for f in example.get("foods", []))
            lines.append(f'- "{example.get("text", "")}" → [{foods}]')
        blocks.append("\n".join(lines))
    if rules:
        lines = ["This user has standing preferences — honor them when relevant:"]
        lines.extend(f"- {rule}" for rule in rules)
        blocks.append("\n".join(lines))
    return ("\n\n".join(blocks) + "\n\n") if blocks else ""


class ParsedItem(BaseModel):
    """One food parsed from free text: its name, quantity, and household unit.

    ``quantity`` defaults to 1 and ``unit`` to "" so a bare food name (the model
    omitting either) still yields a usable item for the deterministic tools.
    ``brand`` carries a restaurant/brand qualifier when the user named one ("Five
    Guys", "Chipotle") — the USDA DB rarely has restaurant meals, so a branded
    item routes to the grounded web fallback when USDA can't honor the brand. The
    model stays a clean schema (no validation constraints) because it is also sent
    to Gemini as the structured-output ``response_schema``, which rejects JSON
    Schema keywords like ``exclusiveMinimum``; the positive/finite-quantity guard
    lives in :func:`_coerce_items` instead.
    """

    food: str
    quantity: float = 1.0
    unit: str = ""
    brand: str = ""


class MealParse(BaseModel):
    """The result of :func:`parse_meal`: the items recovered from the text.

    Empty when the model produced nothing usable — parsing is fail-soft, so an
    empty list is the worst case rather than an exception.
    """

    items: list[ParsedItem] = []


def _strip_fences(text: str) -> str:
    """Drop a surrounding markdown code fence (```json … ```) if present."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    # Drop the opening fence (optionally tagged ```json) and a closing fence.
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _raw_items(payload: Any) -> list[Any]:
    """Pull the item list out of either ``{"items": [...]}`` or a bare ``[...]``."""
    if isinstance(payload, dict):
        items = payload.get("items", [])
        return items if isinstance(items, list) else []
    if isinstance(payload, list):
        return payload
    return []


def _coerce_items(raw: list[Any]) -> list[ParsedItem]:
    """Validate each raw entry into a :class:`ParsedItem`, dropping bad ones.

    A real portion is positive and finite, so a non-positive or NaN/inf quantity
    drops the item fail-soft rather than poisoning the deterministic math (a NaN
    propagates into totals; a negative quantity subtracts). The guard is here
    rather than on the model so the model stays a clean Gemini response schema.
    """
    items: list[ParsedItem] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            item = ParsedItem.model_validate(entry)
        except ValidationError:
            continue  # missing food, non-numeric quantity, … — skip fail-soft
        if not math.isfinite(item.quantity) or item.quantity <= 0:
            continue  # non-positive / non-finite portion — skip fail-soft
        items.append(item)
    return items


def parse_meal(
    text: str, client: Any | None = None, examples: list[dict[str, Any]] | None = None
) -> MealParse:
    """Parse free-text *text* into structured meal items via Gemini.

    *client* is a ``google.genai`` client (a mock in tests); when omitted a
    Vertex client is built lazily. The live default path asks Gemini for
    structured output (``responseMimeType`` + ``responseSchema=MealParse``) so the
    model returns schema-valid JSON directly. Returns a :class:`MealParse` whose
    ``items`` are the foods the model recovered. Any failure to get well-formed
    JSON — no text, non-JSON, wrong shape — degrades to an empty parse rather than
    raising.
    """
    if client is None:
        client = _default_client()

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=_prompt(text, examples),
        config=_structured_config(),
    )

    raw_text = getattr(response, "text", None)
    if not raw_text:
        return MealParse()

    try:
        payload = json.loads(_strip_fences(raw_text))
    except (json.JSONDecodeError, ValueError):
        return MealParse()

    return MealParse(items=_coerce_items(_raw_items(payload)))


def _structured_config() -> Any:
    """Build the structured-output config that pins Gemini to schema-valid JSON.

    Lazy import so this module stays import-cheap and credential-free; mock
    clients in tests ignore the config and still return their canned text.
    """
    from google import genai

    return genai.types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=MealParse,
    )


def _default_client() -> Any:
    """Build a Vertex Gemini client from config — lazy so imports stay cheap."""
    from google import genai

    from dietrace.llm.config import GEMINI_LOCATION, GEMINI_PROJECT

    return genai.Client(vertexai=True, project=GEMINI_PROJECT, location=GEMINI_LOCATION)
