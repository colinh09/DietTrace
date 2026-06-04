"""Tests for the macro-plan evaluators.

These pin the offline, zero-LLM macro evaluators that score a computed
``MacroPlan`` against expected target ranges from the macro dataset.
Arithmetic is locked to known values; no DB or network touched.
"""

from dietrace.evals.evaluators import (
    MACRO_PHOENIX_EVALUATORS,
    EvalResult,
    macro_plan_consistency_eval,
    macro_plan_within_range,
)


def _plan(kcal: float, protein_g: float, fat_g: float, carb_g: float) -> dict:
    """Build a minimal MacroPlan dict the macro evaluators accept."""
    return {
        "targets": {
            "208": kcal,
            "203": protein_g,
            "204": fat_g,
            "205": carb_g,
        },
        "rationale": "test plan",
        "source": "formula",
        "steps": [],
        "clamped": [],
    }


def _expected_ranges(
    kcal_min: float, kcal_max: float,
    protein_g_min: float, protein_g_max: float,
    fat_g_min: float, fat_g_max: float,
    carb_g_min: float, carb_g_max: float,
) -> dict:
    """Build a MacroExpectedTargets-shaped dict."""
    return {
        "kcal_min": kcal_min,
        "kcal_max": kcal_max,
        "protein_g_min": protein_g_min,
        "protein_g_max": protein_g_max,
        "fat_g_min": fat_g_min,
        "fat_g_max": fat_g_max,
        "carb_g_min": carb_g_min,
        "carb_g_max": carb_g_max,
    }


# ---------------------------------------------------------------------------
# macro_plan_within_range
# ---------------------------------------------------------------------------


def test_macro_plan_within_range_known_good() -> None:
    """A plan whose targets all fall within expected ranges passes."""
    # Male 30 / 175cm / 75kg / moderate / maintain — formula gives:
    # kcal≈2633, protein≈198g, fat≈88g, carb≈263g
    plan = _plan(kcal=2633.1, protein_g=197.5, fat_g=87.8, carb_g=263.3)
    expected = _expected_ranges(
        kcal_min=2238.0, kcal_max=3028.0,
        protein_g_min=168.0, protein_g_max=227.0,
        fat_g_min=75.0, fat_g_max=101.0,
        carb_g_min=224.0, carb_g_max=303.0,
    )

    result = macro_plan_within_range(plan, expected)

    assert isinstance(result, EvalResult)
    assert result.score == 1.0
    assert result.label == "pass"
    assert result.metadata["failing"] == []


def test_macro_plan_within_range_known_bad() -> None:
    """A plan with targets clearly outside expected ranges fails."""
    plan = _plan(kcal=5000.0, protein_g=20.0, fat_g=5.0, carb_g=10.0)
    expected = _expected_ranges(
        kcal_min=2238.0, kcal_max=3028.0,
        protein_g_min=168.0, protein_g_max=227.0,
        fat_g_min=75.0, fat_g_max=101.0,
        carb_g_min=224.0, carb_g_max=303.0,
    )

    result = macro_plan_within_range(plan, expected)

    assert isinstance(result, EvalResult)
    assert result.score < 1.0
    assert result.label == "fail"
    # kcal, fat, carb are all out of range
    assert len(result.metadata["failing"]) >= 2


def test_macro_plan_within_range_partial_miss() -> None:
    """When only one target is out of range the score is fractional."""
    plan = _plan(kcal=2633.1, protein_g=197.5, fat_g=87.8, carb_g=999.0)  # carb way high
    expected = _expected_ranges(
        kcal_min=2238.0, kcal_max=3028.0,
        protein_g_min=168.0, protein_g_max=227.0,
        fat_g_min=75.0, fat_g_max=101.0,
        carb_g_min=224.0, carb_g_max=303.0,
    )

    result = macro_plan_within_range(plan, expected)

    assert result.label == "fail"
    assert 0.0 < result.score < 1.0
    assert "carb_g" in result.metadata["failing"]


def test_macro_plan_within_range_score_is_fraction_of_passing() -> None:
    """Score equals fraction of the 4 targets that are within range."""
    # kcal and protein pass; fat and carb miss — 2/4 = 0.5
    plan = _plan(kcal=2633.1, protein_g=197.5, fat_g=200.0, carb_g=999.0)
    expected = _expected_ranges(
        kcal_min=2238.0, kcal_max=3028.0,
        protein_g_min=168.0, protein_g_max=227.0,
        fat_g_min=75.0, fat_g_max=101.0,
        carb_g_min=224.0, carb_g_max=303.0,
    )

    result = macro_plan_within_range(plan, expected)

    assert result.score == 0.5


