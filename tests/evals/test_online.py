"""Unit tests for src/dietrace/evals/online.py.

``evaluate_log(text, per_item, totals)`` is the online-eval core: a per-log
quality score computed from DETERMINISTIC heuristics only — no LLM, no network.
It judges a *single* logged meal (not a dataset case against ground truth) on
four axes: were all the foods named in the text resolved (none dropped), how
trustworthy the resolution source is, whether the portion grams are plausible,
and whether the totalled calories agree with an Atwater estimate of the macros.

The tests exercise a synthetic high-confidence log (everything consistent) and
several low-confidence logs (a dropped item, a web/unknown source, an absurd
portion, calories that don't match the macros) so each heuristic is pinned, not
just the plumbing. Both dict and pydantic-model item shapes are covered, since
the pipeline hands the web layer dicts but tools return models.
"""

from dietrace.agents.nutrition.log_entry import LoggedItem
from dietrace.evals.online import REVIEW_THRESHOLD, evaluate_log, review_flag
from dietrace.nutrition.models import Nutrient


def _macros(calories, protein, fat, carb):
    """A LoggedMeal-shaped totals list keyed by USDA code."""
    return [
        {"code": "208", "name": "Energy", "amount": calories, "unit": "kcal"},
        {"code": "203", "name": "Protein", "amount": protein, "unit": "g"},
        {"code": "204", "name": "Total lipid (fat)", "amount": fat, "unit": "g"},
        {"code": "205", "name": "Carbohydrate", "amount": carb, "unit": "g"},
    ]


def _item(fdc_id, grams, *, source=None):
    """A per-item dict in the LoggedMeal shape, optional explicit source hint."""
    item = {"fdc_id": fdc_id, "description": "x", "grams": grams, "nutrients": []}
    if source is not None:
        item["source"] = source
    return item


def test_returns_expected_shape() -> None:
    result = evaluate_log("an apple", [_item(1, 150)], _macros(78, 0.4, 0.2, 21))
    assert set(result) == {"confidence", "flags", "reasons"}
    assert isinstance(result["confidence"], float)
    assert 0.0 <= result["confidence"] <= 1.0
    assert isinstance(result["flags"], list)
    assert isinstance(result["reasons"], list)


def test_high_confidence_clean_log() -> None:
    """One food, named once, USDA-sourced, sane grams, calories ≈ Atwater."""
    # Atwater: 0.4*4 + 21*4 + 0.2*9 = 1.6 + 84 + 1.8 = 87.4 ≈ 88 kcal.
    result = evaluate_log("an apple", [_item(1, 150)], _macros(88, 0.4, 0.2, 21))
    assert result["confidence"] >= 0.9
    assert result["flags"] == []


def test_high_confidence_multi_item_log() -> None:
    """Two foods named, two resolved, all consistent → still high confidence."""
    per_item = [_item(1, 100), _item(2, 50)]
    # protein 20, fat 10, carb 30 → Atwater 20*4 + 30*4 + 10*9 = 290.
    result = evaluate_log("eggs and toast", per_item, _macros(290, 20, 10, 30))
    assert result["confidence"] >= 0.9
    assert result["flags"] == []


def test_dropped_item_lowers_confidence_and_flags() -> None:
    """Three foods named, one resolved → a drop is detected and flagged."""
    per_item = [_item(1, 100)]
    result = evaluate_log(
        "eggs, toast and orange juice", per_item, _macros(290, 20, 10, 30)
    )
    assert "dropped_items" in result["flags"]
    assert result["confidence"] < 0.9
    assert any("drop" in r.lower() or "resolv" in r.lower() for r in result["reasons"])


def test_nothing_resolved_is_very_low_confidence() -> None:
    result = evaluate_log("a mystery dish", [], [])
    assert "dropped_items" in result["flags"]
    assert result["confidence"] < 0.5


def test_web_source_lowers_confidence_vs_usda() -> None:
    """An explicit low-quality source hint costs confidence relative to USDA."""
    usda = evaluate_log("a burger", [_item(50, 200, source="usda")], _macros(500, 25, 25, 40))
    web = evaluate_log("a burger", [_item(0, 200, source="web")], _macros(500, 25, 25, 40))
    assert web["confidence"] < usda["confidence"]
    assert "low_source_quality" in web["flags"]


def test_source_inferred_from_fdc_id_when_no_hint() -> None:
    """No explicit hint: fdc_id 0 (synthetic web food) infers a weaker source."""
    result = evaluate_log("a burger", [_item(0, 200)], _macros(500, 25, 25, 40))
    assert "low_source_quality" in result["flags"]
    # A soft source signal still dents an otherwise-perfect log.
    assert result["confidence"] < 1.0


def test_implausible_portion_flags() -> None:
    """Grams far outside the plausible band are flagged."""
    result = evaluate_log("an apple", [_item(1, 9000)], _macros(88, 0.4, 0.2, 21))
    assert "implausible_portion" in result["flags"]
    assert result["confidence"] < 0.9


