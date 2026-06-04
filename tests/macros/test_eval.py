"""Unit tests for src/dietrace/macros/eval.py.

``evaluate_macro_plan(profile, plan)`` is the online-eval counterpart for macro
plans: a deterministic, zero-LLM accountability check that mirrors the structure
of ``src/dietrace/evals/online.py``. It scores two axes:

  * consistency — does the Atwater identity hold? (4P + 4C + 9F ≈ kcal)
  * safety — is protein in [1.2, 2.4] g/kg and fat in [0.15, 0.40] of kcal?

A clean plan (one produced by ``compute_targets`` or a preset) passes both axes
and returns ``pass=True``. A plan with Atwater drift or out-of-physiological-bounds
macros fails the right axis and carries a machine flag + human reason.
"""

from __future__ import annotations

from dietrace.macros.eval import evaluate_macro_plan
from dietrace.macros.models import MacroPlan, MacroProfile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _profile(**kw) -> MacroProfile:
    defaults = dict(
        age=30, sex="male", height_cm=175.0, weight_kg=80.0,
        activity="moderate", goal="maintain",
    )
    defaults.update(kw)
    return MacroProfile(**defaults)


def _plan(kcal: float, protein: float, carb: float, fat: float) -> MacroPlan:
    """A MacroPlan with the given raw macro values (no rounding)."""
    return MacroPlan(
        targets={"208": kcal, "203": protein, "205": carb, "204": fat},
        rationale="test",
        source="formula",
        steps=[],
        clamped=[],
    )


def _clean_plan(weight_kg: float = 80.0, kcal: float = 2000.0) -> tuple[MacroProfile, MacroPlan]:
    """
    A Atwater-consistent plan whose macros are in physiological bounds for
    an 80 kg person on 2000 kcal:
      protein 150 g → 1.875 g/kg (in [1.2, 2.4])
      fat     66.7 g → 30% of kcal (in [15%, 40%])
      carb    200 g → remainder
    Atwater: 4*150 + 4*200 + 9*66.7 = 2000.3 (< 5% of 2000 → consistent)
    """
    profile = _profile(weight_kg=weight_kg)
    # Build Atwater-exact carb from the other values to avoid drift.
    protein, fat = 150.0, 66.7
    carb = round((kcal - protein * 4.0 - fat * 9.0) / 4.0, 1)
    return profile, _plan(kcal, protein, carb, fat)


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_returns_expected_shape() -> None:
    profile, plan = _clean_plan()
    result = evaluate_macro_plan(profile, plan)
    assert set(result) == {"score", "pass", "consistency", "safety", "flags", "reasons"}
    assert isinstance(result["score"], float)
    assert isinstance(result["pass"], bool)
    assert isinstance(result["flags"], list)
    assert isinstance(result["reasons"], list)
    assert isinstance(result["consistency"], dict)
    assert isinstance(result["safety"], dict)


def test_consistency_sub_result_has_score() -> None:
    profile, plan = _clean_plan()
    result = evaluate_macro_plan(profile, plan)
    assert "score" in result["consistency"]
    assert 0.0 <= result["consistency"]["score"] <= 1.0


def test_safety_sub_result_has_score() -> None:
    profile, plan = _clean_plan()
    result = evaluate_macro_plan(profile, plan)
    assert "score" in result["safety"]
    assert 0.0 <= result["safety"]["score"] <= 1.0


# ---------------------------------------------------------------------------
# Clean plan passes
# ---------------------------------------------------------------------------


def test_clean_plan_score_is_one() -> None:
    profile, plan = _clean_plan()
    result = evaluate_macro_plan(profile, plan)
    assert result["score"] == 1.0


def test_clean_plan_pass_is_true() -> None:
    profile, plan = _clean_plan()
    result = evaluate_macro_plan(profile, plan)
    assert result["pass"] is True


def test_clean_plan_no_flags() -> None:
    profile, plan = _clean_plan()
    result = evaluate_macro_plan(profile, plan)
    assert result["flags"] == []


def test_clean_plan_no_reasons() -> None:
    profile, plan = _clean_plan()
    result = evaluate_macro_plan(profile, plan)
    assert result["reasons"] == []


