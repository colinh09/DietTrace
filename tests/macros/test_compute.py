"""Unit tests for Mifflin–St Jeor BMR/TDEE computation."""

from __future__ import annotations

import pytest

from dietrace.macros.compute import compute_targets
from dietrace.macros.models import MacroProfile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ACTIVITY_MULTS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}

_GOAL_DELTAS = {
    "cut": -500.0,
    "maintain": 0.0,
    "bulk": 300.0,
}


def _profile(**overrides) -> MacroProfile:
    defaults = dict(
        age=30,
        sex="male",
        height_cm=175.0,
        weight_kg=80.0,
        activity="sedentary",
        goal="maintain",
    )
    defaults.update(overrides)
    return MacroProfile(**defaults)


def _step(plan, name: str) -> dict:
    return next(s for s in plan.steps if s["step"] == name)


# ---------------------------------------------------------------------------
# BMR — known Mifflin–St Jeor values
# ---------------------------------------------------------------------------


class TestBMR:
    def test_male_known_value(self):
        # 10*80 + 6.25*175 - 5*30 + 5 = 800 + 1093.75 - 150 + 5 = 1748.75
        plan = compute_targets(_profile(sex="male", age=30, height_cm=175.0, weight_kg=80.0))
        bmr = _step(plan, "bmr")
        assert abs(bmr["value"] - 1748.75) < 0.01

    def test_female_known_value(self):
        # 10*60 + 6.25*165 - 5*25 - 161 = 600 + 1031.25 - 125 - 161 = 1345.25
        plan = compute_targets(_profile(sex="female", age=25, height_cm=165.0, weight_kg=60.0))
        bmr = _step(plan, "bmr")
        assert abs(bmr["value"] - 1345.25) < 0.01

    def test_male_intercept_differs_from_female(self):
        base = dict(age=30, height_cm=170.0, weight_kg=70.0, activity="sedentary", goal="maintain")
        male_plan = compute_targets(MacroProfile(sex="male", **base))
        female_plan = compute_targets(MacroProfile(sex="female", **base))
        male_bmr = _step(male_plan, "bmr")["value"]
        female_bmr = _step(female_plan, "bmr")["value"]
        # Male intercept +5 vs female -161 → difference = 166
        assert abs(male_bmr - female_bmr - 166.0) < 0.01


# ---------------------------------------------------------------------------
# TDEE — each activity tier
# ---------------------------------------------------------------------------


class TestTDEE:
    @pytest.mark.parametrize(
        "activity,expected_mult",
        [
            ("sedentary", 1.2),
            ("light", 1.375),
            ("moderate", 1.55),
            ("active", 1.725),
            ("very_active", 1.9),
        ],
    )
    def test_multiplier_per_tier(self, activity: str, expected_mult: float):
        plan = compute_targets(_profile(activity=activity))
        bmr_val = _step(plan, "bmr")["value"]
        tdee_val = _step(plan, "tdee")["value"]
        assert abs(tdee_val / bmr_val - expected_mult) < 0.001

    def test_tdee_step_records_activity(self):
        plan = compute_targets(_profile(activity="moderate"))
        assert _step(plan, "tdee")["activity"] == "moderate"


# ---------------------------------------------------------------------------
# Goal adjust — each goal
# ---------------------------------------------------------------------------


class TestGoalAdjust:
    def test_cut_minus_500(self):
        plan = compute_targets(_profile(goal="cut"))
        tdee_val = _step(plan, "tdee")["value"]
        adj = _step(plan, "adjust")
        assert abs(adj["value"] - (tdee_val - 500.0)) < 0.2
        assert adj["goal"] == "cut"

    def test_maintain_zero_delta(self):
        plan = compute_targets(_profile(goal="maintain"))
        tdee_val = _step(plan, "tdee")["value"]
        adj = _step(plan, "adjust")
        assert abs(adj["value"] - tdee_val) < 0.01
        assert adj["delta"] == 0.0

    def test_bulk_plus_300(self):
        plan = compute_targets(_profile(goal="bulk"))
        tdee_val = _step(plan, "tdee")["value"]
        adj = _step(plan, "adjust")
        assert abs(adj["value"] - (tdee_val + 300.0)) < 0.2
        assert adj["goal"] == "bulk"

    def test_kcal_target_stored_in_targets(self):
        plan = compute_targets(_profile(goal="cut"))
        adj_val = _step(plan, "adjust")["value"]
        assert abs(plan.targets["208"] - adj_val) < 0.2


# ---------------------------------------------------------------------------
# Atwater reconciliation — 4·P + 4·C + 9·F ≈ kcal target
# ---------------------------------------------------------------------------


class TestAtwater:
    @pytest.mark.parametrize("goal", ["cut", "maintain", "bulk"])
    def test_reconciles_within_tolerance(self, goal: str):
        plan = compute_targets(_profile(goal=goal))
        p = plan.targets["203"]
        c = plan.targets["205"]
        f = plan.targets["204"]
        kcal = plan.targets["208"]
        atwater = 4.0 * p + 4.0 * c + 9.0 * f
        assert abs(atwater - kcal) <= 5.0, (
            f"Atwater {atwater:.2f} kcal vs target {kcal:.2f} kcal for goal={goal!r}"
        )

    def test_reconciles_female_moderate_cut(self):
        plan = compute_targets(
            MacroProfile(
                age=28, sex="female", height_cm=163.0, weight_kg=58.0,
                activity="moderate", goal="cut",
            )
        )
        p = plan.targets["203"]
        c = plan.targets["205"]
        f = plan.targets["204"]
        kcal = plan.targets["208"]
        assert abs(4.0 * p + 4.0 * c + 9.0 * f - kcal) <= 5.0


# ---------------------------------------------------------------------------
# Plan shape / metadata
# ---------------------------------------------------------------------------


class TestPlanShape:
    def test_all_four_usda_codes_present(self):
        plan = compute_targets(_profile())
        for code in ("208", "203", "205", "204"):
            assert code in plan.targets, f"USDA code {code} missing from targets"

    def test_source_is_formula(self):
        plan = compute_targets(_profile())
        assert plan.source == "formula"

    def test_clamped_is_empty(self):
        plan = compute_targets(_profile())
        assert plan.clamped == []

    def test_steps_ordered_bmr_tdee_adjust_split(self):
        plan = compute_targets(_profile())
        step_names = [s["step"] for s in plan.steps]
        assert step_names == ["bmr", "tdee", "adjust", "split"]

    def test_rationale_non_empty(self):
        plan = compute_targets(_profile())
        assert plan.rationale.strip()

    def test_targets_all_positive(self):
        plan = compute_targets(_profile())
        for code, val in plan.targets.items():
            assert val > 0, f"targets[{code!r}] = {val} is not positive"

    def test_ai_help_ignored_by_pure_formula(self):
        base = _profile(goal="maintain")
        with_ai = compute_targets(MacroProfile(**{**base.model_dump(), "ai_help": True}))
        without_ai = compute_targets(MacroProfile(**{**base.model_dump(), "ai_help": False}))
        assert with_ai.targets == without_ai.targets
        assert with_ai.source == "formula"
