"""Mifflin–St Jeor macro target computation.

``compute_targets(profile) -> MacroPlan`` is a pure, deterministic function:
no LLM, no network. The derivation is:

    BMR  (Mifflin–St Jeor, sex-specific intercept)
    TDEE = BMR × activity multiplier
    kcal = TDEE + goal delta  (cut −500 / maintain 0 / bulk +300)
    macros split by fixed kcal-percentage ratios, converted to grams
            via standard Atwater factors (protein 4 / carb 4 / fat 9 kcal·g⁻¹)

Each step is recorded in ``MacroPlan.steps`` so the guided flow and
observability layer can surface "reasoning out loud" without invoking an LLM.
"""

from __future__ import annotations

from typing import Any

from .models import MacroPlan, MacroProfile

# USDA nutrient number codes — never by name so results stay reproducible.
_ENERGY = "208"
_PROTEIN = "203"
_FAT = "204"
_CARB = "205"

# Standard Atwater energy factors (kcal per gram).
_ATWATER: dict[str, float] = {_PROTEIN: 4.0, _CARB: 4.0, _FAT: 9.0}

# Activity multipliers (Little/Harris-Benedict scale, five tiers).
_ACTIVITY_MULTIPLIER: dict[str, float] = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}

# Calorie delta relative to TDEE for each goal.
_GOAL_DELTA: dict[str, float] = {
    "cut": -500.0,
    "maintain": 0.0,
    "bulk": 300.0,
}

# Minimum safe daily calorie target (kcal), sex-aware — the widely-cited clinical
# floors (~1500 men / ~1200 women). An aggressive cut on a small/light person can
# drive TDEE − 500 well below this; the floor guarantees the "AI nutritionist"
# never recommends a dangerously low intake.
_CALORIE_FLOOR: dict[str, float] = {"male": 1500.0, "female": 1200.0}

# Macro split as (protein_pct, carb_pct, fat_pct) fractions of total kcal.
# All three fractions sum to 1.0; converted to grams via Atwater factors.
_GOAL_SPLIT: dict[str, tuple[float, float, float]] = {
    "cut": (0.35, 0.35, 0.30),
    "maintain": (0.30, 0.40, 0.30),
    "bulk": (0.25, 0.45, 0.30),
}


def _mifflin_bmr(profile: MacroProfile) -> float:
    """Mifflin–St Jeor resting metabolic rate (kcal/day).

    Male   intercept: +5
    Female intercept: −161
    """
    base = 10.0 * profile.weight_kg + 6.25 * profile.height_cm - 5.0 * profile.age
    return base + 5.0 if profile.sex == "male" else base - 161.0


def compute_targets(profile: MacroProfile) -> MacroPlan:
    """Derive daily macro targets from *profile*.

    Returns a ``MacroPlan`` with ``source="formula"`` and four ordered ``steps``:
    ``bmr`` → ``tdee`` → ``adjust`` → ``split``. The plan is deterministic given
    the same profile; ``ai_help`` and ``preference`` are forwarded to later
    pipeline stages and do not affect this computation.
    """
    bmr = _mifflin_bmr(profile)
    multiplier = _ACTIVITY_MULTIPLIER[profile.activity]
    tdee = bmr * multiplier
    delta = _GOAL_DELTA[profile.goal]

    # Round the calorie target once; use this value for all downstream math so
    # targets["208"] and the Atwater sum of the macro grams agree.
    raw_kcal = round(tdee + delta, 1)

    # Enforce the sex-aware safe-minimum floor so an aggressive cut on a light
    # person never drops below a clinically safe intake. Record it as a clamp.
    floor = _CALORIE_FLOOR[profile.sex]
    floored = raw_kcal < floor
    kcal = floor if floored else raw_kcal
    clamped = ["calorie_floor"] if floored else []

    protein_pct, carb_pct, fat_pct = _GOAL_SPLIT[profile.goal]
    protein_g = round(kcal * protein_pct / _ATWATER[_PROTEIN], 1)
    carb_g = round(kcal * carb_pct / _ATWATER[_CARB], 1)
    fat_g = round(kcal * fat_pct / _ATWATER[_FAT], 1)

    steps: list[dict[str, Any]] = [
        {
            "step": "bmr",
            "value": round(bmr, 2),
            "formula": "mifflin_st_jeor",
            "sex": profile.sex,
        },
        {
            "step": "tdee",
            "value": round(tdee, 2),
            "multiplier": multiplier,
            "activity": profile.activity,
        },
        {
            "step": "adjust",
            "value": kcal,
            "goal": profile.goal,
            "delta": delta,
            "raw": raw_kcal,
            "floor": floor,
            "floored": floored,
        },
        {
            "step": "split",
            "kcal": kcal,
            "protein_pct": protein_pct,
            "carb_pct": carb_pct,
            "fat_pct": fat_pct,
        },
    ]

    rationale = (
        f"Mifflin–St Jeor BMR {bmr:.0f} kcal"
        f" × {multiplier} ({profile.activity})"
        f" = TDEE {tdee:.0f} kcal;"
        f" {profile.goal} goal ({delta:+.0f} kcal)"
        f" → {kcal:.0f} kcal target."
    )
    if floored:
        rationale += f" Raised to the {floor:.0f} kcal safe minimum."

    return MacroPlan(
        targets={
            _ENERGY: kcal,
            _PROTEIN: protein_g,
            _CARB: carb_g,
            _FAT: fat_g,
        },
        rationale=rationale,
        source="formula",
        steps=steps,
        clamped=clamped,
    )