# ---------------------------------------------------------------------------
# Consistency — Atwater identity
# ---------------------------------------------------------------------------


def test_atwater_inconsistent_flags_consistency() -> None:
    """A plan where 4P+4C+9F >> kcal is flagged for consistency."""
    # Atwater: 4*200 + 4*200 + 9*80 = 2320 vs kcal=2000 → 16% off → flag
    profile = _profile()
    plan = _plan(kcal=2000.0, protein=200.0, carb=200.0, fat=80.0)
    result = evaluate_macro_plan(profile, plan)
    assert "atwater_inconsistent" in result["flags"]
    assert result["pass"] is False
    assert any("atwater" in r.lower() or "kcal" in r.lower() or "energy" in r.lower()
               for r in result["reasons"])


def test_atwater_inconsistent_lowers_score() -> None:
    profile = _profile()
    plan = _plan(kcal=2000.0, protein=200.0, carb=200.0, fat=80.0)
    result = evaluate_macro_plan(profile, plan)
    assert result["score"] < 1.0


def test_consistency_sub_score_is_one_for_clean_plan() -> None:
    profile, plan = _clean_plan()
    result = evaluate_macro_plan(profile, plan)
    assert result["consistency"]["score"] == 1.0


def test_consistency_sub_score_less_than_one_for_drift() -> None:
    profile = _profile()
    plan = _plan(kcal=2000.0, protein=200.0, carb=200.0, fat=80.0)
    result = evaluate_macro_plan(profile, plan)
    assert result["consistency"]["score"] < 1.0


# ---------------------------------------------------------------------------
# Safety — protein g/kg
# ---------------------------------------------------------------------------


def test_protein_too_low_flags_safety() -> None:
    """Protein below 1.2 g/kg (80 kg → min 96 g) is flagged."""
    profile = _profile(weight_kg=80.0)
    # protein=50g, fat=66.7g, kcal=2000, carb=(2000-200-600.3)/4 ≈ 299.9g — consistent
    fat = 66.7
    protein = 50.0
    carb = round((2000.0 - protein * 4.0 - fat * 9.0) / 4.0, 1)
    plan = _plan(kcal=2000.0, protein=protein, carb=carb, fat=fat)
    result = evaluate_macro_plan(profile, plan)
    assert "protein_out_of_bounds" in result["flags"]
    assert result["pass"] is False
    assert any("protein" in r.lower() for r in result["reasons"])


def test_protein_too_high_flags_safety() -> None:
    """Protein above 2.4 g/kg (80 kg → max 192 g) is flagged.
    fat=50g (22.5% of kcal) is within bounds so only protein fails."""
    profile = _profile(weight_kg=80.0)
    fat = 50.0  # 50*9/2000 = 22.5% — inside [15%, 40%]
    protein = 250.0
    carb = round((2000.0 - protein * 4.0 - fat * 9.0) / 4.0, 1)
    plan = _plan(kcal=2000.0, protein=protein, carb=carb, fat=fat)
    result = evaluate_macro_plan(profile, plan)
    assert "protein_out_of_bounds" in result["flags"]
    assert "fat_out_of_bounds" not in result["flags"]
    assert result["pass"] is False


# ---------------------------------------------------------------------------
# Safety — fat fraction
# ---------------------------------------------------------------------------


def test_fat_too_low_flags_safety() -> None:
    """Fat below 15% of kcal is flagged."""
    profile = _profile(weight_kg=80.0)
    # fat=20g (180 kcal = 9%) — Atwater-consistent at 2000 kcal
    fat = 20.0
    protein = 150.0
    carb = round((2000.0 - protein * 4.0 - fat * 9.0) / 4.0, 1)
    plan = _plan(kcal=2000.0, protein=protein, carb=carb, fat=fat)
    result = evaluate_macro_plan(profile, plan)
    assert "fat_out_of_bounds" in result["flags"]
    assert result["pass"] is False
    assert any("fat" in r.lower() for r in result["reasons"])


