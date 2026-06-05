"""Canned demo seed fixtures for POST /demo/seed.

Pre-computed per_item/totals/trace data that bypasses the live Gemini pipeline
entirely — deterministic and offline. One meal is deliberately over-portioned
(100 g peanut butter vs the standard 32 g serving) to invite a correction
demonstration from the judge, exercising the /correct flow.
"""

from __future__ import annotations

from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _n(code: str, name: str, amount: float, unit: str) -> dict[str, Any]:
    return {"code": code, "name": name, "amount": round(amount, 2), "unit": unit}


def _totals(kcal: float, protein: float, carb: float, fat: float) -> list[dict[str, Any]]:
    return [
        _n("208", "Energy", kcal, "kcal"),
        _n("203", "Protein", protein, "g"),
        _n("205", "Carbohydrate, by difference", carb, "g"),
        _n("204", "Total lipid (fat)", fat, "g"),
    ]


def _item_nutrients(kcal: float, protein: float, carb: float, fat: float) -> list[dict[str, Any]]:
    return _totals(kcal, protein, carb, fat)


def _build_trace(
    per_item: list[dict[str, Any]], totals: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Build the agent's-work trace from canned per_item fixtures."""
    foods = [item["description"] for item in per_item]
    steps: list[dict[str, Any]] = [
        {
            "step": "parse_meal",
            "foods": foods,
            "summary": f"Parsed {len(foods)} food(s): {', '.join(foods)}",
        }
    ]
    for item in per_item:
        food = item["description"]
        fdc_id = item.get("fdc_id", 0)
        grams = item["grams"]
        basis = item.get("portion_basis", "")
        steps.append(
            {
                "step": "search_nutrition",
                "food": food,
                "matched": food,
                "fdc_id": fdc_id,
                "summary": f"Matched '{food}' to USDA food {fdc_id}",
            }
        )
        steps.append(
            {
                "step": "estimate_portion",
                "food": food,
                "grams": grams,
                "basis": basis,
                "summary": f"Estimated {grams} g for '{food}'"
                + (f" ({basis})" if basis else ""),
            }
        )
    steps.append(
        {
            "step": "log_entry",
            "totals": totals,
            "summary": f"Logged {len(per_item)} item(s) into {len(totals)} nutrient total(s)",
        }
    )
    return steps


def _detail(
    per_item: list[dict[str, Any]],
    totals: list[dict[str, Any]],
    axes: list[dict[str, Any]],
    confidence: float,
    needs_review: bool,
    review_reason: str | None = None,
    reasons: list[str] | None = None,
) -> dict[str, Any]:
    """Package the full per-meal detail dict stored in detail_json."""
    trace = _build_trace(per_item, totals)
    return {
        "per_item": per_item,
        "trace": trace,
        "confidence": confidence,
        "reasons": reasons or [],
        "axes": axes,
        "needs_review": needs_review,
        "review_reason": review_reason,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Quality axes
# ──────────────────────────────────────────────────────────────────────────────

_HIGH_CONF_AXES: list[dict[str, Any]] = [
    {"name": "resolution_completeness", "score": 1.0, "note": "✓ all items resolved"},
    {"name": "source_quality", "score": 1.0, "note": "✓ USDA Foundation data"},
    {"name": "portion_sanity", "score": 1.0, "note": "✓ plausible gram weight"},
    {"name": "calorie_plausibility", "score": 1.0, "note": "✓ Atwater consistent"},
]

_MISMATCH_AXES: list[dict[str, Any]] = [
    {"name": "resolution_completeness", "score": 1.0, "note": "✓ all items resolved"},
    {"name": "source_quality", "score": 1.0, "note": "✓ USDA Foundation data"},
    {
        "name": "portion_sanity",
        "score": 0.35,
        "note": "⚠ 100 g peanut butter is ~3× the standard 32 g serving",
    },
    {
        "name": "calorie_plausibility",
        "score": 0.55,
        "note": "⚠ 588 kcal is high for a single snack",
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# Canned meal fixtures
# ──────────────────────────────────────────────────────────────────────────────


def _breakfast() -> dict[str, Any]:
    """Oatmeal with blueberries — a balanced, well-portioned breakfast."""
    per_item = [
        {
            "fdc_id": 168872,
            "description": "Oats, raw",
            "grams": 80.0,
            "portion_basis": "1 cup dry (80 g reference serving)",
            "nutrients": _item_nutrients(307.2, 10.7, 52.4, 5.2),
        },
        {
            "fdc_id": 171711,
            "description": "Blueberries, raw",
            "grams": 100.0,
            "portion_basis": "1 cup (~100 g reference serving)",
            "nutrients": _item_nutrients(57.0, 0.74, 14.5, 0.33),
        },
    ]
    meal_totals = _totals(364.2, 11.44, 66.9, 5.53)
    return {
        "text": "oatmeal with blueberries",
        "totals": meal_totals,
        "detail": _detail(
            per_item,
            meal_totals,
            _HIGH_CONF_AXES,
            0.92,
            False,
            reasons=["USDA Foundation foods; portions at reference servings"],
        ),
    }


def _lunch() -> dict[str, Any]:
    """Grilled chicken salad — high-protein, low-carb lunch."""
    per_item = [
        {
            "fdc_id": 171477,
            "description": "Chicken breast, grilled",
            "grams": 150.0,
            "portion_basis": "1 medium breast (~150 g)",
            "nutrients": _item_nutrients(247.5, 46.4, 0.0, 5.4),
        },
        {
            "fdc_id": 168462,
            "description": "Mixed greens, raw",
            "grams": 60.0,
            "portion_basis": "2 cups (~60 g reference serving)",
            "nutrients": _item_nutrients(15.0, 1.5, 2.3, 0.3),
        },
    ]
    meal_totals = _totals(262.5, 47.9, 2.3, 5.7)
    return {
        "text": "grilled chicken salad",
        "totals": meal_totals,
        "detail": _detail(
            per_item,
            meal_totals,
            _HIGH_CONF_AXES,
            0.89,
            False,
            reasons=["USDA Foundation foods; portion at typical meal weight"],
        ),
    }


def _snack_mismatch() -> dict[str, Any]:
    """Peanut butter on apple — over-portioned PB begging for a correction.

    Standard peanut-butter serving is 32 g (2 tbsp); logging 100 g (~3×) is a
    common casual-spoon scenario.  The habit-mismatch triggers needs_review=True
    so a judge can immediately demo the /correct flow to see the day band update.
    """
    per_item = [
        {
            "fdc_id": 172470,
            "description": "Peanut butter, smooth",
            "grams": 100.0,
            "portion_basis": "no amount given → reference serving (100 g per-100 g base)",
            "nutrients": _item_nutrients(588.0, 25.1, 19.6, 50.4),
        },
        {
            "fdc_id": 341508,
            "description": "Apple, raw",
            "grams": 182.0,
            "portion_basis": "1 medium apple (~182 g)",
            "nutrients": _item_nutrients(94.6, 0.5, 25.1, 0.3),
        },
    ]
    meal_totals = _totals(682.6, 25.6, 44.7, 50.7)
    review_reason = (
        "portion sanity: 100 g peanut butter is ~3× the standard 32 g serving "
        "— try correcting it to 32 g to see the day band update"
    )
    return {
        "text": "peanut butter on apple",
        "totals": meal_totals,
        "detail": _detail(
            per_item,
            meal_totals,
            _MISMATCH_AXES,
            0.48,
            True,
            review_reason=review_reason,
            reasons=[review_reason],
        ),
    }


def _dinner() -> dict[str, Any]:
    """Salmon with sweet potato — balanced omega-3 dinner."""
    per_item = [
        {
            "fdc_id": 175167,
            "description": "Salmon, Atlantic, farmed, cooked",
            "grams": 170.0,
            "portion_basis": "1 fillet (~170 g)",
            "nutrients": _item_nutrients(354.6, 38.4, 0.0, 22.0),
        },
        {
            "fdc_id": 168482,
            "description": "Sweet potato, baked",
            "grams": 150.0,
            "portion_basis": "1 medium sweet potato (~150 g baked)",
            "nutrients": _item_nutrients(129.0, 2.3, 30.0, 0.15),
        },
    ]
    meal_totals = _totals(483.6, 40.7, 30.0, 22.15)
    return {
        "text": "salmon with sweet potato",
        "totals": meal_totals,
        "detail": _detail(
            per_item,
            meal_totals,
            _HIGH_CONF_AXES,
            0.91,
            False,
            reasons=["USDA Foundation foods; portions at standard serving weights"],
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Public interface
# ──────────────────────────────────────────────────────────────────────────────

# Sample macro targets for a moderately active adult maintaining weight.
# Only the four macro codes the /goals + /analysis band reads.
DEMO_GOALS: dict[str, float] = {
    "208": 2200.0,  # kcal/day
    "203": 160.0,   # protein g
    "205": 220.0,   # carbohydrate g
    "204": 65.0,    # fat g
}

DEMO_GOAL_RATIONALE = (
    "Sample targets for a moderately active adult (~2 200 kcal/day, 160 g protein). "
    "Correct the peanut-butter snack to see the day band update instantly."
)

# Ordered list of canned meals: breakfast → lunch → snack (mismatch) → dinner.
DEMO_MEALS: list[dict[str, Any]] = [
    _breakfast(),
    _lunch(),
    _snack_mismatch(),
    _dinner(),
]
