"""macro_adherence — alignment of a plan to a user's saved split preference (P2.1)."""

from __future__ import annotations

from dietrace.macros.adherence import macro_adherence
from dietrace.macros.models import MacroPlan


def _plan(kcal: float = 2000.0, p: float = 150.0, f: float = 44.0, c: float = 200.0) -> MacroPlan:
    return MacroPlan(
        targets={"208": kcal, "203": p, "204": f, "205": c},
        rationale="x", source="formula", steps=[], clamped=[],
    )


def test_perfect_match_scores_one() -> None:
    # 150 g protein / 2000 kcal = 0.30; 44 g fat = 0.198.
    a = macro_adherence(_plan(), {"protein_pct": 0.30, "fat_pct": 0.198})
    assert a["score"] == 1.0
    assert abs(a["protein_delta"]) < 0.001
    assert abs(a["fat_delta"]) < 0.001


def test_distance_lowers_score_with_signed_deltas() -> None:
    a = macro_adherence(_plan(), {"protein_pct": 0.40, "fat_pct": 0.198})
    assert a["score"] == 0.9  # 10% off on protein
    assert a["protein_delta"] == -0.1  # plan 0.30 - pref 0.40


def test_no_preference_scores_zero() -> None:
    assert macro_adherence(_plan(), None)["score"] == 0.0


def test_degenerate_plan_scores_zero() -> None:
    plan = MacroPlan(targets={"208": 0.0}, rationale="x", source="preset", steps=[], clamped=[])
    assert macro_adherence(plan, {"protein_pct": 0.3, "fat_pct": 0.3})["score"] == 0.0
