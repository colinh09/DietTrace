"""Deterministic portion→grams estimation.

``estimate_portion(food, quantity, unit)`` turns a household portion ("1 egg",
"half an avocado", "1 slice toast") into a gram weight without ever asking the
LLM for a number — the search/calculation split keeps generative steps
away from the math. Resolution is tried in descending order of trust:

1. an explicit **mass** unit (g, oz, lb …) is converted directly;
2. a unit that matches one of the food's **serving sizes** is scaled by quantity;
3. a **whole-item** count (the food's own name, or "each"/"whole"/…) uses the
   food's primary serving size;
4. otherwise a generic **fallback table** of household measures is consulted.

Each result reports its ``source`` and a ``confidence`` in [0, 1] so the eval
``portion_error`` surface and the supervisor can see how firm the number is. An
unresolvable portion returns ``grams=None`` at zero confidence rather than
raising, keeping the agent loop fail-soft.
"""

from __future__ import annotations

from pydantic import BaseModel

from dietrace.nutrition.models import Food

# Mass units → grams per unit. The agent reads/scales nutrients per 100 g, so a
# mass portion needs no food context and is the most trustworthy source.
_MASS_GRAMS: dict[str, float] = {
    "g": 1.0,
    "gram": 1.0,
    "grams": 1.0,
    "mg": 0.001,
    "kg": 1000.0,
    "oz": 28.3495,
    "ounce": 28.3495,
    "lb": 453.592,
    "pound": 453.592,
}

# Generic household measures, consulted only when the food's own serving sizes
# don't resolve the unit — a coarse guess, hence the lower confidence.
_FALLBACK_GRAMS: dict[str, float] = {
    "cup": 240.0,
    "tablespoon": 15.0,
    "tbsp": 15.0,
    "teaspoon": 5.0,
    "tsp": 5.0,
    "slice": 28.0,
    "piece": 50.0,
    "egg": 50.0,
    "handful": 30.0,
}

# Units that denote a whole piece of the food rather than a named measure.
_WHOLE_ITEM_WORDS = frozenset({"", "whole", "each", "piece", "item", "unit", "serving"})

_SERVING_CONFIDENCE = 0.9
_WHOLE_ITEM_CONFIDENCE = 0.8
_FALLBACK_CONFIDENCE = 0.5


class PortionEstimate(BaseModel):
    """A resolved portion: ``grams`` plus how it was reached.

    ``grams`` is None when the unit could not be resolved. ``source`` names the
    strategy that produced it ("mass", "serving_size", "whole_item",
    "fallback_table", or "unknown") and ``confidence`` is in [0, 1].
    """

    grams: float | None
    source: str
    confidence: float


def _singular(word: str) -> str:
    """Lower-case *word* and drop a single trailing plural "s" for matching."""
    word = word.strip().lower()
    if len(word) > 1 and word.endswith("s"):
        return word[:-1]
    return word


def _matches_whole_item(food: Food, unit: str) -> bool:
    """True when *unit* names a whole piece of *food* (its name or a count word)."""
    if unit in _WHOLE_ITEM_WORDS:
        return True
    target = _singular(unit)
    if not target:
        return True
    tokens = {_singular(token) for token in food.description.replace(",", " ").split()}
    return target in tokens


def estimate_portion(food: Food, quantity: float, unit: str | None = None) -> PortionEstimate:
    """Estimate the gram weight of *quantity* *unit* of *food*.

    Tries mass → serving size → whole-item → fallback table, returning the first
    that resolves. ``unit`` is matched case- and plural-insensitively. The
    result always carries a ``source`` and ``confidence``; an unresolved unit
    yields ``grams=None`` rather than raising.
    """
    normalized = (unit or "").strip().lower()
    key = _singular(normalized)

    # 1. Explicit mass unit — no food context needed, fully trusted.
    if key in _MASS_GRAMS:
        return PortionEstimate(
            grams=quantity * _MASS_GRAMS[key], source="mass", confidence=1.0
        )

    # 2. A serving size whose unit matches — scale its per-unit weight.
    for serving in food.serving_sizes:
        if serving.amount and _singular(serving.unit) == key:
            per_unit = serving.gram_weight / serving.amount
            return PortionEstimate(
                grams=quantity * per_unit,
                source="serving_size",
                confidence=_SERVING_CONFIDENCE,
            )

    # 3. A whole-item count — use the food's primary serving size.
    if food.serving_sizes and _matches_whole_item(food, normalized):
        primary = food.serving_sizes[0]
        if primary.amount:
            per_item = primary.gram_weight / primary.amount
            return PortionEstimate(
                grams=quantity * per_item,
                source="whole_item",
                confidence=_WHOLE_ITEM_CONFIDENCE,
            )

    # 4. Generic fallback table — a coarse household-measure guess.
    if key in _FALLBACK_GRAMS:
        return PortionEstimate(
            grams=quantity * _FALLBACK_GRAMS[key],
            source="fallback_table",
            confidence=_FALLBACK_CONFIDENCE,
        )

    return PortionEstimate(grams=None, source="unknown", confidence=0.0)
