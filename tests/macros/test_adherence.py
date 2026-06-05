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


def test_empty_preference_dict_scores_zero() -> None:
    # {} is falsy; the `not preference` guard must treat it identically to None
    # so callers that pass an empty saved-preference dict get the same zero result.
    a = macro_adherence(_plan(), {})
    assert a == {"score": 0.0, "protein_delta": 0.0, "fat_delta": 0.0}


def test_score_floored_at_zero_when_total_delta_exceeds_one() -> None:
    # A plan with all calories from carbs (protein=0, fat=0) vs a preference
    # expecting 55 % protein + 55 % fat has a combined absolute delta of 1.1 — the
    # max(0.0, ...) floor keeps the score non-negative.
    all_carb = MacroPlan(
        targets={"208": 2000.0, "203": 0.0, "204": 0.0, "205": 500.0},
        rationale="x", source="formula", steps=[], clamped=[],
    )
    a = macro_adherence(all_carb, {"protein_pct": 0.55, "fat_pct": 0.55})
    assert a["score"] == 0.0
    assert a["protein_delta"] < 0.0
    assert a["fat_delta"] < 0.0


def test_positive_deltas_when_plan_split_exceeds_preference() -> None:
    # Plan has MORE protein (0.30) and fat (0.198) than the user's low-fat preference.
    # Deltas should be positive and score should be strictly below 1.0.
    a = macro_adherence(_plan(), {"protein_pct": 0.20, "fat_pct": 0.10})
    assert a["protein_delta"] > 0.0  # plan protein_pct (0.30) > preference (0.20)
    assert a["fat_delta"] > 0.0      # plan fat_pct (0.198) > preference (0.10)
    assert 0.0 < a["score"] < 1.0
