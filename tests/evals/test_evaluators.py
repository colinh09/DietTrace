"""Unit tests for src/dietrace/evals/evaluators.py.

These pin the numeric, zero-LLM evaluators that hold the agent's macro accuracy
to account. ``macro_pct_error`` computes a per-macro |%error| between
the agent's logged totals and the case's USDA ground truth, returning an
``EvalResult{score,label,explanation}`` (the shape ported from axon) with the
raw per-macro magnitudes carried in ``metadata`` for the supervisor. The tests
exercise known values so the arithmetic is locked, not just the plumbing. No DB
or network is touched.
"""

from dietrace.evals.evaluators import (
    EvalResult,
    calorie_accuracy,
    macro_pct_error,
    micro_panel_accuracy,
    portion_error,
    within_tolerance,
)
from dietrace.evals.schema import ExpectedNutrition


def _totals(calories: float, protein_g: float, fat_g: float, carb_g: float) -> dict:
    """Build an agent output in the LoggedMeal shape: totals keyed by USDA code."""
    return {
        "totals": [
            {"code": "208", "name": "Energy", "amount": calories, "unit": "kcal"},
            {"code": "203", "name": "Protein", "amount": protein_g, "unit": "g"},
            {"code": "204", "name": "Total lipid (fat)", "amount": fat_g, "unit": "g"},
            {"code": "205", "name": "Carbohydrate", "amount": carb_g, "unit": "g"},
        ]
    }


def test_macro_pct_error_known_values() -> None:
    """Per-macro |%error| matches hand-computed values; mean drives the score."""
    output = _totals(calories=440.0, protein_g=18.0, fat_g=34.0, carb_g=10.0)
    expected = {"calories": 400.0, "protein_g": 20.0, "fat_g": 40.0, "carb_g": 10.0}

    result = macro_pct_error(output, expected)

    per_macro = result.metadata["per_macro"]
    assert per_macro["calories"] == 0.10  # |440-400|/400
    assert per_macro["protein_g"] == 0.10  # |18-20|/20
    assert per_macro["fat_g"] == 0.15  # |34-40|/40
    assert per_macro["carb_g"] == 0.0  # exact
    assert result.metadata["mean_pct_error"] == 0.0875  # (.10+.10+.15+0)/4
    # Normalized to [0,1] for Phoenix charts: 1 - min(mean, 1).
    assert result.score == 0.9125
    assert result.label == "pass"  # mean within the default ±15% band


def test_macro_pct_error_perfect_match() -> None:
    """An exact match scores 1.0 with zero error across every macro."""
    output = _totals(calories=400.0, protein_g=20.0, fat_g=40.0, carb_g=10.0)
    expected = {"calories": 400.0, "protein_g": 20.0, "fat_g": 40.0, "carb_g": 10.0}

    result = macro_pct_error(output, expected)

    assert result.score == 1.0
    assert result.metadata["mean_pct_error"] == 0.0
    assert all(err == 0.0 for err in result.metadata["per_macro"].values())
    assert result.label == "pass"


def test_macro_pct_error_large_error_fails_and_clamps() -> None:
    """A gross overestimate fails the band; the score clamps at 0.0, not negative."""
    output = _totals(calories=1200.0, protein_g=80.0, fat_g=120.0, carb_g=40.0)
    expected = {"calories": 400.0, "protein_g": 20.0, "fat_g": 40.0, "carb_g": 10.0}

    result = macro_pct_error(output, expected)

    # Every macro is 200%+ over: mean error >> 1, so the normalized score floors.
    assert result.metadata["mean_pct_error"] > 1.0
    assert result.score == 0.0
    assert result.label == "fail"


def test_macro_pct_error_accepts_expected_nutrition_model() -> None:
    """``expected`` may be an ExpectedNutrition model, not just a dict."""
    output = _totals(calories=420.0, protein_g=20.0, fat_g=40.0, carb_g=10.0)
    expected = ExpectedNutrition(
        calories=400.0, protein_g=20.0, fat_g=40.0, carb_g=10.0
    )

    result = macro_pct_error(output, expected)

    assert result.metadata["per_macro"]["calories"] == 0.05
    assert result.metadata["per_macro"]["protein_g"] == 0.0


def test_macro_pct_error_zero_expected_macro() -> None:
    """A zero ground-truth macro: exact zero is 0 error, any amount is full error."""
    on_target = _totals(calories=400.0, protein_g=20.0, fat_g=40.0, carb_g=0.0)
    expected = {"calories": 400.0, "protein_g": 20.0, "fat_g": 40.0, "carb_g": 0.0}
    assert macro_pct_error(on_target, expected).metadata["per_macro"]["carb_g"] == 0.0

    off_target = _totals(calories=400.0, protein_g=20.0, fat_g=40.0, carb_g=5.0)
    assert macro_pct_error(off_target, expected).metadata["per_macro"]["carb_g"] == 1.0