# ---------------------------------------------------------------------------
# macro_plan_consistency_eval
# ---------------------------------------------------------------------------


def test_macro_plan_consistency_eval_passes_consistent() -> None:
    """A plan whose macros satisfy the Atwater identity within tolerance passes."""
    # 4*197.5 + 4*263.3 + 9*87.8 = 790 + 1053.2 + 790.2 = 2633.4 ≈ 2633.1 (<2%)
    plan = _plan(kcal=2633.1, protein_g=197.5, fat_g=87.8, carb_g=263.3)

    result = macro_plan_consistency_eval(plan)

    assert isinstance(result, EvalResult)
    assert result.score == 1.0
    assert result.label == "pass"
    assert "atwater" not in result.explanation.lower() or "consistent" in result.explanation.lower()


def test_macro_plan_consistency_eval_fails_inconsistent() -> None:
    """A plan with a large Atwater drift labels fail and scores below 1."""
    # Claim 2000 kcal but macros sum to 4*100+4*100+9*100 = 2300 — 15% drift
    plan = _plan(kcal=2000.0, protein_g=100.0, fat_g=100.0, carb_g=100.0)

    result = macro_plan_consistency_eval(plan)

    assert result.score < 1.0
    assert result.label == "fail"
    assert "atwater" in result.explanation.lower() or "inconsist" in result.explanation.lower()


def test_macro_plan_consistency_eval_returns_eval_result() -> None:
    """The evaluator always returns an EvalResult instance.

    The all-zero plan hits the first kcal==0 branch (atwater==0 too): both
    sides are zero, so the plan is considered consistent (score=1.0, pass).
    """
    plan = _plan(kcal=0.0, protein_g=0.0, fat_g=0.0, carb_g=0.0)
    result = macro_plan_consistency_eval(plan)
    assert isinstance(result, EvalResult)
    assert result.score == 1.0
    assert result.label == "pass"


def test_macro_plan_consistency_eval_zero_kcal_nonzero_atwater_fails() -> None:
    """kcal=0 but macros give a nonzero Atwater estimate: pins the second
    kcal==0 branch in macro_plan_consistency_eval (score=0.0, label='fail').

    Without this branch the code would reach ``abs(atwater - kcal) / kcal``
    and raise ZeroDivisionError. The existing all-zero test only exercises
    branch 1 (atwater==0 too → pass); a partial plan (e.g. protein logged
    against a 0-kcal target) reaches this branch in production.
    """
    # atwater = 4*100 + 4*0 + 9*0 = 400 kcal, but kcal target is 0
    plan = _plan(kcal=0.0, protein_g=100.0, fat_g=0.0, carb_g=0.0)
    result = macro_plan_consistency_eval(plan)
    assert result.score == 0.0
    assert result.label == "fail"
    assert "0" in result.explanation
    assert result.metadata["atwater"] == 400.0
    assert result.metadata["kcal"] == 0.0


# ---------------------------------------------------------------------------
# MACRO_PHOENIX_EVALUATORS
# ---------------------------------------------------------------------------


def test_macro_phoenix_evaluators_list_exists_and_is_callable() -> None:
    """MACRO_PHOENIX_EVALUATORS is a non-empty list of callables."""
    assert isinstance(MACRO_PHOENIX_EVALUATORS, list)
    assert len(MACRO_PHOENIX_EVALUATORS) >= 2
    for fn in MACRO_PHOENIX_EVALUATORS:
        assert callable(fn)


def test_macro_phoenix_evaluators_return_tuple_not_eval_result() -> None:
    """The Phoenix-adapted callables return (score, label, explanation) tuples."""
    plan = _plan(kcal=2633.1, protein_g=197.5, fat_g=87.8, carb_g=263.3)
    expected = _expected_ranges(
        kcal_min=2238.0, kcal_max=3028.0,
        protein_g_min=168.0, protein_g_max=227.0,
        fat_g_min=75.0, fat_g_max=101.0,
        carb_g_min=224.0, carb_g_max=303.0,
    )
    for fn in MACRO_PHOENIX_EVALUATORS:
        result = fn(plan, expected)
        assert isinstance(result, tuple)
        assert len(result) == 3
        score, label, explanation = result
        assert isinstance(score, float)
        assert isinstance(label, str)
        assert isinstance(explanation, str)
