"""Tests for micronutrient carry-through and /analysis micro aggregation.

Three assertions from the done criterion:
1. Micros are carried additively: log_entry passes micro nutrients through scaled
   and summed, code by code, without touching macro codes.
2. HARD guard: macro totals (208/203/204/205) are byte-for-byte identical when a
   food's nutrient panel has micros added to it — additive means non-interfering.
3. /analysis returns a ``micros`` section with consumed-vs-RDA for the tracked
   micro codes, correct amounts from the day's logged meals.
"""

import pytest
from fastapi.testclient import TestClient

from dietrace.agents.nutrition.log_entry import MealItem, log_entry
from dietrace.nutrition.models import ConversionFactors, Food, Nutrient
from dietrace.web.app import create_app
from dietrace.web.feedback import FeedbackStore
from dietrace.web.memory import SqliteMemory
from dietrace.web.micros import MICRO_CODES, micro_progress
from dietrace.web.store import MealLogStore
from dietrace.web.trust import TrustStore

# USDA codes: macros
_ENERGY, _PROTEIN, _FAT, _CARB = "208", "203", "204", "205"
# Spot-checked micro codes that must appear in MICRO_CODES
_FIBER, _SODIUM, _VIT_C, _IRON = "291", "307", "401", "303"


def _food_macros_only() -> Food:
    """An egg carrying only the four macro codes."""
    return Food(
        fdc_id=748967,
        description="Egg, whole, raw, fresh",
        data_type="sr_legacy_food",
        nutrients=[
            Nutrient(code=_ENERGY, name="Energy", amount=143.0, unit="kcal"),
            Nutrient(code=_PROTEIN, name="Protein", amount=12.6, unit="g"),
            Nutrient(code=_FAT, name="Total lipid (fat)", amount=9.51, unit="g"),
            Nutrient(code=_CARB, name="Carbohydrate, by difference", amount=0.72, unit="g"),
        ],
        conversion_factors=ConversionFactors(protein=4.36, fat=9.02, carbohydrate=3.68),
    )


def _food_with_micros() -> Food:
    """Same egg, same macro amounts, with micro nutrients added to the panel."""
    return Food(
        fdc_id=748967,
        description="Egg, whole, raw, fresh",
        data_type="sr_legacy_food",
        nutrients=[
            Nutrient(code=_ENERGY, name="Energy", amount=143.0, unit="kcal"),
            Nutrient(code=_PROTEIN, name="Protein", amount=12.6, unit="g"),
            Nutrient(code=_FAT, name="Total lipid (fat)", amount=9.51, unit="g"),
            Nutrient(code=_CARB, name="Carbohydrate, by difference", amount=0.72, unit="g"),
            # Micros — USDA-grounded per-100 g values for eggs
            Nutrient(code=_FIBER, name="Fiber, total dietary", amount=0.0, unit="g"),
            Nutrient(code=_SODIUM, name="Sodium, Na", amount=142.0, unit="mg"),
            Nutrient(code=_VIT_C, name="Vitamin C, total ascorbic acid", amount=0.0, unit="mg"),
            Nutrient(code=_IRON, name="Iron, Fe", amount=1.75, unit="mg"),
        ],
        conversion_factors=ConversionFactors(protein=4.36, fat=9.02, carbohydrate=3.68),
    )


# ---------------------------------------------------------------------------
# 1. Micros carried additively
# ---------------------------------------------------------------------------


def test_micros_carried_additively() -> None:
    """Micro nutrients are scaled and summed alongside macros — additive, no interference."""
    meal = log_entry([MealItem(food=_food_with_micros(), grams=100.0)])

    # Macros still present
    assert meal.total(_ENERGY) is not None
    assert meal.total(_PROTEIN) is not None
    # Micros present in totals
    assert meal.total(_SODIUM) is not None
    assert meal.total(_SODIUM).amount == pytest.approx(142.0)
    assert meal.total(_IRON) is not None
    assert meal.total(_IRON).amount == pytest.approx(1.75)


def test_micros_scale_with_grams() -> None:
    """Micro amounts scale proportionally to grams, just like macros."""
    meal = log_entry([MealItem(food=_food_with_micros(), grams=50.0)])
    # 50 g = half portion → sodium should be 142 * 0.5 = 71
    assert meal.total(_SODIUM).amount == pytest.approx(71.0)


