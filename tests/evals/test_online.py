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
from dietrace.evals.online import REVIEW_THRESHOLD, evaluate_log, review_flag, sources_of
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
    assert {"confidence", "flags", "reasons", "axes"} <= set(result)
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


def test_absurd_per_item_calories_flagged_even_when_grams_in_band() -> None:
    """A kilogram of almonds (~5800 kcal) is under the gram ceiling but is far more
    calories than one food — caught by the per-item calorie check."""
    item = {
        "fdc_id": 1,
        "description": "almonds",
        "grams": 1000.0,  # within the 1–4000 g band
        "nutrients": [{"code": "208", "name": "Energy", "amount": 5800.0, "unit": "kcal"}],
    }
    result = evaluate_log("10 almonds", [item], _macros(5800, 210, 500, 220))
    assert "implausible_portion" in result["flags"]
    assert result["confidence"] < 0.9


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


def test_severe_single_axis_flags_review_even_when_confidence_is_fine() -> None:
    """A badly-off portion (one axis ≤ 0.5) flags review even though the averaged
    confidence (0.75 here) clears the threshold — the average smooths it over.
    """
    result = {
        "confidence": 0.75,
        "flags": ["implausible_portion"],
        "reasons": ["1 implausible portion(s): 2058 kcal for one item"],
        "axes": [
            {"name": "resolution_completeness", "score": 1.0, "note": "✓ all resolved"},
            {"name": "source_quality", "score": 1.0, "note": "✓ trusted sources"},
            {"name": "portion_sanity", "score": 0.5, "note": "⚠ 2058 kcal for one item"},
            {"name": "calorie_plausibility", "score": 1.0, "note": "✓ Atwater ok"},
        ],
    }
    flag = review_flag(result)
    assert flag["needs_review"] is True
    # The reason points at the failing axis, glyph stripped.
    assert flag["review_reason"] == "2058 kcal for one item"


def test_all_healthy_axes_do_not_flag_review() -> None:
    """All four axes high → not flagged (the severe-axis check stays quiet)."""
    result = {
        "confidence": 1.0,
        "flags": [],
        "reasons": [],
        "axes": [
            {"name": "resolution_completeness", "score": 1.0, "note": "✓ ok"},
            {"name": "source_quality", "score": 1.0, "note": "✓ ok"},
            {"name": "portion_sanity", "score": 1.0, "note": "✓ ok"},
            {"name": "calorie_plausibility", "score": 1.0, "note": "✓ ok"},
        ],
    }
    assert review_flag(result)["needs_review"] is False


def test_review_flag_over_a_real_low_confidence_log() -> None:
    """End-to-end: a mostly-unresolved log evaluates below the threshold."""
    result = evaluate_log("eggs, toast and orange juice", [], [])
    assert result["confidence"] < REVIEW_THRESHOLD
    flag = review_flag(result)
    assert flag["needs_review"] is True
    assert flag["review_reason"]  # a human-readable reason is carried


# --- _calorie_plausibility: zero-atwater + nonzero-energy branch ---
# Pins the untested path where energy is reported but all macro codes (203/204/205)
# are absent, so the Atwater estimate is zero while energy is positive — the
# maximum-penalty case (score = 0.0). A partial totals dict (e.g. from a food
# record with only calorie data) can reach this branch in production.


def test_energy_only_totals_flagged_as_calorie_mismatch() -> None:
    """Totals with energy (208) but no macro codes cannot be Atwater-verified."""
    totals_energy_only = [{"code": "208", "name": "Energy", "amount": 400, "unit": "kcal"}]
    result = evaluate_log("a snack bar", [_item(1, 45)], totals_energy_only)
    assert "calorie_mismatch" in result["flags"]
    assert result["confidence"] < 0.9
    assert any("zero" in r.lower() for r in result["reasons"])


def test_zero_energy_with_zero_macros_is_not_a_mismatch() -> None:
    """Energy = 0 with no macros is consistent (both sides are zero), not flagged."""
    totals_all_zero = [{"code": "208", "name": "Energy", "amount": 0, "unit": "kcal"}]
    result = evaluate_log("water", [_item(1, 240)], totals_all_zero)
    assert "calorie_mismatch" not in result["flags"]


# --- sources_of: the public trust-store accessor ---
# sources_of() is imported and called in app.py (POST /log trust record) but was
# never directly tested; the sub-score tests only exercised it indirectly through
# evaluate_log. These tests pin the public contract so renames or logic changes
# are caught without having to reason about the full evaluate_log call chain.


def test_sources_of_explicit_source_hint() -> None:
    """An explicit source hint is returned verbatim (lowercased)."""
    items = [_item(fdc_id=50, grams=100, source="usda")]
    assert sources_of(items) == ["usda"]