def test_eval_result_to_phoenix_carries_metadata() -> None:
    """EvalResult serializes the score/label/explanation plus raw metadata."""
    result = EvalResult(
        score=0.5, label="pass", explanation="x", metadata={"mean_pct_error": 0.5}
    )

    payload = result.to_phoenix()

    assert payload["score"] == 0.5
    assert payload["label"] == "pass"
    assert payload["explanation"] == "x"
    assert payload["metadata"] == {"mean_pct_error": 0.5}


# --- calorie_accuracy (4.3) ---------------------------------------------------


def test_calorie_accuracy_normalizes_and_passes() -> None:
    """Calories 10% over: score 0.9, raw error in metadata, within the band."""
    output = _totals(calories=440.0, protein_g=18.0, fat_g=34.0, carb_g=10.0)
    expected = {"calories": 400.0, "protein_g": 20.0, "fat_g": 40.0, "carb_g": 10.0}

    result = calorie_accuracy(output, expected)

    assert result.metadata["calorie_pct_error"] == 0.10
    assert result.score == 0.9
    assert result.label == "pass"


def test_calorie_accuracy_fails_outside_band() -> None:
    """A 50% calorie overestimate fails the default ±15% band."""
    output = _totals(calories=600.0, protein_g=20.0, fat_g=40.0, carb_g=10.0)
    expected = {"calories": 400.0, "protein_g": 20.0, "fat_g": 40.0, "carb_g": 10.0}

    assert calorie_accuracy(output, expected).label == "fail"


# --- within_tolerance (4.4) ---------------------------------------------------


def test_within_tolerance_passes_when_all_macros_inside_band() -> None:
    """Every macro 5% off → pass at score 1.0."""
    output = _totals(calories=420.0, protein_g=21.0, fat_g=42.0, carb_g=10.5)
    expected = {"calories": 400.0, "protein_g": 20.0, "fat_g": 40.0, "carb_g": 10.0}

    result = within_tolerance(output, expected, {"tolerance": 0.15})

    assert result.label == "pass"
    assert result.score == 1.0


def test_within_tolerance_fails_when_one_macro_exceeds() -> None:
    """Fat 50% over → fail, and the offending macro is named in metadata."""
    output = _totals(calories=400.0, protein_g=20.0, fat_g=60.0, carb_g=10.0)
    expected = {"calories": 400.0, "protein_g": 20.0, "fat_g": 40.0, "carb_g": 10.0}

    result = within_tolerance(output, expected, {"tolerance": 0.15})

    assert result.label == "fail"
    assert result.score == 0.0
    assert "fat_g" in result.metadata["failing"]


# --- portion_error (4.5) ------------------------------------------------------


def test_portion_error_scores_grams() -> None:
    """Estimated 55 g vs ground-truth 50 g → 10% error, passes."""
    output = {"per_item": [{"grams": 55.0}], "totals": []}
    expected = ExpectedNutrition(
        calories=72, protein_g=6.3, fat_g=4.8, carb_g=0.4, grams=50.0
    )

    result = portion_error(output, expected)

    assert result.metadata["expected_grams"] == 50.0
    assert abs(result.metadata["portion_pct_error"] - 0.1) < 1e-9
    assert result.label == "pass"


def test_portion_error_na_without_ground_truth_grams() -> None:
    """No expected grams → n/a, not a spurious score."""
    output = {"per_item": [{"grams": 55.0}], "totals": []}
    expected = {"calories": 1, "protein_g": 1, "fat_g": 1, "carb_g": 1}

    assert portion_error(output, expected).label == "n/a"


# --- micro_panel_accuracy (4.6, two-tier dispatch) ----------------------------


def test_micro_panel_na_for_label_tier() -> None:
    """A branded label-tier case scores micros as n/a."""
    output = {"totals": [{"code": "307", "name": "Sodium", "amount": 70.0, "unit": "mg"}]}
    expected = {
        "calories": 1, "protein_g": 1, "fat_g": 1, "carb_g": 1, "micros": {"307": 71.0}
    }

    result = micro_panel_accuracy(output, expected, {"nutrient_tier": "label"})

    assert result.label == "n/a"


def test_micro_panel_scores_full_tier() -> None:
    """A full-tier case scores the micro panel against ground truth."""
    output = {
        "totals": [
            {"code": "307", "name": "Sodium", "amount": 70.0, "unit": "mg"},
            {"code": "301", "name": "Calcium", "amount": 28.0, "unit": "mg"},
        ]
    }
    expected = {
        "calories": 1, "protein_g": 1, "fat_g": 1, "carb_g": 1,
        "micros": {"307": 71.0, "301": 28.0},
    }

    result = micro_panel_accuracy(output, expected, {"nutrient_tier": "full"})

    assert result.label == "pass"
    assert result.score > 0.9
