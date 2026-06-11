"""Unit tests for src/dietrace/evals/evaluators.py.

These pin the numeric, zero-LLM evaluators that hold the agent's macro accuracy
to account. ``macro_pct_error`` computes a per-macro |%error| between
the agent's logged totals and the case's USDA ground truth, returning an
``EvalResult{score,label,explanation}`` with the raw per-macro magnitudes
carried in ``metadata`` for the supervisor. The tests
exercise known values so the arithmetic is locked, not just the plumbing. No DB
or network is touched.
"""

import math

import pytest

from dietrace.evals.evaluators import (
    PHOENIX_EVALUATORS,
    EvalResult,
    calorie_accuracy,
    fiber_accuracy,
    macro_mae,
    macro_pct_error,
    micro_panel_accuracy,
    portion_error,
    sodium_accuracy,
    total_sugars_accuracy,
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


def test_macro_pct_error_honors_per_case_tolerance() -> None:
    """The pass/fail label respects a per-case ±band, not just the ±15% default.

    : the tolerance is "configurable per case". The same mean error must
    fail a tighter band and pass a looser one, matching the other evaluators.
    """
    # Mean |%error| is 8.75% (see test_macro_pct_error_known_values).
    output = _totals(calories=440.0, protein_g=18.0, fat_g=34.0, carb_g=10.0)
    expected = {"calories": 400.0, "protein_g": 20.0, "fat_g": 40.0, "carb_g": 10.0}

    assert macro_pct_error(output, expected, {"tolerance": 0.05}).label == "fail"
    assert macro_pct_error(output, expected, {"tolerance": 0.20}).label == "pass"
    # Default (no metadata) still passes at ±15%.
    assert macro_pct_error(output, expected).label == "pass"


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


# --- macro_mae -------------------------------------------------------


def test_macro_mae_known_values() -> None:
    """MAE is the mean absolute error in native units; the score is NMAE-based.

     pairs macro_mae with macro_pct_error: same accuracy signal, but the
    raw magnitude carried for the supervisor is the absolute error (g/kcal), not
    a percentage. The [0,1] score normalizes the MAE against the expected total
    (NMAE = Σ|err| / Σ|expected|), so it weights by magnitude rather than
    equal-weighting per-macro percentages.
    """
    output = _totals(calories=440.0, protein_g=18.0, fat_g=34.0, carb_g=10.0)
    expected = {"calories": 400.0, "protein_g": 20.0, "fat_g": 40.0, "carb_g": 10.0}

    result = macro_mae(output, expected)

    per_macro = result.metadata["per_macro_abs"]
    assert per_macro["calories"] == 40.0  # |440-400|
    assert per_macro["protein_g"] == 2.0  # |18-20|
    assert per_macro["fat_g"] == 6.0  # |34-40|
    assert per_macro["carb_g"] == 0.0  # exact
    assert result.metadata["mae"] == 12.0  # (40+2+6+0)/4
    # NMAE = 48 / 470; score = 1 - NMAE.
    assert abs(result.metadata["nmae"] - 48.0 / 470.0) < 1e-12
    assert abs(result.score - (1.0 - 48.0 / 470.0)) < 1e-12
    assert result.label == "pass"  # within the default ±15% band


def test_macro_mae_perfect_match() -> None:
    """An exact match scores 1.0 with zero absolute error across every macro."""
    output = _totals(calories=400.0, protein_g=20.0, fat_g=40.0, carb_g=10.0)
    expected = {"calories": 400.0, "protein_g": 20.0, "fat_g": 40.0, "carb_g": 10.0}

    result = macro_mae(output, expected)

    assert result.score == 1.0
    assert result.metadata["mae"] == 0.0
    assert all(err == 0.0 for err in result.metadata["per_macro_abs"].values())
    assert result.label == "pass"


def test_macro_mae_large_error_fails_and_clamps() -> None:
    """A gross overestimate fails the band; the score clamps at 0.0, not negative."""
    output = _totals(calories=1200.0, protein_g=80.0, fat_g=120.0, carb_g=40.0)
    expected = {"calories": 400.0, "protein_g": 20.0, "fat_g": 40.0, "carb_g": 10.0}

    result = macro_mae(output, expected)

    assert result.metadata["nmae"] > 1.0  # Σ|err| 970 > Σ|exp| 470
    assert result.score == 0.0
    assert result.label == "fail"


def test_macro_mae_honors_per_case_tolerance() -> None:
    """The pass/fail label respects a per-case ±band like the other evaluators."""
    output = _totals(calories=440.0, protein_g=18.0, fat_g=34.0, carb_g=10.0)
    expected = {"calories": 400.0, "protein_g": 20.0, "fat_g": 40.0, "carb_g": 10.0}

    # NMAE ≈ 10.2%, between the two bands.
    assert macro_mae(output, expected, {"tolerance": 0.05}).label == "fail"
    assert macro_mae(output, expected, {"tolerance": 0.20}).label == "pass"
    assert macro_mae(output, expected).label == "pass"  # default ±15%


def test_macro_mae_all_zero_expected() -> None:
    """All-zero ground truth: exact zero is perfect; any amount is full error."""
    expected = {"calories": 0.0, "protein_g": 0.0, "fat_g": 0.0, "carb_g": 0.0}

    on_target = _totals(calories=0.0, protein_g=0.0, fat_g=0.0, carb_g=0.0)
    assert macro_mae(on_target, expected).score == 1.0

    off_target = _totals(calories=5.0, protein_g=0.0, fat_g=0.0, carb_g=0.0)
    result = macro_mae(off_target, expected)
    assert result.metadata["nmae"] == 1.0
    assert result.score == 0.0
    assert result.label == "fail"


def test_macro_mae_accepts_expected_nutrition_model() -> None:
    """``expected`` may be an ExpectedNutrition model, not just a dict."""
    output = _totals(calories=420.0, protein_g=20.0, fat_g=40.0, carb_g=10.0)
    expected = ExpectedNutrition(
        calories=400.0, protein_g=20.0, fat_g=40.0, carb_g=10.0
    )

    result = macro_mae(output, expected)

    assert result.metadata["per_macro_abs"]["calories"] == 20.0
    assert result.metadata["per_macro_abs"]["protein_g"] == 0.0


def test_macro_mae_registered_in_phoenix_list() -> None:
    """macro_mae is wired into PHOENIX_EVALUATORS by name."""
    assert "macro_mae" in {fn.__name__ for fn in PHOENIX_EVALUATORS}


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


def test_micro_panel_na_for_full_tier_without_micros() -> None:
    """A full-tier case with no micro ground truth is n/a, not a crash.

    The ``not micros`` guard is the second arm of the dispatch: the docstring
    promises "any case without an expected micro panel" returns n/a, and the
    guard is load-bearing — an empty panel would otherwise divide a mean by
    ``len(per_micro) == 0``. Mutation-verified: dropping ``or not micros`` makes
    this raise ``ZeroDivisionError``.
    """
    output = {"totals": [{"code": "307", "name": "Sodium", "amount": 70.0, "unit": "mg"}]}
    expected = {"calories": 1, "protein_g": 1, "fat_g": 1, "carb_g": 1, "micros": {}}

    result = micro_panel_accuracy(output, expected, {"nutrient_tier": "full"})

    assert result.label == "n/a"
    assert result.score == 1.0


def test_micro_panel_na_when_micros_key_absent() -> None:
    """A case carrying no ``micros`` key at all (and no tier) is n/a, not a crash.

    Exercises the same ``not micros`` guard via the ``_expected_value(...) or {}``
    coercion when ``micros`` is absent rather than empty, with metadata omitted.
    """
    output = {"totals": [{"code": "307", "name": "Sodium", "amount": 70.0, "unit": "mg"}]}
    expected = {"calories": 1, "protein_g": 1, "fat_g": 1, "carb_g": 1}

    result = micro_panel_accuracy(output, expected)

    assert result.label == "n/a"
    assert result.score == 1.0


# --- fiber/sodium/sugar single-nutrient evaluators (10.2) ---------------------


def test_fiber_accuracy_known_value() -> None:
    """Fiber (291) 10% over → score 0.9, raw error in metadata, within the band."""
    output = {"totals": [{"code": "291", "name": "Fiber", "amount": 11.0, "unit": "g"}]}
    expected = {"calories": 1, "protein_g": 1, "fat_g": 1, "carb_g": 1, "micros": {"291": 10.0}}

    result = fiber_accuracy(output, expected)

    assert result.metadata["fiber_pct_error"] == 0.10  # |11-10|/10
    assert result.metadata["code"] == "291"
    assert result.score == 0.9
    assert result.label == "pass"


def test_sodium_accuracy_known_value_and_unit() -> None:
    """Sodium (307) 10% over → 0.9; the explanation carries the mg unit."""
    output = {"totals": [{"code": "307", "name": "Sodium", "amount": 660.0, "unit": "mg"}]}
    expected = {"calories": 1, "protein_g": 1, "fat_g": 1, "carb_g": 1, "micros": {"307": 600.0}}

    result = sodium_accuracy(output, expected)

    assert result.metadata["sodium_pct_error"] == 0.10  # |660-600|/600
    assert result.score == 0.9
    assert result.label == "pass"
    assert "mg" in result.explanation


def test_sodium_accuracy_fails_outside_band() -> None:
    """A 50% sodium overestimate fails the default ±15% band."""
    output = {"totals": [{"code": "307", "name": "Sodium", "amount": 900.0, "unit": "mg"}]}
    expected = {"calories": 1, "protein_g": 1, "fat_g": 1, "carb_g": 1, "micros": {"307": 600.0}}

    assert sodium_accuracy(output, expected).label == "fail"


def test_total_sugars_accuracy_known_value() -> None:
    """Total sugars (269) exact match → score 1.0, zero error."""
    output = {"totals": [{"code": "269", "name": "Sugars", "amount": 24.0, "unit": "g"}]}
    expected = {"calories": 1, "protein_g": 1, "fat_g": 1, "carb_g": 1, "micros": {"269": 24.0}}

    result = total_sugars_accuracy(output, expected)

    assert result.metadata["total_sugars_pct_error"] == 0.0
    assert result.score == 1.0
    assert result.label == "pass"


def test_fiber_accuracy_na_without_ground_truth() -> None:
    """No fiber in the expected micro panel → n/a, not a spurious score."""
    output = {"totals": [{"code": "291", "name": "Fiber", "amount": 5.0, "unit": "g"}]}
    expected = {"calories": 1, "protein_g": 1, "fat_g": 1, "carb_g": 1, "micros": {"307": 600.0}}

    assert fiber_accuracy(output, expected).label == "n/a"


def test_sodium_accuracy_missing_total_is_full_error() -> None:
    """Ground truth present but the agent logged no sodium → full error, fails."""
    output = {"totals": [{"code": "208", "name": "Energy", "amount": 200.0, "unit": "kcal"}]}
    expected = {"calories": 1, "protein_g": 1, "fat_g": 1, "carb_g": 1, "micros": {"307": 600.0}}

    result = sodium_accuracy(output, expected)

    assert result.metadata["sodium_pct_error"] == 1.0  # 0 vs 600
    assert result.score == 0.0
    assert result.label == "fail"


def test_sodium_accuracy_scored_on_label_tier() -> None:
    """Unlike the full micro panel, sodium is scored on branded label cases too."""
    output = {"totals": [{"code": "307", "name": "Sodium", "amount": 600.0, "unit": "mg"}]}
    expected = {"calories": 1, "protein_g": 1, "fat_g": 1, "carb_g": 1, "micros": {"307": 600.0}}

    result = sodium_accuracy(output, expected, {"nutrient_tier": "label"})

    assert result.label == "pass"
    assert result.score == 1.0


def test_fiber_accuracy_accepts_expected_nutrition_model() -> None:
    """``expected`` may be an ExpectedNutrition model carrying the micro panel."""
    output = {"totals": [{"code": "291", "name": "Fiber", "amount": 9.0, "unit": "g"}]}
    expected = ExpectedNutrition(
        calories=1, protein_g=1, fat_g=1, carb_g=1, micros={"291": 9.0}
    )

    assert fiber_accuracy(output, expected).score == 1.0


def test_new_evaluators_registered_in_phoenix_list() -> None:
    """The three new evaluators are wired into PHOENIX_EVALUATORS by name (10.2)."""
    names = {fn.__name__ for fn in PHOENIX_EVALUATORS}
    assert {"fiber_accuracy", "sodium_accuracy", "total_sugars_accuracy"} <= names


# --- non-finite output stays in the [0,1] contract -------------------
#
# Every numeric evaluator funnels through ``_pct_error`` and normalizes its score
# with ``1 - min(err, 1)``.  requires scores "normalized to [0,1] for
# Phoenix charts" so "regressions flag". But ``min(nan, 1.0)`` is ``nan`` in
# Python, so a non-finite agent total (a NaN/inf amount reaching an evaluator from
# a replayed/stored output or an MCP-written dataset point) would yield a ``nan``
# score — which corrupts Phoenix aggregation and, worse, does NOT flag as a
# regression (``nan <= tol`` is False, but a nan score poisons any mean). A broken
# output must instead score as the worst possible miss (error 1.0 → score 0.0).


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_calorie_accuracy_non_finite_total_is_worst_miss_not_nan(bad: float) -> None:
    output = _totals(calories=bad, protein_g=20.0, fat_g=40.0, carb_g=10.0)
    expected = {"calories": 400.0, "protein_g": 20.0, "fat_g": 40.0, "carb_g": 10.0}

    result = calorie_accuracy(output, expected)

    assert math.isfinite(result.score)
    assert result.score == 0.0  # unusable output → worst miss, keeps [0,1]
    assert result.metadata["calorie_pct_error"] == 1.0
    assert result.label == "fail"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_macro_pct_error_non_finite_macro_keeps_score_finite(bad: float) -> None:
    # One poisoned macro must not NaN out the whole mean-driven score.
    output = _totals(calories=400.0, protein_g=bad, fat_g=40.0, carb_g=10.0)
    expected = {"calories": 400.0, "protein_g": 20.0, "fat_g": 40.0, "carb_g": 10.0}

    result = macro_pct_error(output, expected)

    assert math.isfinite(result.score)
    # One poisoned macro (err 1.0) among three exact (0.0) → mean 0.25 → score 0.75.
    assert result.score == 0.75
    assert result.metadata["per_macro"]["protein_g"] == 1.0  # bad macro → full error
    assert math.isfinite(result.metadata["mean_pct_error"])


# --- a garbled per-case tolerance falls back to the default band -----
#
# The pass/fail band is overridable per case via ``metadata["tolerance"]``, and
# that metadata can arrive from a replayed/stored case or an MCP-written dataset
# point — the same untrusted channel ``_pct_error`` already guards against. An
# unusable tolerance must degrade to the ±15% default rather than crash the
# evaluator (a non-numeric value makes ``float()`` raise, aborting the whole
# experiment run) or silently corrupt every label (``err <= nan`` is always
# False, flagging a false regression; ``+inf`` masks real ones; a negative band
# flips pass/fail). The score is unaffected by the band, so only the label is at
# stake — and the label must reflect the real ±15% default verdict.


@pytest.mark.parametrize("bad", ["abc", None, float("nan"), float("inf"), -0.10])
def test_macro_pct_error_garbled_tolerance_falls_back_to_default(bad: object) -> None:
    # mean |%error| 0.0875 — passes under the default ±15% but would fail at ±5%.
    output = _totals(calories=440.0, protein_g=18.0, fat_g=34.0, carb_g=10.0)
    expected = {"calories": 400.0, "protein_g": 20.0, "fat_g": 40.0, "carb_g": 10.0}

    result = macro_pct_error(output, expected, {"tolerance": bad})

    assert result.label == "pass"  # default ±15% band restored, no crash
    assert result.score == 0.9125  # score never depended on the band


@pytest.mark.parametrize("bad", ["", {}, None, float("inf"), float("-inf"), -1.0])
def test_within_tolerance_garbled_tolerance_uses_default(bad: object) -> None:
    # Every macro exact except fat at 12% off — inside ±15%, outside ±5%.
    output = _totals(calories=400.0, protein_g=20.0, fat_g=44.8, carb_g=10.0)
    expected = {"calories": 400.0, "protein_g": 20.0, "fat_g": 40.0, "carb_g": 10.0}

    result = within_tolerance(output, expected, {"tolerance": bad})

    assert result.label == "pass"  # default ±15% restored
    assert result.metadata["tolerance"] == 0.15


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_macro_mae_non_finite_macro_is_worst_miss_not_nan(bad: float) -> None:
    # macro_mae scores ABSOLUTE error, so it bypasses _pct_error's guard entirely:
    # abs(nan - 20) is nan, the NMAE becomes nan, and 1 - min(nan, 1.0) is a nan
    # score — off the [0,1] contract  promises, and a nan never flags as a
    # regression. An unusable macro must be a full miss (NMAE ≥ 1 → score 0.0), like
    # the percent-based evaluators above.
    output = _totals(calories=400.0, protein_g=bad, fat_g=40.0, carb_g=10.0)
    expected = {"calories": 400.0, "protein_g": 20.0, "fat_g": 40.0, "carb_g": 10.0}

    result = macro_mae(output, expected)

    assert math.isfinite(result.score)
    assert result.score == 0.0  # unusable output → worst miss, keeps [0,1]
    assert result.label == "fail"
    assert math.isfinite(result.metadata["nmae"])  # the score-companion stays finite
    # The bad macro's raw error is +inf (well-ordered), never a comparison-breaking
    # nan — including the unnormalized native-unit MAE the supervisor may read.
    assert result.metadata["per_macro_abs"]["protein_g"] == float("inf")
    assert result.metadata["mae"] == float("inf")
    assert not math.isnan(result.metadata["mae"])