def test_sources_of_infers_web_when_fdc_id_zero() -> None:
    """No hint + fdc_id=0 (synthetic web food) infers 'web'."""
    items = [_item(fdc_id=0, grams=100)]
    assert sources_of(items) == ["web"]


def test_sources_of_infers_usda_when_fdc_id_nonzero() -> None:
    """No hint + real fdc_id infers 'usda' (reproducible USDA record)."""
    items = [_item(fdc_id=170379, grams=100)]
    assert sources_of(items) == ["usda"]


def test_sources_of_mixed_list() -> None:
    """A mixed list preserves per-item order."""
    items = [
        _item(fdc_id=50, grams=100, source="usda"),
        _item(fdc_id=0, grams=80),  # no hint → web
    ]
    assert sources_of(items) == ["usda", "web"]


def test_sources_of_empty_and_none() -> None:
    """Empty list and None both return an empty list without raising."""
    assert sources_of([]) == []
    assert sources_of(None) == []  # type: ignore[arg-type]


# --- _source_of: data_type fallback ---
# The pipeline can hand per_item entries that carry data_type rather than source
# (the search layer uses data_type; the web adapter may omit the source rename).
# The `or _field(item, "data_type")` branch in _source_of() was never exercised.


def test_sources_of_falls_back_to_data_type_when_no_source() -> None:
    """data_type is used when source is absent."""
    item = {"fdc_id": 50, "description": "yogurt", "grams": 200, "data_type": "branded"}
    assert sources_of([item]) == ["branded"]


def test_sources_of_source_takes_precedence_over_data_type() -> None:
    """Explicit source wins when both source and data_type are present."""
    item = {
        "fdc_id": 50,
        "description": "yogurt",
        "grams": 200,
        "source": "usda",
        "data_type": "branded",
    }
    assert sources_of([item]) == ["usda"]


# --- _item_energy: null guards ---
# Two defensive `or` guards in _item_energy() protect against None flowing in
# from malformed pipeline output. Exercises the nutrients=None and amount=None
# branches (`_field(...) or []` and `_field(...) or 0.0` respectively).


def test_evaluate_log_with_nutrients_none_does_not_raise() -> None:
    """An item whose nutrients field is explicitly None doesn't crash the eval."""
    item = {"fdc_id": 1, "description": "mystery", "grams": 100, "nutrients": None}
    result = evaluate_log("mystery", [item], [])
    assert isinstance(result["confidence"], float)


def test_evaluate_log_with_nutrient_amount_none_does_not_raise() -> None:
    """A nutrient with amount=None is treated as zero, not a crash."""
    item = {
        "fdc_id": 1,
        "description": "snack",
        "grams": 50,
        "nutrients": [{"code": "208", "name": "Energy", "amount": None, "unit": "kcal"}],
    }
    result = evaluate_log("a snack", [item], [])
    assert isinstance(result["confidence"], float)


# ──  all four confidence axes ──────────────────────────────────────


def test_all_four_axes_present() -> None:
    """evaluate_log always returns all 4 confidence axes, each with name/score/note."""
    result = evaluate_log("an apple", [_item(1, 150)], _macros(88, 0.4, 0.2, 21))
    axes = result["axes"]
    assert len(axes) == 4
    names = {a["name"] for a in axes}
    assert names == {
        "resolution_completeness",
        "source_quality",
        "portion_sanity",
        "calorie_plausibility",
    }
    for axis in axes:
        assert isinstance(axis["score"], float), f"{axis['name']} score not float"
        assert isinstance(axis["note"], str) and axis["note"], f"{axis['name']} note empty"


def test_passing_axes_have_check_note() -> None:
    """A clean log's axes all carry ✓ notes."""
    result = evaluate_log("an apple", [_item(1, 150)], _macros(88, 0.4, 0.2, 21))
    for axis in result["axes"]:
        assert axis["note"].startswith("✓"), f"{axis['name']}: {axis['note']!r}"


def test_failing_axis_has_warn_note() -> None:
    """A failing axis (e.g. dropped item) carries a ⚠ note."""
    per_item = [_item(1, 100)]
    result = evaluate_log(
        "eggs, toast and orange juice", per_item, _macros(290, 20, 10, 30)
    )
    rc = next(a for a in result["axes"] if a["name"] == "resolution_completeness")
    assert rc["note"].startswith("⚠"), f"Expected ⚠, got {rc['note']!r}"
    assert rc["score"] < 1.0


def test_all_axes_present_even_when_items_empty() -> None:
    """All 4 axes are always returned, even when per_item is empty."""
    result = evaluate_log("nothing to eat", [], [])
    assert len(result["axes"]) == 4
    names = {a["name"] for a in result["axes"]}
    assert names == {
        "resolution_completeness",
        "source_quality",
        "portion_sanity",
        "calorie_plausibility",
    }
