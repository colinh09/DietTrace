"""Deterministic portion→grams estimation.

``estimate_portion(food, quantity, unit)`` turns a household portion ("1 egg",
"half an avocado", "1 slice toast") into a gram weight without ever asking the
LLM for a number — the search/calculation split keeps generative steps
away from the math. Resolution is tried in descending order of trust:

1. an explicit **mass** unit (g, oz, lb …) is converted directly;
2. a unit that matches one of the food's **serving sizes** is scaled by quantity;
3. a **whole-item** count (the food's own name, or "each"/"whole"/…) uses the
   food's representative serving — an NLEA/edible serving in preference to an
   oversized whole-package one;
4. otherwise a generic **fallback table** of household measures is consulted.

Each result reports its ``source`` and a ``confidence`` in [0, 1] so the eval
``portion_error`` surface and the supervisor can see how firm the number is. An
unresolvable portion returns ``grams=None`` at zero confidence rather than
raising, keeping the agent loop fail-soft.
"""

from __future__ import annotations

import math

from pydantic import BaseModel

from dietrace.nutrition.models import Food, ServingSize

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

# Generic "one piece" words. A query in these ("a slice" of pizza, "a piece" of
# chicken) counts single pieces of the food, so when no serving's own unit matches
# it scales the food's single-piece serving — "2 slices of pizza" → 2 × the pizza's
# "1 piece" (119 g), not 28 g and not the as-eaten 2-piece default.
_PIECE_WORDS = frozenset({"slice", "piece", "wedge", "portion", "item", "unit"})

# Words for a bare/unspecified portion ("a latte", "1 serving of soup"): scale the
# food's as-eaten default serving, not a single piece.
_DEFAULT_PORTION_WORDS = frozenset({"", "whole", "each", "serving"})

# Volume/weight measures (a serving's unit naming one of these is a measure, not a
# single edible piece) — used to skip them when picking a per-piece weight for a
# counted query like "10 almonds" (the piece is the "1 nut", not the "1 cup").
_MEASURE_UNITS = frozenset({
    "cup", "tablespoon", "tbsp", "teaspoon", "tsp", "fl oz", "floz", "oz",
    "ounce", "cubic inch", "linear inch", "gram", "g", "kg", "ml", "l", "liter",
    "quart", "pint", "gallon", "quantity not specified",
})

# Markers (in a serving's description/unit) of an NLEA label / edible-portion
# serving — USDA's reference amount, the most trustworthy single serving to scale
# a bare count by.
_PREFERRED_SERVING_WORDS = frozenset({"nlea", "edible"})

# The FNDDS "as-eaten" default portion ("Quantity not specified") — the survey's
# own answer to "one typical serving of this food," and the best default to scale
# a bare item ("a latte" → 360 g, "grilled chicken" → 100 g) by.
_DEFAULT_SERVING_PHRASE = "quantity not specified"

# Generic whole-unit serving words. A serving whose unit is one of these — or the
# food's own name — is one whole item ("1 fruit" of an avocado, "1 banana"), the
# right per-piece weight for "an avocado" over a smaller "1 slice" serving.
_WHOLE_UNIT_WORDS = frozenset({"fruit", "whole"})

# Markers of a whole-package/container serving, which is often oversized (a whole
# box or bag holding several portions) and a poor default for a bare count. These
# are skipped in favor of an edible serving when one exists.
_OVERSIZED_SERVING_WORDS = frozenset({
    "package", "pkg", "container", "box", "bag", "carton",
    "jar", "tub", "pouch", "bottle", "can", "loaf",
})

_SERVING_CONFIDENCE = 0.9
_WHOLE_ITEM_CONFIDENCE = 0.8
_FALLBACK_CONFIDENCE = 0.5


class PortionEstimate(BaseModel):
    """A resolved portion: ``grams`` plus how it was reached.

    ``grams`` is None when the unit could not be resolved. ``source`` names the
    strategy that produced it ("mass", "serving_size", "whole_item",
    "fallback_table", or "unknown") and ``confidence`` is in [0, 1].
    ``basis`` is a plain-English explanation of the specific serving or measure
    used — e.g. "matched serving: 1 cup" or "counted 10 piece(s) — 1 nut" —
    so the UI can show why a food got its gram value.
    """

    grams: float | None
    source: str
    confidence: float
    basis: str = ""


def _singular(word: str) -> str:
    """Lower-case *word* and drop a single trailing plural "s" for matching."""
    word = word.strip().lower()
    if len(word) > 1 and word.endswith("s"):
        return word[:-1]
    return word


def _food_name_tokens(food: Food) -> set[str]:
    """The singularized word tokens of the food's description."""
    return {_singular(token) for token in food.description.replace(",", " ").split()}