def test_zero_grams_is_implausible() -> None:
    result = evaluate_log("an apple", [_item(1, 0)], _macros(0, 0, 0, 0))
    assert "implausible_portion" in result["flags"]


def test_calorie_atwater_mismatch_flags() -> None:
    """Totalled calories that disagree with the macros' Atwater estimate flag."""
    # Atwater of (20,10,30) ≈ 290 kcal, but totals claim 900 → mismatch.
    result = evaluate_log("eggs and toast", [_item(1, 100), _item(2, 50)], _macros(900, 20, 10, 30))
    assert "calorie_mismatch" in result["flags"]
    assert result["confidence"] < 0.9


def test_calorie_within_tolerance_does_not_flag() -> None:
    """A small calorie deviation inside tolerance is not a mismatch."""
    # Atwater 290; 300 is within ±15%.
    result = evaluate_log("eggs and toast", [_item(1, 100), _item(2, 50)], _macros(300, 20, 10, 30))
    assert "calorie_mismatch" not in result["flags"]


def test_missing_energy_total_is_not_a_calorie_mismatch() -> None:
    """Totals with macros but no 208 can't be calorie-checked → no false flag."""
    macros_only = [
        {"code": "203", "name": "Protein", "amount": 20, "unit": "g"},
        {"code": "205", "name": "Carbohydrate", "amount": 30, "unit": "g"},
    ]
    result = evaluate_log("eggs and toast", [_item(1, 100), _item(2, 50)], macros_only)
    assert "calorie_mismatch" not in result["flags"]


def test_accepts_pydantic_model_items() -> None:
    """per_item / totals may be pydantic models, not just dicts."""
    item = LoggedItem(fdc_id=1, description="apple", grams=150, nutrients=[])
    totals = [
        Nutrient(code="208", name="Energy", amount=88, unit="kcal"),
        Nutrient(code="203", name="Protein", amount=0.4, unit="g"),
        Nutrient(code="204", name="Total lipid (fat)", amount=0.2, unit="g"),
        Nutrient(code="205", name="Carbohydrate", amount=21, unit="g"),
    ]
    result = evaluate_log("an apple", [item], totals)
    assert result["confidence"] >= 0.9
    assert result["flags"] == []


def test_many_low_confidence_signals_stack() -> None:
    """A log that trips every heuristic lands far below a clean one."""
    # Two foods named, one resolved (drop), web source, absurd grams, calories
    # that don't match the macros.
    per_item = [_item(0, 9000, source="web")]
    result = evaluate_log("eggs and toast", per_item, _macros(2000, 20, 10, 30))
    assert result["confidence"] < 0.5
    assert {
        "dropped_items",
        "low_source_quality",
        "implausible_portion",
        "calorie_mismatch",
    } <= set(result["flags"])


# --- review flag: the low-confidence threshold ---


def test_review_flag_shape() -> None:
    flag = review_flag({"confidence": 0.5, "flags": [], "reasons": ["x"]})
    assert set(flag) == {"needs_review", "review_reason"}


def test_low_confidence_sets_needs_review_with_top_reason() -> None:
    """Below the threshold the flag is set, carrying the eval's first reason."""
    result = {
        "confidence": 0.42,
        "flags": ["low_source_quality"],
        "reasons": ["lower-trust source(s): web", "118 kcal off"],
    }
    flag = review_flag(result)
    assert flag["needs_review"] is True
    assert flag["review_reason"] == "lower-trust source(s): web"


def test_confidence_at_or_above_threshold_does_not_need_review() -> None:
    """A confident log isn't flagged and carries no review reason."""
    assert review_flag({"confidence": 0.92, "flags": [], "reasons": []}) == {
        "needs_review": False,
        "review_reason": None,
    }


def test_threshold_boundary_is_strict_less_than() -> None:
    """Exactly at the threshold is not flagged; just under it is (0.6)."""
    assert review_flag({"confidence": REVIEW_THRESHOLD, "reasons": ["x"]})[
        "needs_review"
    ] is False
    assert review_flag({"confidence": REVIEW_THRESHOLD - 0.001, "reasons": ["x"]})[
        "needs_review"
    ] is True


def test_review_reason_is_none_when_no_reasons() -> None:
    """A low score with nothing to explain flags review but carries no reason."""
    flag = review_flag({"confidence": 0.1, "flags": [], "reasons": []})
    assert flag["needs_review"] is True
    assert flag["review_reason"] is None


def test_review_flag_over_a_real_low_confidence_log() -> None:
    """End-to-end: a mostly-unresolved log evaluates below the threshold."""
    result = evaluate_log("eggs, toast and orange juice", [], [])
    assert result["confidence"] < REVIEW_THRESHOLD
    flag = review_flag(result)
    assert flag["needs_review"] is True
    assert flag["review_reason"]  # a human-readable reason is carried