def test_fat_too_high_flags_safety() -> None:
    """Fat above 40% of kcal is flagged."""
    profile = _profile(weight_kg=80.0)
    # fat=100g (900 kcal = 45%) — Atwater-consistent at 2000 kcal
    fat = 100.0
    protein = 150.0
    carb = round((2000.0 - protein * 4.0 - fat * 9.0) / 4.0, 1)
    plan = _plan(kcal=2000.0, protein=protein, carb=carb, fat=fat)
    result = evaluate_macro_plan(profile, plan)
    assert "fat_out_of_bounds" in result["flags"]
    assert result["pass"] is False


# ---------------------------------------------------------------------------
# Safety sub-score
# ---------------------------------------------------------------------------


def test_safety_sub_score_is_one_for_clean_plan() -> None:
    profile, plan = _clean_plan()
    result = evaluate_macro_plan(profile, plan)
    assert result["safety"]["score"] == 1.0


def test_safety_sub_score_less_than_one_when_protein_out_of_bounds() -> None:
    profile = _profile(weight_kg=80.0)
    fat = 66.7
    protein = 50.0
    carb = round((2000.0 - protein * 4.0 - fat * 9.0) / 4.0, 1)
    plan = _plan(kcal=2000.0, protein=protein, carb=carb, fat=fat)
    result = evaluate_macro_plan(profile, plan)
    assert result["safety"]["score"] < 1.0


def test_safety_sub_score_less_than_one_when_fat_out_of_bounds() -> None:
    profile = _profile(weight_kg=80.0)
    fat = 20.0
    protein = 150.0
    carb = round((2000.0 - protein * 4.0 - fat * 9.0) / 4.0, 1)
    plan = _plan(kcal=2000.0, protein=protein, carb=carb, fat=fat)
    result = evaluate_macro_plan(profile, plan)
    assert result["safety"]["score"] < 1.0


# ---------------------------------------------------------------------------
# Both axes fail
# ---------------------------------------------------------------------------


def test_both_axes_fail_accumulate_flags() -> None:
    """A plan that is both inconsistent and out-of-bounds carries both flags."""
    profile = _profile(weight_kg=80.0)
    # Atwater: 4*250 + 4*50 + 9*150 = 1000 + 200 + 1350 = 2550 ≠ 2000 → inconsistent
    # protein=250g > 192g max → protein out of bounds
    # fat=150g (1350 kcal = 67.5%) > 40% → fat out of bounds
    plan = _plan(kcal=2000.0, protein=250.0, carb=50.0, fat=150.0)
    result = evaluate_macro_plan(profile, plan)
    assert "atwater_inconsistent" in result["flags"]
    assert "protein_out_of_bounds" in result["flags"]
    assert "fat_out_of_bounds" in result["flags"]
    assert result["score"] < 1.0
    assert result["pass"] is False


# ---------------------------------------------------------------------------
# Boundary conditions
# ---------------------------------------------------------------------------


def test_score_is_float_in_unit_interval() -> None:
    profile, plan = _clean_plan()
    result = evaluate_macro_plan(profile, plan)
    assert 0.0 <= result["score"] <= 1.0


def test_protein_at_minimum_boundary_passes() -> None:
    """Protein exactly at 1.2 g/kg (80 kg → 96 g) is acceptable."""
    profile = _profile(weight_kg=80.0)
    protein = 80.0 * 1.2  # = 96.0
    fat = 66.7
    carb = round((2000.0 - protein * 4.0 - fat * 9.0) / 4.0, 1)
    plan = _plan(kcal=2000.0, protein=protein, carb=carb, fat=fat)
    result = evaluate_macro_plan(profile, plan)
    assert "protein_out_of_bounds" not in result["flags"]


def test_protein_at_maximum_boundary_passes() -> None:
    """Protein exactly at 2.4 g/kg (80 kg → 192 g) is acceptable."""
    profile = _profile(weight_kg=80.0)
    protein = 80.0 * 2.4  # = 192.0
    fat = 33.3
    carb = round((2000.0 - protein * 4.0 - fat * 9.0) / 4.0, 1)
    plan = _plan(kcal=2000.0, protein=protein, carb=carb, fat=fat)
    result = evaluate_macro_plan(profile, plan)
    assert "protein_out_of_bounds" not in result["flags"]