def test_micros_sum_across_two_items() -> None:
    """Micro totals accumulate code-by-code across multiple food items."""
    meal = log_entry([
        MealItem(food=_food_with_micros(), grams=100.0),
        MealItem(food=_food_with_micros(), grams=100.0),
    ])
    assert meal.total(_SODIUM).amount == pytest.approx(284.0)  # 142 * 2
    assert meal.total(_IRON).amount == pytest.approx(3.50)  # 1.75 * 2


# ---------------------------------------------------------------------------
# 2. HARD guard: macro totals identical before/after adding micros
# ---------------------------------------------------------------------------


def test_macro_totals_identical_before_after_micros() -> None:
    """HARD guard: adding micros to a food's panel leaves macro totals byte-for-byte identical."""
    grams = 100.0
    meal_base = log_entry([MealItem(food=_food_macros_only(), grams=grams)])
    meal_with = log_entry([MealItem(food=_food_with_micros(), grams=grams)])

    for code in (_ENERGY, _PROTEIN, _FAT, _CARB):
        base_nut = meal_base.total(code)
        with_nut = meal_with.total(code)
        assert base_nut is not None
        assert with_nut is not None
        assert base_nut.amount == with_nut.amount, f"macro amount differs for code {code!r}"
        assert base_nut.unit == with_nut.unit, f"macro unit differs for code {code!r}"
        assert base_nut.name == with_nut.name, f"macro name differs for code {code!r}"


def test_macro_totals_identical_two_item_meal() -> None:
    """HARD guard holds for a multi-item meal too."""
    avocado_base = Food(
        fdc_id=171705,
        description="Avocados, raw",
        data_type="sr_legacy_food",
        nutrients=[
            Nutrient(code=_ENERGY, name="Energy", amount=160.0, unit="kcal"),
            Nutrient(code=_PROTEIN, name="Protein", amount=2.0, unit="g"),
            Nutrient(code=_FAT, name="Total lipid (fat)", amount=14.66, unit="g"),
            Nutrient(code=_CARB, name="Carbohydrate, by difference", amount=8.53, unit="g"),
        ],
    )
    avocado_with = Food(
        fdc_id=171705,
        description="Avocados, raw",
        data_type="sr_legacy_food",
        nutrients=[
            Nutrient(code=_ENERGY, name="Energy", amount=160.0, unit="kcal"),
            Nutrient(code=_PROTEIN, name="Protein", amount=2.0, unit="g"),
            Nutrient(code=_FAT, name="Total lipid (fat)", amount=14.66, unit="g"),
            Nutrient(code=_CARB, name="Carbohydrate, by difference", amount=8.53, unit="g"),
            Nutrient(code=_SODIUM, name="Sodium, Na", amount=7.0, unit="mg"),
            Nutrient(code="306", name="Potassium, K", amount=485.0, unit="mg"),
        ],
    )

    meal_base = log_entry([
        MealItem(food=_food_macros_only(), grams=100.0),
        MealItem(food=avocado_base, grams=50.0),
    ])
    meal_with = log_entry([
        MealItem(food=_food_with_micros(), grams=100.0),
        MealItem(food=avocado_with, grams=50.0),
    ])

    for code in (_ENERGY, _PROTEIN, _FAT, _CARB):
        assert meal_base.total(code).amount == pytest.approx(meal_with.total(code).amount), (
            f"multi-item macro total differs for code {code!r}"
        )


# ---------------------------------------------------------------------------
# 3. micro_progress() unit tests
# ---------------------------------------------------------------------------


def test_micro_progress_returns_consumed_and_rda() -> None:
    """micro_progress maps daily totals to consumed + rda + pct_dv for tracked codes."""
    totals = [
        {"code": _SODIUM, "name": "Sodium, Na", "amount": 1150.0, "unit": "mg"},
        {"code": _FIBER, "name": "Fiber, total dietary", "amount": 14.0, "unit": "g"},
        # A macro code must NOT appear in the output
        {"code": _ENERGY, "name": "Energy", "amount": 500.0, "unit": "kcal"},
    ]
    result = micro_progress(totals)

    codes_out = {r["code"] for r in result}
    assert _ENERGY not in codes_out, "macro code 208 must not appear in micro_progress output"
    assert _SODIUM in codes_out
    assert _FIBER in codes_out

    sodium = next(r for r in result if r["code"] == _SODIUM)
    assert sodium["consumed"] == pytest.approx(1150.0)
    assert sodium["rda"] > 0
    assert sodium["pct_dv"] == pytest.approx(1150.0 / sodium["rda"] * 100, rel=1e-3)

    fiber = next(r for r in result if r["code"] == _FIBER)
    assert fiber["consumed"] == pytest.approx(14.0)
    assert fiber["rda"] > 0


