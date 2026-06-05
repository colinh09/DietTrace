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

# A single food item rarely exceeds this many calories — more is the signature of
# a portion blow-up (a count scaled by a 100 g default → a kilogram of almonds at
# ~5800 kcal). Grams alone can't catch it (1000 g of soup is fine), but calories
# per item can, so this flags it for the user to review.
_MAX_ITEM_KCAL = 1800.0

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

# Below this overall confidence a log is flagged for the user to glance at — the
# meal row offers a calm "review?" affordance into the correction editor
#.
REVIEW_THRESHOLD = 0.6

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


def sources_of(per_item: list[Any]) -> list[str]:
    """Each logged item's resolution source (the trust store's source breakdown).

    Reuses the same source resolution the source-quality sub-score scores by, so
    the per-log trust record and its confidence agree on where each number came
    from.
    """
    return [_source_of(item) for item in per_item or []]


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


def _item_energy(item: Any) -> float:
    """The logged calories of a single item (its scaled energy nutrient)."""
    for nutrient in _field(item, "nutrients", []) or []:
        if str(_field(nutrient, "code", "")) == _ENERGY:
            return float(_field(nutrient, "amount", 0.0) or 0.0)
    return 0.0


def _portion_sanity(per_item: list[Any]) -> dict[str, Any] | None:
    """Sub-score for items whose grams AND per-item calories are both plausible.

    Grams catch a near-zero or huge weight; per-item calories catch a portion
    blow-up that grams miss (a kilogram of almonds is under the gram ceiling but
    is ~5800 kcal — far more than one food).
    """
    if not per_item:
        return None
    offenders: list[str] = []
    for item in per_item:
        grams = float(_field(item, "grams", 0.0) or 0.0)
        if not _MIN_GRAMS <= grams <= _MAX_GRAMS:
            offenders.append(f"{grams:g} g")
        elif _item_energy(item) > _MAX_ITEM_KCAL:
            offenders.append(f"{_item_energy(item):.0f} kcal for one item")
    if not offenders:
        return {"score": 1.0}
    score = (len(per_item) - len(offenders)) / len(per_item)
    return {
        "score": score,
        "flag": "implausible_portion",
        "reason": f"{len(offenders)} implausible portion(s): " + ", ".join(offenders),
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


def _to_axis(name: str, component: dict[str, Any] | None, pass_note: str) -> dict[str, Any]:
    """Convert a sub-score component to a named axis with a ✓/⚠ note.

    When *component* is None (axis not applicable), reports score=1.0 and the
    pass note.  When it carries a ``flag``, the note leads with ⚠ and the human
    reason; otherwise it leads with ✓ and the pass note.
    """
    if component is None:
        return {"name": name, "score": 1.0, "note": f"✓ {pass_note}"}
    score = float(component["score"])
    if "flag" in component:
        return {"name": name, "score": score, "note": f"⚠ {component['reason']}"}
    return {"name": name, "score": score, "note": f"✓ {pass_note}"}


def evaluate_log(
    text: str,
    per_item: list[Any],
    totals: Any,
) -> dict[str, Any]:
    """Score a single logged meal's quality from deterministic heuristics (§6).

    Returns ``{"confidence": float in [0,1], "flags": [str], "reasons": [str],
    "axes": [{"name", "score", "note"}]}``.
    ``confidence`` is the mean of the applicable sub-scores (resolution
    completeness, source quality, portion sanity, calorie plausibility); each
    axis always appears in ``axes`` with a ✓/⚠ note — not only when failing
   .  No LLM, no network — only the structured pipeline output.
    """
    per_item = list(per_item or [])
    rc = _resolution_completeness(text, per_item)
    sq = _source_quality(per_item)
    ps = _portion_sanity(per_item)
    cp = _calorie_plausibility(totals)

    # Pass notes for each axis (only shown when the axis clears its threshold).
    named_count = _count_named_foods(text)
    resolved_count = len(per_item)
    rc_pass = (
        f"all {resolved_count} food(s) resolved" if named_count > 0 else "n/a"
    )
    sq_pass = "high-trust sources" if per_item else "n/a"
    ps_pass = f"all {len(per_item)} portion(s) plausible" if per_item else "n/a"
    by_code = _totals_by_code(totals)
    cp_pass = (
        f"{by_code[_ENERGY]:.0f} kcal ≈ Atwater estimate"
        if _ENERGY in by_code
        else "n/a"
    )

    axes = [
        _to_axis("resolution_completeness", rc, rc_pass),
        _to_axis("source_quality", sq, sq_pass),
        _to_axis("portion_sanity", ps, ps_pass),
        _to_axis("calorie_plausibility", cp, cp_pass),
    ]

    components = [rc, sq, ps, cp]
    applicable = [c for c in components if c is not None]
    scores = [c["score"] for c in applicable]
    confidence = round(sum(scores) / len(scores), 3) if scores else 0.0
    flags = [c["flag"] for c in applicable if "flag" in c]
    reasons = [c["reason"] for c in applicable if "reason" in c]

    result: dict[str, Any] = {
        "confidence": max(0.0, min(1.0, confidence)),
        "flags": flags,
        "reasons": reasons,
        "axes": axes,
    }

    from dietrace.evals.span_eval import annotate_log_eval  # local to avoid circular risk

    annotate_log_eval(result)
    return result


def review_flag(result: dict[str, Any]) -> dict[str, Any]:
    """Whether an ``evaluate_log`` *result* warrants a user review.

    Confidence below :data:`REVIEW_THRESHOLD` sets ``needs_review`` and surfaces a
    single ``review_reason`` — the eval's top (first) reason — so the meal row can
    offer a calm "review?" affordance into the correction editor. A confident log,
    or one with no reason to show, carries ``review_reason: None``. This is policy
    over the measurement: ``evaluate_log`` scores, ``review_flag`` decides.
    """
    needs_review = result["confidence"] < REVIEW_THRESHOLD
    reasons = result.get("reasons") or []
    return {
        "needs_review": needs_review,
        "review_reason": reasons[0] if (needs_review and reasons) else None,
    }
