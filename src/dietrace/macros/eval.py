"""Macro plan online eval — point-of-use accountability check.

``evaluate_macro_plan(profile, plan)`` is the deterministic, zero-LLM counterpart
of ``src/dietrace/evals/online.py`` for macro plans. It scores two axes:

1. **Consistency** — the Atwater identity holds: 4·protein + 4·carb + 9·fat ≈ kcal
   (the same identity ``compute_targets`` and ``personalize_plan`` enforce). Drift
   beyond tolerance means the plan's internal numbers disagree.

2. **Safety** — macros sit in physiological bounds (same bounds ``personalize_plan``
   clamps to):
   - protein in [1.2, 2.4] g per kg body weight
   - fat in [0.15, 0.40] of total kcal

``score`` is the mean of the two sub-scores (each in [0,1]); ``pass`` is True only
when both axes score 1.0 (no flags). No LLM, no network.
"""

from __future__ import annotations

from .models import MacroPlan, MacroProfile

# USDA nutrient codes.
_ENERGY = "208"
_PROTEIN = "203"
_FAT = "204"
_CARB = "205"

# Standard Atwater factors (kcal/g).
_ATWATER_P = 4.0
_ATWATER_C = 4.0
_ATWATER_F = 9.0

# Consistency: fraction of kcal by which the Atwater estimate may differ before
# the plan is considered internally inconsistent.
_ATWATER_TOLERANCE_FRAC = 0.05

# Safety bounds for protein (g per kg body weight).
_PROTEIN_MIN_PER_KG = 1.2
_PROTEIN_MAX_PER_KG = 2.4

# Safety bounds for fat (fraction of total kcal).
_FAT_MIN_FRAC = 0.15
_FAT_MAX_FRAC = 0.40


def _consistency(plan: MacroPlan) -> dict:
    """Check that the Atwater identity holds within tolerance."""
    t = plan.targets
    kcal = t.get(_ENERGY, 0.0)
    protein = t.get(_PROTEIN, 0.0)
    fat = t.get(_FAT, 0.0)
    carb = t.get(_CARB, 0.0)

    atwater = _ATWATER_P * protein + _ATWATER_C * carb + _ATWATER_F * fat

    if kcal == 0.0:
        if atwater == 0.0:
            return {"score": 1.0}
        return {
            "score": 0.0,
            "flag": "atwater_inconsistent",
            "reason": (
                f"Atwater estimate {atwater:.0f} kcal but plan target is 0 kcal"
            ),
        }

    rel_err = abs(atwater - kcal) / kcal
    if rel_err <= _ATWATER_TOLERANCE_FRAC:
        return {"score": 1.0}

    return {
        "score": max(0.0, 1.0 - rel_err),
        "flag": "atwater_inconsistent",
        "reason": (
            f"Atwater estimate {atwater:.0f} kcal vs energy target {kcal:.0f} kcal "
            f"({rel_err:.0%} drift)"
        ),
    }


def _safety(profile: MacroProfile, plan: MacroPlan) -> dict:
    """Check that protein g/kg and fat fraction are in physiological bounds."""
    t = plan.targets
    kcal = t.get(_ENERGY, 0.0)
    protein = t.get(_PROTEIN, 0.0)
    fat = t.get(_FAT, 0.0)

    flags: list[str] = []
    reasons: list[str] = []
    axes_failed = 0
    total_axes = 2

    # Protein g/kg check — skip (don't penalise) when weight is degenerate (zero),
    # mirroring how the fat fraction axis is skipped when kcal is zero.
    if profile.weight_kg > 0.0:
        protein_per_kg = protein / profile.weight_kg
        protein_lo = _PROTEIN_MIN_PER_KG
        protein_hi = _PROTEIN_MAX_PER_KG
        if not (protein_lo <= protein_per_kg <= protein_hi):
            flags.append("protein_out_of_bounds")
            reasons.append(
                f"protein {protein_per_kg:.2f} g/kg outside [{protein_lo}, {protein_hi}] g/kg "
                f"({protein:.0f} g for {profile.weight_kg:.0f} kg)"
            )
            axes_failed += 1
    else:
        total_axes -= 1  # protein axis undefined — don't count it

    # Fat fraction check.
    if kcal > 0.0:
        fat_frac = (fat * _ATWATER_F) / kcal
        if not (_FAT_MIN_FRAC <= fat_frac <= _FAT_MAX_FRAC):
            flags.append("fat_out_of_bounds")
            reasons.append(
                f"fat {fat_frac:.0%} of kcal outside [{_FAT_MIN_FRAC:.0%}, {_FAT_MAX_FRAC:.0%}] "
                f"({fat:.0f} g)"
            )
            axes_failed += 1
    else:
        # Zero kcal: fat fraction is undefined; check only gram-level.
        if fat > 0.0:
            flags.append("fat_out_of_bounds")
            reasons.append(f"fat {fat:.0f} g present but kcal target is 0")
            axes_failed += 1

    score = (total_axes - axes_failed) / total_axes

    result: dict = {"score": score}
    if flags:
        result["flags"] = flags
        result["reasons"] = reasons
    return result


def evaluate_macro_plan(
    profile: MacroProfile,
    plan: MacroPlan,
) -> dict:
    """Score a macro plan on consistency and safety.

    Returns::

        {
            "score":       float in [0, 1],  # mean of both sub-scores
            "pass":        bool,             # True iff score == 1.0
            "consistency": dict,             # Atwater sub-result
            "safety":      dict,             # protein/fat bounds sub-result
            "flags":       [str],            # machine-readable axis failures
            "reasons":     [str],            # human-readable failure descriptions
        }

    Deterministic, zero-LLM — only the structured plan data and the profile's
    weight_kg are used.
    """
    c = _consistency(plan)
    s = _safety(profile, plan)

    score = round((c["score"] + s["score"]) / 2.0, 3)

    flags: list[str] = []
    reasons: list[str] = []
    if "flag" in c:
        flags.append(c["flag"])
        reasons.append(c["reason"])
    flags.extend(s.get("flags", []))
    reasons.extend(s.get("reasons", []))

    result = {
        "score": score,
        "pass": score == 1.0,
        "consistency": c,
        "safety": s,
        "flags": flags,
        "reasons": reasons,
    }

    from dietrace.evals.span_eval import annotate_macro_eval  # local to avoid circular risk

    annotate_macro_eval(result)
    return result