def test_micro_progress_zero_for_unlogged_codes() -> None:
    """micro_progress includes all tracked codes even when absent from daily totals."""
    result = micro_progress([])  # nothing logged today

    for entry in result:
        assert entry["consumed"] == 0.0


def test_micro_progress_excludes_untracked_codes() -> None:
    """Codes not in MICRO_CODES are silently dropped."""
    totals = [{"code": "999", "name": "Unknown nutrient", "amount": 99.0, "unit": "g"}]
    result = micro_progress(totals)
    assert all(r["code"] != "999" for r in result)


def test_micro_codes_set_contains_expected_codes() -> None:
    """MICRO_CODES includes the tracked nutrient codes (spot check)."""
    for code in (_FIBER, _SODIUM, _VIT_C, _IRON):
        assert code in MICRO_CODES, f"{code!r} missing from MICRO_CODES"


def test_micro_progress_non_finite_amount_treated_as_zero() -> None:
    """A non-finite total amount (NaN/±inf) reads as nothing consumed, not NaN/inf.

    pydantic admits non-finite floats and a garbled tool-call / corrupted total can
    supply one; left unguarded it flows through to ``consumed`` and ``pct_dv``,
    where it both surfaces in the UI and serializes as the invalid-JSON token
    ``NaN``/``Infinity`` from ``/analysis``. Mirrors the isfinite guard in
    check_against_goals / estimate_portion / parse_meal.
    """
    import json
    import math

    totals = [
        {"code": _SODIUM, "name": "Sodium, Na", "amount": float("nan"), "unit": "mg"},
        {"code": _FIBER, "name": "Fiber, total dietary", "amount": float("inf"), "unit": "g"},
        {"code": _IRON, "name": "Iron, Fe", "amount": float("-inf"), "unit": "mg"},
    ]
    result = micro_progress(totals)

    for code in (_SODIUM, _FIBER, _IRON):
        entry = next(r for r in result if r["code"] == code)
        assert entry["consumed"] == 0.0, f"non-finite {code!r} must read as 0.0 consumed"
        assert entry["pct_dv"] == 0.0
        assert math.isfinite(entry["consumed"])
        assert math.isfinite(entry["pct_dv"])

    # The whole panel must stay strict-JSON serializable (no NaN/Infinity tokens).
    json.dumps(result, allow_nan=False)


def test_micro_progress_skips_total_without_code() -> None:
    """A total missing its ``code`` key is skipped, not a crash.

    ``micro_progress`` already coerces a junk/non-finite ``amount`` defensively via
    ``t.get("amount")``, but it read ``t["code"]`` directly — so one partial or
    malformed total (a code-less dict from a garbled tool-call or a corrupted
    aggregate) raised ``KeyError`` and took down the entire ``/analysis`` micro
    panel. The rest of the pipeline reads the code defensively (online
    ``_totals_by_code`` / memory ``calories_of`` use ``.get("code")``); this aligns
    micros with that, dropping the code-less entry while the valid totals still land.
    """
    totals = [
        {"name": "mystery", "amount": 5.0, "unit": "g"},  # no "code" — must be skipped
        {"code": _SODIUM, "name": "Sodium, Na", "amount": 1150.0, "unit": "mg"},
    ]
    result = micro_progress(totals)  # must not raise

    # The full tracked set is still returned and the valid total still lands.
    assert {r["code"] for r in result} == set(MICRO_CODES)
    sodium = next(r for r in result if r["code"] == _SODIUM)
    assert sodium["consumed"] == pytest.approx(1150.0)


# ---------------------------------------------------------------------------
# 4. /analysis micro aggregation + RDA comparison
# ---------------------------------------------------------------------------


