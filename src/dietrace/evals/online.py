"""Per-log quality eval — the online-eval core.

The dataset evaluators in ``evaluators.py`` score the agent against USDA ground
truth offline. This is the *online* counterpart: it scores a single logged meal
*as it is logged*, with no ground truth and no LLM — only deterministic
heuristics over what the pipeline already produced. The web layer can surface
the resulting ``confidence`` next to a meal and the supervisor can watch it
trend, the same way the numeric evaluators feed Phoenix (: deterministic,
zero-LLM scoring; normalize to [0,1]).

``evaluate_log(text, per_item, totals)`` judges four things, each a sub-score in
[0,1] that averages into the overall confidence:

1. **Resolution completeness** — were all the foods named in *text* resolved, or
   did some get dropped? The count of foods named is read from the free text;
   fewer resolved items than named is a drop.
2. **Source quality** — how trustworthy each item's resolution is. An explicit
   per-item ``source``/``data_type`` hint is used when present; otherwise it is
   inferred from the ``fdc_id`` (a real USDA id is high-trust; the synthetic
   ``0`` of a web-grounded food is weaker).
3. **Portion sanity** — each item's grams sit in a plausible band; a zero or an
   absurd weight is implausible.
4. **Calorie plausibility** — the totalled energy (USDA 208) agrees, within
   tolerance, with the Atwater estimate of the macros (protein·4 + carb·4 +
   fat·9), the same identity ``log_entry`` builds totals from.

Each failing axis adds a short machine ``flag`` and a human-readable ``reason``.
"""

from __future__ import annotations

import re
from typing import Any

# USDA number codes the heuristics read by, never by name.
_ENERGY, _PROTEIN, _FAT, _CARB = "208", "203", "204", "205"

# Standard Atwater factors (kcal per gram) — the same identity log_entry totals
# energy from, used here in reverse to sanity-check the totalled calories.
_ATWATER: dict[str, float] = {_PROTEIN: 4.0, _FAT: 9.0, _CARB: 4.0}

# A single food's portion plausibly weighs within this band (grams). Below it is
# effectively nothing logged; above it is more than a person eats of one food.
_MIN_GRAMS = 1.0
_MAX_GRAMS = 4000.0

# Calorie total may diverge from the macro-derived Atwater estimate by this much
# before it reads as inconsistent (mirrors the evaluators' default ±band, §6).
_CALORIE_TOLERANCE = 0.15

# Source hints (explicit or inferred) → a trust weight in [0,1]. USDA whole-food
# tiers are ground-truth grade; a branded label is slightly softer; a grounded
# web lookup is the one place the agent reads a number it didn't compute; an
# unknown/absent source is the weakest.
_SOURCE_QUALITY: dict[str, float] = {
    "usda": 1.0,
    "foundation": 1.0,
    "sr_legacy": 1.0,
    "db": 1.0,
    "user_meal_correction": 1.0,
    "branded": 0.85,
    "label": 0.85,
    "web": 0.6,
    "web_grounded": 0.6,
    "none": 0.3,
    "unknown": 0.3,
}

# Below this mean source weight, the log carries a low-quality-source flag.
_SOURCE_FLAG_THRESHOLD = 0.8

# Delimiters that separate the foods named in a free-text meal. Crude but
# deterministic — enough to notice "eggs, toast and juice" is three foods.
_ITEM_SPLIT = re.compile(r",|;|\+|&|\n|\band\b|\bwith\b|\bplus\b", re.IGNORECASE)


def _field(item: Any, key: str, default: Any = None) -> Any:
    """Read *key* from a dict-or-model item (the pipeline hands either)."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _count_named_foods(text: str) -> int:
    """How many distinct foods the free text names, by splitting on delimiters."""
    chunks = [chunk.strip() for chunk in _ITEM_SPLIT.split(text or "")]
    return sum(1 for chunk in chunks if chunk)


def _source_of(item: Any) -> str:
    """The item's source: an explicit hint if present, else inferred from fdc_id."""
    hint = _field(item, "source") or _field(item, "data_type")
    if hint:
        return str(hint).lower()
    fdc_id = _field(item, "fdc_id")
    # A real USDA id is reproducible (high trust); the synthetic 0 of a
    # web-grounded food, or a missing id, is not.
    return "usda" if fdc_id else "web"


def _totals_by_code(totals: Any) -> dict[str, float]:
    """Map a totals list (dicts or Nutrient models) to ``code -> amount``."""
    out: dict[str, float] = {}
    for nutrient in totals or []:
        code = str(_field(nutrient, "code"))
        out[code] = float(_field(nutrient, "amount", 0.0) or 0.0)
    return out


