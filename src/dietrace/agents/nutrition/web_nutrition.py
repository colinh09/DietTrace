"""Grounded web lookup for foods the USDA DB doesn't carry — the fallback path.

The USDA FoodData Central DB is excellent for whole and packaged foods but rarely
carries restaurant meals (a "Five Guys bacon cheeseburger" has no FDC entry, so a
plain DB search resolves it to some *other* chain's cheeseburger). When the
deterministic search can't honor a branded item, the orchestrator falls back here:
one Gemini call **grounded with Google Search** looks up the item's published
nutrition facts and returns them as a synthetic :class:`Food` that flows through
the same ``estimate_portion`` → ``log_entry`` pipeline as a DB hit.

This is the one place the agent reads a number it didn't compute, so it is kept
narrow and fail-soft: the model must return a single serving's macros + that
serving's gram weight, which are normalized to the per-100 g panel the rest of the
pipeline expects; any missing/garbled field degrades to ``None`` (the item is then
skipped or left to its weak DB match) rather than raising. The Gemini client is
injectable so tests never touch the network.
"""

from __future__ import annotations

import json
import math
from typing import Any

from dietrace.agents.nutrition.parse_meal import _strip_fences
from dietrace.llm.config import GEMINI_MODEL
from dietrace.nutrition.models import Food, Nutrient, ServingSize

# (payload key, USDA number code, nutrient name, unit) for each macro/micro the
# grounded lookup may return. Energy (208) is required; the rest are optional so a
# label that omits fiber/sodium/sugar still logs its macros.
_NUTRIENT_SPECS: list[tuple[str, str, str, str]] = [
    ("calories", "208", "Energy", "kcal"),
    ("protein_g", "203", "Protein", "g"),
    ("fat_g", "204", "Total lipid (fat)", "g"),
    ("carb_g", "205", "Carbohydrate, by difference", "g"),
    ("fiber_g", "291", "Fiber, total dietary", "g"),
    ("sodium_mg", "307", "Sodium, Na", "mg"),
    ("sugar_g", "269", "Sugars, total including NLEA", "g"),
]

_PROMPT = """You are a nutrition lookup tool with web search. Find the published \
nutrition facts for ONE standard serving of the food below, using authoritative \
sources (the brand's official site, the USDA, or a reputable nutrition database).

Food: {food}
Brand or restaurant: {brand}

Return ONLY JSON of this exact shape (numbers only, no units in the values):
{{"description": "<brand + food>", "serving_grams": <grams in one serving>, \
"calories": <kcal>, "protein_g": <g>, "fat_g": <g>, "carb_g": <g>, \
"fiber_g": <g or null>, "sodium_mg": <mg or null>, "sugar_g": <g or null>}}

Use the item's standard single serving. If the food is a recognizable dish or \
ingredient (e.g. shakshuka, risotto, pad thai), give your best published or \
typical-recipe estimate — do NOT give up just because an exact label isn't \
published. Only return empty (\
{{"description": "", "serving_grams": null, "calories": null}}) if the food is \
genuinely unrecognizable or gibberish.
"""


def _positive(value: Any) -> bool:
    """True when *value* is a finite, strictly positive number."""
    return isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def web_nutrition(
    food: str, brand: str = "", *, client: Any | None = None, attempts: int = 2
) -> Food | None:
    """Look up *food* (optionally a *brand*'s) nutrition facts via grounded Gemini.

    Returns a synthetic :class:`Food` — per-100 g nutrient panel plus a single
    serving's gram weight — or ``None`` when the lookup yields no usable data. The
    grounded model is non-deterministic and sometimes bails to its empty fallback
    even for a recognizable dish, so a None is **retried** up to *attempts* times
    (cheap, and a retry usually succeeds). The *client* is a ``google.genai``
    client (mocked in tests); when omitted a Vertex client is built lazily.
    """
    try:
        if client is None:
            client = _default_client()
    except Exception:
        # A credentials failure must never crash a meal log (fail-soft).
        return None

    for _ in range(max(1, attempts)):
        food_obj = _lookup_once(client, food, brand)
        if food_obj is not None:
            return food_obj
    return None


def _lookup_once(client: Any, food: str, brand: str) -> Food | None:
    """One grounded lookup attempt; None on any failure or empty result."""
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=_PROMPT.format(food=food, brand=brand or "(none)"),
            config=_grounded_config(),
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
    return _to_food(payload, food, brand)


def _to_food(payload: Any, food: str, brand: str) -> Food | None:
    """Build a synthetic per-100 g :class:`Food` from a serving-sized lookup result.

    The model returns one serving's macros + that serving's grams; each is scaled to
    per 100 g (the panel the pipeline reads) so ``estimate_portion`` can scale it back
    by the logged portion. Returns ``None`` unless the serving weight and energy are
    both present — without them nothing downstream can compute.
    """
    if not isinstance(payload, dict):
        return None
    grams = payload.get("serving_grams")
    if not _positive(grams) or not _positive(payload.get("calories")):
        return None

    nutrients: list[Nutrient] = []
    for key, code, name, unit in _NUTRIENT_SPECS:
        value = payload.get(key)
        if value is None or not isinstance(value, (int, float)) or not math.isfinite(value):
            continue
        if value < 0:
            continue
        nutrients.append(
            Nutrient(code=code, name=name, amount=value / grams * 100.0, unit=unit)
        )

    # Fall back to a brand+food label whenever the model's description isn't a
    # usable string — a non-empty str only. A truthy-but-wrong-type value (a list/
    # dict from garbled JSON) would otherwise reach Food.description (a str field
    # pydantic won't coerce) and raise, crashing the meal log instead of degrading.
    desc = payload.get("description")
    label = (
        desc.strip()
        if isinstance(desc, str) and desc.strip()
        else " ".join(p for p in (brand, food) if p).strip()
    )
    return Food(
        fdc_id=0,  # synthetic: not a USDA food, so no reproducible fdc_id
        description=label or food,
        data_type="web_grounded",
        nutrients=nutrients,
        serving_sizes=[
            ServingSize(
                amount=1.0, unit="serving", gram_weight=float(grams), description="web serving"
            )
        ],
        conversion_factors=None,
    )


def _grounded_config() -> Any:
    """A generate-content config with the Google Search tool enabled (web grounding).

    Lazy import keeps the module credential-free; mock clients in tests ignore the
    config entirely. Structured-output schemas can't be combined with tools on
    Vertex, so the JSON shape is enforced by the prompt and parsed fail-soft.
    """
    from google import genai

    return genai.types.GenerateContentConfig(
        tools=[genai.types.Tool(google_search=genai.types.GoogleSearch())]
    )


def _default_client() -> Any:
    """Build a Vertex Gemini client from config — lazy so imports stay cheap."""
    from google import genai

    from dietrace.llm.config import GEMINI_LOCATION, GEMINI_PROJECT

    return genai.Client(vertexai=True, project=GEMINI_PROJECT, location=GEMINI_LOCATION)