def _analysis_client(tmp_path, meal_totals):
    """A test client whose logger returns *meal_totals* on every POST /log."""
    def logger(text, examples=()):
        return {"totals": meal_totals, "per_item": [{"description": text, "grams": 100.0}]}

    store = MealLogStore(tmp_path / "log.sqlite")
    app = create_app(
        meal_logger=logger,
        store=store,
        feedback_store=FeedbackStore(tmp_path / "feedback.sqlite"),
        trust_store=TrustStore(tmp_path / "trust.sqlite"),
        memory=SqliteMemory(tmp_path / "memory.sqlite"),
        tracer_init=lambda name: None,
    )
    return TestClient(app)


def test_analysis_micro_aggregation_and_rda(tmp_path) -> None:
    """/analysis includes a micros section with consumed-vs-RDA for the day's meals."""
    meal_totals = [
        {"code": "208", "name": "Energy", "amount": 500.0, "unit": "kcal"},
        {"code": "203", "name": "Protein", "amount": 30.0, "unit": "g"},
        {"code": "204", "name": "Total lipid (fat)", "amount": 20.0, "unit": "g"},
        {"code": "205", "name": "Carbohydrate, by difference", "amount": 60.0, "unit": "g"},
        {"code": _SODIUM, "name": "Sodium, Na", "amount": 800.0, "unit": "mg"},
        {"code": _FIBER, "name": "Fiber, total dietary", "amount": 8.0, "unit": "g"},
        {"code": _IRON, "name": "Iron, Fe", "amount": 5.0, "unit": "mg"},
    ]
    client = _analysis_client(tmp_path, meal_totals)
    client.post("/log", json={"text": "test meal"})

    response = client.get("/analysis")
    assert response.status_code == 200
    body = response.json()

    assert "micros" in body, "/analysis response must include a 'micros' section"
    micros = body["micros"]
    assert isinstance(micros, list)
    assert len(micros) > 0

    micro_codes = {m["code"] for m in micros}
    assert _SODIUM in micro_codes
    assert _FIBER in micro_codes
    assert _IRON in micro_codes
    # Macro codes must not leak into the micros section
    assert "208" not in micro_codes, "macro code 208 must not appear in micros section"
    assert "203" not in micro_codes

    sodium = next(m for m in micros if m["code"] == _SODIUM)
    assert sodium["consumed"] == pytest.approx(800.0)
    assert "rda" in sodium and sodium["rda"] > 0
    assert "pct_dv" in sodium
    assert sodium["pct_dv"] == pytest.approx(800.0 / sodium["rda"] * 100, rel=1e-3)

    fiber = next(m for m in micros if m["code"] == _FIBER)
    assert fiber["consumed"] == pytest.approx(8.0)


def test_analysis_macro_goals_unchanged_by_micros(tmp_path) -> None:
    """HARD guard at the API level: adding micros to totals does not change macro goals progress."""
    macro_totals = [
        {"code": "208", "name": "Energy", "amount": 600.0, "unit": "kcal"},
        {"code": "203", "name": "Protein", "amount": 40.0, "unit": "g"},
        {"code": "204", "name": "Total lipid (fat)", "amount": 25.0, "unit": "g"},
        {"code": "205", "name": "Carbohydrate, by difference", "amount": 70.0, "unit": "g"},
    ]
    macro_and_micro_totals = macro_totals + [
        {"code": _SODIUM, "name": "Sodium, Na", "amount": 1200.0, "unit": "mg"},
        {"code": _FIBER, "name": "Fiber, total dietary", "amount": 12.0, "unit": "g"},
    ]

    client_base = _analysis_client(tmp_path / "base", macro_totals)
    client_base.post("/log", json={"text": "base meal"})
    base_goals = client_base.get("/analysis").json()["goals"]

    client_with = _analysis_client(tmp_path / "with", macro_and_micro_totals)
    client_with.post("/log", json={"text": "with meal"})
    with_goals = client_with.get("/analysis").json()["goals"]

    for base_g, with_g in zip(base_goals, with_goals, strict=True):
        assert base_g["code"] == with_g["code"]
        assert base_g["consumed"] == pytest.approx(with_g["consumed"]), (
            f"macro goals consumed differs for code {base_g['code']!r}"
        )
        assert base_g["remaining"] == pytest.approx(with_g["remaining"])