def _resolution_completeness(text: str, per_item: list[Any]) -> dict[str, Any]:
    """Sub-score for whether every named food resolved to a logged item."""
    named = _count_named_foods(text)
    resolved = len(per_item)
    if named == 0:
        # Nothing recognizable named; don't penalize this axis.
        return {"score": 1.0}
    if resolved >= named:
        return {"score": 1.0}
    dropped = named - resolved
    return {
        "score": resolved / named,
        "flag": "dropped_items",
        "reason": (
            f"{dropped} of {named} food(s) named were not resolved "
            f"({resolved} logged)"
        ),
    }


def _source_quality(per_item: list[Any]) -> dict[str, Any] | None:
    """Sub-score for the mean trust of each item's resolution source."""
    if not per_item:
        return None
    sources = [_source_of(item) for item in per_item]
    weights = [_SOURCE_QUALITY.get(src, 0.3) for src in sources]
    score = sum(weights) / len(weights)
    if score >= _SOURCE_FLAG_THRESHOLD:
        return {"score": score}
    weak = sorted({src for src, w in zip(sources, weights, strict=True) if w < 1.0})
    return {
        "score": score,
        "flag": "low_source_quality",
        "reason": f"lower-trust source(s): {', '.join(weak)}",
    }


def _portion_sanity(per_item: list[Any]) -> dict[str, Any] | None:
    """Sub-score for the fraction of items whose grams sit in a plausible band."""
    if not per_item:
        return None
    grams = [float(_field(item, "grams", 0.0) or 0.0) for item in per_item]
    offenders = [g for g in grams if not _MIN_GRAMS <= g <= _MAX_GRAMS]
    score = (len(grams) - len(offenders)) / len(grams)
    if not offenders:
        return {"score": 1.0}
    return {
        "score": score,
        "flag": "implausible_portion",
        "reason": (
            f"{len(offenders)} portion(s) outside {_MIN_GRAMS:g}–{_MAX_GRAMS:g} g: "
            + ", ".join(f"{g:g} g" for g in offenders)
        ),
    }


def _calorie_plausibility(totals: Any) -> dict[str, Any] | None:
    """Sub-score for totalled energy vs the macros' Atwater estimate."""
    by_code = _totals_by_code(totals)
    # Without a totalled energy figure there is nothing to sanity-check against
    # the macros; don't false-flag a mismatch (log_entry always emits 208, but
    # a partial totals input shouldn't misfire).
    if _ENERGY not in by_code:
        return None
    energy = by_code[_ENERGY]
    atwater = sum(by_code.get(code, 0.0) * factor for code, factor in _ATWATER.items())
    if atwater == 0.0:
        # No macros to derive energy from; consistent only if energy is ~0 too.
        if energy == 0.0:
            return {"score": 1.0}
        return {
            "score": 0.0,
            "flag": "calorie_mismatch",
            "reason": f"{energy:.0f} kcal logged but the macros total zero energy",
        }
    rel_err = abs(energy - atwater) / atwater
    if rel_err <= _CALORIE_TOLERANCE:
        return {"score": 1.0}
    return {
        "score": 1.0 - min(rel_err, 1.0),
        "flag": "calorie_mismatch",
        "reason": (
            f"{energy:.0f} kcal logged vs {atwater:.0f} kcal Atwater estimate "
            f"({rel_err:.0%} off)"
        ),
    }


def evaluate_log(
    text: str,
    per_item: list[Any],
    totals: Any,
) -> dict[str, Any]:
    """Score a single logged meal's quality from deterministic heuristics (§6).

    Returns ``{"confidence": float in [0,1], "flags": [str], "reasons": [str]}``.
    ``confidence`` is the mean of the applicable sub-scores (resolution
    completeness, source quality, portion sanity, calorie plausibility); each
    axis that falls short contributes a machine ``flag`` and a human ``reason``.
    No LLM, no network — only the structured pipeline output.
    """
    per_item = list(per_item or [])
    components = [
        _resolution_completeness(text, per_item),
        _source_quality(per_item),
        _portion_sanity(per_item),
        _calorie_plausibility(totals),
    ]
    applicable = [c for c in components if c is not None]

    scores = [c["score"] for c in applicable]
    confidence = round(sum(scores) / len(scores), 3) if scores else 0.0
    flags = [c["flag"] for c in applicable if "flag" in c]
    reasons = [c["reason"] for c in applicable if "reason" in c]

    return {
        "confidence": max(0.0, min(1.0, confidence)),
        "flags": flags,
        "reasons": reasons,
    }
