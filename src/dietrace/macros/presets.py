"""Deterministic macro presets — the no-profile path.

``preset_plan(key) -> MacroPlan`` returns a ready-to-use macro plan for one of
three lifestyle templates without requiring any personal measurements, making it
the privacy-friendly "skip the calculator" option.

Template calorie targets and macro splits:

    cut      ~1 800 kcal  — modest deficit for gradual fat loss
    maintain ~2 200 kcal  — balanced maintenance for a typical adult
    bulk     ~2 600 kcal  — moderate surplus for muscle gain

Grams are derived from each calorie target using standard Atwater factors
(protein 4 / carb 4 / fat 9 kcal·g⁻¹) so that 4·P + 4·C + 9·F equals the
stated calorie target exactly (within rounding to one decimal place).
"""

from __future__ import annotations

from .models import MacroPlan

# USDA nutrient number codes — same codes used across the whole stack.
_ENERGY = "208"
_PROTEIN = "203"
_FAT = "204"
_CARB = "205"

# Standard Atwater energy factors (kcal per gram).
_ATWATER = {_PROTEIN: 4.0, _CARB: 4.0, _FAT: 9.0}


def _make_plan(
    key: str, kcal: float, protein_pct: float, carb_pct: float, fat_pct: float
) -> MacroPlan:
    """Build a MacroPlan from kcal and percentage splits.

    Grams are rounded to one decimal place, matching the formula path.
    The rationale string is kept brief — it's the "no maths required" path.
    """
    protein_g = round(kcal * protein_pct / _ATWATER[_PROTEIN], 1)
    carb_g = round(kcal * carb_pct / _ATWATER[_CARB], 1)
    fat_g = round(kcal * fat_pct / _ATWATER[_FAT], 1)

    rationale = (
        f"Preset '{key}': {kcal:.0f} kcal target"
        f" ({protein_pct*100:.0f}% protein /"
        f" {carb_pct*100:.0f}% carb /"
        f" {fat_pct*100:.0f}% fat)."
        f" No profile required."
    )

    return MacroPlan(
        targets={
            _ENERGY: kcal,
            _PROTEIN: protein_g,
            _CARB: carb_g,
            _FAT: fat_g,
        },
        rationale=rationale,
        source="preset",
        steps=[
            {
                "step": "preset",
                "key": key,
                "kcal": kcal,
                "protein_pct": protein_pct,
                "carb_pct": carb_pct,
                "fat_pct": fat_pct,
            }
        ],
        clamped=[],
    )


# Template definitions: (kcal, protein_pct, carb_pct, fat_pct).
# Splits sum to 1.0; calorie targets chosen so Atwater sum matches exactly.
_PRESETS: dict[str, tuple[float, float, float, float]] = {
    "cut": (1800.0, 0.35, 0.35, 0.30),
    "maintain": (2200.0, 0.30, 0.40, 0.30),
    "bulk": (2600.0, 0.25, 0.45, 0.30),
}


def preset_plan(key: str) -> MacroPlan:
    """Return a ``MacroPlan`` for the named lifestyle preset.

    Args:
        key: One of ``"cut"``, ``"maintain"``, or ``"bulk"``.

    Raises:
        KeyError: If *key* does not match a known preset.
    """
    if key not in _PRESETS:
        raise KeyError(f"Unknown preset {key!r}; valid keys: {sorted(_PRESETS)}")
    kcal, protein_pct, carb_pct, fat_pct = _PRESETS[key]
    return _make_plan(key, kcal, protein_pct, carb_pct, fat_pct)
