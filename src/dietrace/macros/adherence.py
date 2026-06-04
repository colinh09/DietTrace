"""Macro split adherence — how closely a plan matches a user's saved preference.

Deterministic, zero-LLM. The personalization-value signal (Macros Phase 2): with a
remembered preference, 1.0 means the plan's protein/fat split exactly matches what
the user chose; lower means the safety clamps (e.g. the 2.4 g/kg ceiling) pulled it
away. Rides the trace into Phoenix and powers the "tuned to you" UI line. This is an
ALIGNMENT measure (plan vs the user's own preference), not accuracy against truth.
"""

from __future__ import annotations

from typing import Any

from .models import MacroPlan

_ENERGY, _PROTEIN, _FAT = "208", "203", "204"
_ATWATER_P, _ATWATER_F = 4.0, 9.0


def _split(plan: MacroPlan) -> tuple[float, float] | None:
    """The plan's (protein_pct, fat_pct) of kcal, or None when kcal is non-positive."""
    kcal = float(plan.targets.get(_ENERGY, 0.0) or 0.0)
    if kcal <= 0.0:
        return None
    return (
        _ATWATER_P * float(plan.targets.get(_PROTEIN, 0.0)) / kcal,
        _ATWATER_F * float(plan.targets.get(_FAT, 0.0)) / kcal,
    )


def macro_adherence(plan: MacroPlan, preference: dict[str, float] | None) -> dict[str, Any]:
    """Return ``{score in [0,1], protein_delta, fat_delta}`` for *plan* vs *preference*.

    Deltas are ``plan_split - preferred_split`` (signed, as fractions of kcal). Score
    is 1 minus the total absolute split distance, floored at 0 — 1.0 is a perfect
    match. With no preference (or a degenerate plan), score is 0.0 and deltas 0.0.
    """
    split = _split(plan)
    if split is None or not preference:
        return {"score": 0.0, "protein_delta": 0.0, "fat_delta": 0.0}
    protein_pct, fat_pct = split
    protein_delta = round(protein_pct - float(preference.get("protein_pct", 0.0)), 4)
    fat_delta = round(fat_pct - float(preference.get("fat_pct", 0.0)), 4)
    score = round(max(0.0, 1.0 - (abs(protein_delta) + abs(fat_delta))), 3)
    return {"score": score, "protein_delta": protein_delta, "fat_delta": fat_delta}