def _matches_whole_item(food: Food, unit: str) -> bool:
    """True when *unit* names a whole piece of *food* (its name or a count word)."""
    if unit in _WHOLE_ITEM_WORDS:
        return True
    target = _singular(unit)
    if not target:
        return True
    return target in _food_name_tokens(food)


def _serving_words(serving: ServingSize) -> set[str]:
    """The singularized word tokens of a serving's description and unit."""
    text = f"{serving.description or ''} {serving.unit or ''}".replace(",", " ")
    return {_singular(token) for token in text.split()}


def _is_default_serving(serving: ServingSize) -> bool:
    """True for the FNDDS "Quantity not specified" as-eaten default serving."""
    text = f"{serving.description or ''} {serving.unit or ''}".lower()
    return _DEFAULT_SERVING_PHRASE in text


def _is_medium_size(serving: ServingSize) -> bool:
    """True when a serving names the medium/regular size of a sized food.

    Substring, not token, so it catches "small/medium shrimp" (the slash keeps
    "medium" from being its own word) and "1 medium or regular slice".
    """
    text = f"{serving.description or ''} {serving.unit or ''}".lower()
    return "medium" in text or "regular" in text


def representative_serving(servings: list[ServingSize]) -> ServingSize | None:
    """Pick the serving that best represents one edible portion.

    USDA foods may list servings in any order, sometimes leading with an oversized
    whole-package serving (a whole box or bag) ahead of the edible reference
    amount. Used to scale a bare count or a fallback, that package wildly overstates
    a portion. So prefer, in order: the FNDDS "Quantity not specified" as-eaten
    serving (the survey's own typical portion), then an NLEA/edible-portion serving,
    then any serving that is not a whole-package one, then — fail-soft — the first
    listed serving so a food whose only serving is a package still resolves.
    """
    if not servings:
        return None
    for serving in servings:
        if _is_default_serving(serving):
            return serving
    for serving in servings:
        if _serving_words(serving) & _PREFERRED_SERVING_WORDS:
            return serving
    for serving in servings:
        if not (_serving_words(serving) & _OVERSIZED_SERVING_WORDS):
            return serving
    return servings[0]


def _best_unit_match(matches: list[ServingSize], key: str) -> ServingSize:
    """Among servings whose tokens include the query *unit*, pick the best one.

    Prefer a serving whose own unit IS the query unit ("cup" → "1 cup"); else a
    medium/regular size when the food lists small/medium/large variants (so "5
    shrimp" takes the small/medium piece, not the tiny or jumbo one); else the
    first listed.
    """
    for serving in matches:
        if _singular((serving.unit or "").lower()) == key:
            return serving
    for serving in matches:
        if _is_medium_size(serving):
            return serving
    return matches[0]


def _per_piece_serving(food: Food) -> ServingSize | None:
    """The serving that represents ONE physical piece of *food*, for a counted query.

    "an avocado" is one whole fruit ("1 fruit", 150 g), but "10 almonds" is ten of
    the small piece ("1 nut", 1.2 g) — both counts, opposite sizes. So among the
    genuine single pieces (skip measure units, the as-eaten default, and oversized
    packages) prefer, in order: a serving named after the whole food itself ("1
    banana", "1 fruit"), an explicit "not further specified" piece ("1 piece,
    NFS"), a medium/regular size, then — for a truly granular food — the smallest.
    Falls back to the representative serving when the food lists no piece.
    """
    servings = food.serving_sizes
    pieces = [
        s
        for s in servings
        if s.amount
        and s.gram_weight
        and _singular((s.unit or "").lower()) not in _MEASURE_UNITS_SINGULAR
        and not _is_default_serving(s)
        and not (_serving_words(s) & _OVERSIZED_SERVING_WORDS)
    ]
    if not pieces:
        return representative_serving(servings)
    whole = _food_name_tokens(food) | _WHOLE_UNIT_WORDS
    for serving in pieces:  # a whole-food piece ("1 banana", "1 fruit")
        if _singular((serving.unit or "").lower()) in whole:
            return serving
    for serving in pieces:  # an explicit "not further specified" single piece
        if "nfs" in f"{serving.description or ''} {serving.unit or ''}".lower():
            return serving
    for serving in pieces:  # the medium/regular size of a sized piece
        if _is_medium_size(serving):
            return serving
    return min(pieces, key=lambda s: s.gram_weight / s.amount)


_MEASURE_UNITS_SINGULAR = frozenset(_singular(u) for u in _MEASURE_UNITS)


