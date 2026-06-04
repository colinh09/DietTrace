"""Apply a user's remembered macro split preference to a plan (macro-learning closure).

When a returning user has a saved preferred split (from ``macro_memory``), the plan
biases toward it instead of the generic goal-default split — the macro counterpart
of food-logging recall. Calories stay the deterministic number; only the protein/
fat/carb split moves, and it is clamped to the same physiological safety bands the
eval enforces, so a personalized plan still passes its safety check.
"""

from __future__ import annotations

from .models import MacroPlan

_ENERGY = "208"
_PROTEIN = "203"
_FAT = "204"
_CARB = "205"

_ATWATER_P = 4.0
_ATWATER_C = 4.0
_ATWATER_F = 9.0

# Safety bands on the split as fractions of kcal (fat matches the eval's [0.15,
# 0.40]; protein gets a sane kcal-fraction backstop). When the body weight is
# known, protein is additionally clamped to the eval's [1.2, 2.4] g/kg ceiling so
# a high protein-% at a high calorie target can't exceed the safe maximum.
_FAT_MIN_FRAC, _FAT_MAX_FRAC = 0.15, 0.40
_PROTEIN_MIN_FRAC, _PROTEIN_MAX_FRAC = 0.10, 0.40
_PROTEIN_MIN_PER_KG, _PROTEIN_MAX_PER_KG = 1.2, 2.4


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def apply_preferred_split(
    plan: MacroPlan, preference: dict[str, float], weight_kg: float | None = None
) -> MacroPlan:
    """Return *plan* re-split toward *preference* (``{protein_pct, fat_pct}``).

    Keeps ``plan``'s calorie target; recomputes protein/fat from the clamped
    preferred fractions and derives carbohydrate from the remainder so the Atwater
    identity still holds. When *weight_kg* is positive, protein is also clamped to
    [1.2, 2.4] g/kg so the personalized plan still passes its safety eval. Marks the
    result ``personalized=True``. If the plan has no positive calorie target, it is
    returned unchanged.
    """
    kcal = float(plan.targets.get(_ENERGY, 0.0) or 0.0)
    if kcal <= 0.0:
        return plan

    protein_pct = _clamp(
        float(preference.get("protein_pct", 0.0)), _PROTEIN_MIN_FRAC, _PROTEIN_MAX_FRAC
    )
    fat_pct = _clamp(
        float(preference.get("fat_pct", 0.0)), _FAT_MIN_FRAC, _FAT_MAX_FRAC
    )

    protein_g = round(kcal * protein_pct / _ATWATER_P, 1)
    fat_g = round(kcal * fat_pct / _ATWATER_F, 1)
    if weight_kg and weight_kg > 0.0:
        protein_g = round(
            _clamp(protein_g, _PROTEIN_MIN_PER_KG * weight_kg, _PROTEIN_MAX_PER_KG * weight_kg),
            1,
        )
    carb_kcal = max(0.0, kcal - protein_g * _ATWATER_P - fat_g * _ATWATER_F)
    carb_g = round(carb_kcal / _ATWATER_C, 1)

    rationale = (
        f"{plan.rationale} Split personalized to your saved preference "
        f"(protein {protein_pct:.0%} / fat {fat_pct:.0%} of kcal)."
    )

    return MacroPlan(
        targets={_ENERGY: kcal, _PROTEIN: protein_g, _CARB: carb_g, _FAT: fat_g},
        rationale=rationale,
        source=plan.source,
        steps=plan.steps,
        clamped=plan.clamped,
        personalized=True,
    )