def test_fat_at_minimum_boundary_passes() -> None:
    """Fat at ~15% of kcal is acceptable (round(0.15*2000/9,1)=33.3g gives 0.1485;
    use 33.4g → 0.1503 which sits inside the [15%, 40%] bound)."""
    profile = _profile(weight_kg=80.0)
    fat = 33.4  # 33.4*9/2000 = 0.1503 > 0.15
    protein = 150.0
    carb = round((2000.0 - protein * 4.0 - fat * 9.0) / 4.0, 1)
    plan = _plan(kcal=2000.0, protein=protein, carb=carb, fat=fat)
    result = evaluate_macro_plan(profile, plan)
    assert "fat_out_of_bounds" not in result["flags"]


def test_fat_at_maximum_boundary_passes() -> None:
    """Fat at ~40% of kcal is acceptable (88.8g → 0.3996 which sits inside the bound)."""
    profile = _profile(weight_kg=80.0)
    fat = 88.8  # 88.8*9/2000 = 0.3996 < 0.40
    protein = 100.0
    carb = round((2000.0 - protein * 4.0 - fat * 9.0) / 4.0, 1)
    plan = _plan(kcal=2000.0, protein=protein, carb=carb, fat=fat)
    result = evaluate_macro_plan(profile, plan)
    assert "fat_out_of_bounds" not in result["flags"]


# ---------------------------------------------------------------------------
# Zero-kcal plan (edge case)
# ---------------------------------------------------------------------------


def test_zero_kcal_plan_does_not_crash() -> None:
    """A zero-kcal plan is degenerate but must not raise."""
    profile = _profile()
    plan = _plan(kcal=0.0, protein=0.0, carb=0.0, fat=0.0)
    result = evaluate_macro_plan(profile, plan)
    assert isinstance(result["score"], float)


def test_zero_weight_protein_axis_skipped() -> None:
    """A zero-weight profile cannot compute g/kg — protein axis is skipped, not flagged."""
    profile = MacroProfile(
        age=30, sex="male", height_cm=175.0, weight_kg=0.0,
        activity="moderate", goal="maintain",
    )
    fat = 66.7
    protein = 150.0
    carb = round((2000.0 - protein * 4.0 - fat * 9.0) / 4.0, 1)
    plan = _plan(kcal=2000.0, protein=protein, carb=carb, fat=fat)
    result = evaluate_macro_plan(profile, plan)
    assert "protein_out_of_bounds" not in result["flags"]
    assert isinstance(result["score"], float)


# ---------------------------------------------------------------------------
# Reason content
# ---------------------------------------------------------------------------


def test_inconsistency_reason_includes_kcal_values() -> None:
    """The inconsistency reason mentions the Atwater estimate and the target."""
    profile = _profile()
    plan = _plan(kcal=2000.0, protein=200.0, carb=200.0, fat=80.0)
    result = evaluate_macro_plan(profile, plan)
    reasons = " ".join(result["reasons"]).lower()
    # At least one of: a number, "kcal", "atwater", "energy" should appear
    assert any(token in reasons for token in ["kcal", "atwater", "energy", "2000", "2320"])


def test_protein_reason_mentions_protein() -> None:
    profile = _profile(weight_kg=80.0)
    fat = 66.7
    protein = 50.0
    carb = round((2000.0 - protein * 4.0 - fat * 9.0) / 4.0, 1)
    plan = _plan(kcal=2000.0, protein=protein, carb=carb, fat=fat)
    result = evaluate_macro_plan(profile, plan)
    assert any("protein" in r.lower() for r in result["reasons"])


def test_fat_reason_mentions_fat() -> None:
    profile = _profile(weight_kg=80.0)
    fat = 20.0
    protein = 150.0
    carb = round((2000.0 - protein * 4.0 - fat * 9.0) / 4.0, 1)
    plan = _plan(kcal=2000.0, protein=protein, carb=carb, fat=fat)
    result = evaluate_macro_plan(profile, plan)
    assert any("fat" in r.lower() for r in result["reasons"])