def _has_whole_food_piece(food: Food) -> bool:
    """True when the food lists a serving that is one whole item of itself — a
    serving named after the food or a generic whole-unit word ("1 fruit", "1
    banana"), e.g. avocado's "1 fruit" (150 g). Such foods should be counted by
    that piece for a bare or fractional count ("half an avocado" → half the
    fruit), not scaled from a tiny "quantity not specified" reference serving.
    """
    whole = _food_name_tokens(food) | _WHOLE_UNIT_WORDS
    return any(
        s.amount
        and s.gram_weight
        and _singular((s.unit or "").lower()) in whole
        and not _is_default_serving(s)
        and not (_serving_words(s) & _OVERSIZED_SERVING_WORDS)
        for s in food.serving_sizes
    )


def estimate_portion(food: Food, quantity: float, unit: str | None = None) -> PortionEstimate:
    """Estimate the gram weight of *quantity* *unit* of *food*.

    Tries mass → serving size → whole-item → fallback table, returning the first
    that resolves. ``unit`` is matched case- and plural-insensitively. The
    result always carries a ``source`` and ``confidence``; an unresolved unit —
    or a non-finite/non-positive ``quantity`` (no real portion) — yields
    ``grams=None`` rather than raising.
    """
    # A real portion is a positive, finite count. The ADK agent calls this tool
    # directly with an LLM-supplied quantity (agent.py), so — like parse_meal's
    # guard on its own output — a non-finite or non-positive quantity is rejected
    # up front rather than scaled into a negative/NaN/inf gram weight that would
    # poison log_entry's totals.
    if not math.isfinite(quantity) or quantity <= 0:
        return PortionEstimate(
            grams=None,
            source="unknown",
            confidence=0.0,
            basis=f"invalid quantity: {quantity:g} — not a positive, finite portion",
        )

    normalized = (unit or "").strip().lower()
    key = _singular(normalized)

    # 1. Explicit mass unit — no food context needed, fully trusted.
    if key in _MASS_GRAMS:
        return PortionEstimate(
            grams=quantity * _MASS_GRAMS[key],
            source="mass",
            confidence=1.0,
            basis=f"explicit weight: {quantity:g} {normalized}",
        )

    # 2. A serving whose unit/description names the query unit — scale it. Token
    #    matching catches a measure ("1 cup") and a counted piece, including a
    #    sized one ("5 shrimp" → "1 small/medium shrimp").
    if key and key not in _WHOLE_ITEM_WORDS:
        matches = [s for s in food.serving_sizes if s.amount and key in _serving_words(s)]
        if matches:
            best = _best_unit_match(matches, key)
            per_unit = best.gram_weight / best.amount
            serving_label = best.description or best.unit or key
            return PortionEstimate(
                grams=quantity * per_unit,
                source="serving_size",
                confidence=_SERVING_CONFIDENCE,
                basis=f"matched serving: {serving_label}",
            )

    # 3. A whole-item count. Counting single pieces — the named food ("10 almonds"),
    #    a generic "slice"/"piece" ("2 slices of pizza"), or a plain multi-count whose
    #    unit the parse left bare ("10 almonds" → quantity 10, no unit) — scales ONE
    #    physical piece; a single bare/unspecified portion ("a latte") scales the
    #    food's as-eaten default serving instead.
    counts_pieces = (
        key in _PIECE_WORDS
        or (bool(key) and key not in _WHOLE_ITEM_WORDS and _matches_whole_item(food, normalized))
        or (normalized in _DEFAULT_PORTION_WORDS and quantity >= 2)
        # A bare/fractional count of a food with its own whole-item serving
        # ("half an avocado", "an apple") counts that piece, not the reference.
        or (normalized in _DEFAULT_PORTION_WORDS and _has_whole_food_piece(food))
    )
    wants_default = normalized in _DEFAULT_PORTION_WORDS and not counts_pieces
    if food.serving_sizes and (counts_pieces or wants_default):
        serving = (
            _per_piece_serving(food)
            if counts_pieces
            else representative_serving(food.serving_sizes)
        )
        if serving and serving.amount:
            per_item = serving.gram_weight / serving.amount
            serving_label = serving.description or serving.unit or "serving"
            if counts_pieces:
                basis = f"counted {quantity:g} piece(s) — {serving_label}"
            else:
                basis = f"no amount given → reference serving ({serving_label})"
            return PortionEstimate(
                grams=quantity * per_item,
                source="whole_item",
                confidence=_WHOLE_ITEM_CONFIDENCE,
                basis=basis,
            )

    # 4. Generic fallback table — a coarse household-measure guess.
    if key in _FALLBACK_GRAMS:
        return PortionEstimate(
            grams=quantity * _FALLBACK_GRAMS[key],
            source="fallback_table",
            confidence=_FALLBACK_CONFIDENCE,
            basis=f"generic {key or 'serving'} measure",
        )

    return PortionEstimate(
        grams=None,
        source="unknown",
        confidence=0.0,
        basis=f"unit not recognized: '{unit or '(none)'}' — no matching serving",
    )
