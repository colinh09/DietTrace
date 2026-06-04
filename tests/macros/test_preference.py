"""apply_preferred_split — bias a plan toward a user's saved split (macro learning)."""

from __future__ import annotations

from dietrace.macros.models import MacroPlan
from dietrace.macros.preference import apply_preferred_split


def _plan(kcal: float = 2121.0) -> MacroPlan:
    return MacroPlan(
        targets={"208": kcal, "203": 159.1, "205": 212.1, "204": 70.7},
        rationale="base", source="formula", steps=[], clamped=[],
    )


def test_applies_preferred_split_and_marks_personalized() -> None:
    plan = apply_preferred_split(_plan(), {"protein_pct": 0.20, "fat_pct": 0.35})
    assert plan.personalized is True
    t = plan.targets
    assert abs(4 * t["203"] / t["208"] - 0.20) < 0.01
    assert abs(9 * t["204"] / t["208"] - 0.35) < 0.01


def test_clamps_protein_to_g_per_kg_ceiling_when_weight_given() -> None:
    # 40% protein at 2121 kcal = 212 g = 2.65 g/kg for 80 kg → clamp to 2.4*80 = 192.
    plan = apply_preferred_split(_plan(), {"protein_pct": 0.40, "fat_pct": 0.20}, weight_kg=80.0)
    assert plan.targets["203"] == 192.0


def test_stays_atwater_consistent_after_apply() -> None:
    plan = apply_preferred_split(_plan(), {"protein_pct": 0.40, "fat_pct": 0.20}, weight_kg=80.0)
    t = plan.targets
    assert abs(4 * t["203"] + 4 * t["205"] + 9 * t["204"] - t["208"]) <= 5.0


def test_zero_kcal_plan_returned_unchanged() -> None:
    plan = MacroPlan(targets={"208": 0.0}, rationale="x", source="preset", steps=[], clamped=[])
    out = apply_preferred_split(plan, {"protein_pct": 0.3, "fat_pct": 0.3})
    assert out.personalized is False
