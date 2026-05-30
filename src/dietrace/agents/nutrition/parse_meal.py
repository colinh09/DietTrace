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
from typing import Any

from pydantic import BaseModel, ValidationError

from dietrace.llm.config import GEMINI_MODEL

_PROMPT = """\
Extract the foods from this meal description into a JSON object.

Return ONLY JSON of the form:
{{"items": [{{"food": "<food name>", "quantity": <number>, "unit": "<unit>"}}]}}

Rules:
- One entry per distinct food.
- "food" is the bare food name (singular, no quantity words).
- "quantity" is a number ("half" -> 0.5, "a"/"an"/none -> 1).
- "unit" is the household measure ("slice", "cup", "each", ...); use "each" \
for whole countable items and "" when there is no natural unit.
- Do not invent foods that are not mentioned.

Meal description:
{text}
"""


class ParsedItem(BaseModel):
    """One food parsed from free text: its name, quantity, and household unit.

    ``quantity`` defaults to 1 and ``unit`` to "" so a bare food name (the model
    omitting either) still yields a usable item for the deterministic tools.
    """

    food: str
    quantity: float = 1.0
    unit: str = ""


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
    """Validate each raw entry into a :class:`ParsedItem`, dropping bad ones."""
    items: list[ParsedItem] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            items.append(ParsedItem.model_validate(entry))
        except ValidationError:
            continue  # missing food, non-numeric quantity, … — skip fail-soft
    return items


def parse_meal(text: str, client: Any | None = None) -> MealParse:
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
        contents=_PROMPT.format(text=text),
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
