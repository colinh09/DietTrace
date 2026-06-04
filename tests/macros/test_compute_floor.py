"""Calorie floor on compute_targets (review fix #3).

An aggressive cut on a small/light person must never drop below the sex-aware
safe-minimum floor, and a floored plan must stay Atwater-consistent.
"""

from __future__ import annotations

from dietrace.macros.compute import compute_targets
from dietrace.macros.models import MacroProfile


def _plan(**over: object):
    base: dict[str, object] = dict(
        age=30,
        sex="male",
        height_cm=178.0,
        weight_kg=76.0,
        activity="moderate",
        goal="maintain",
    )
    base.update(over)
    return compute_targets(MacroProfile(**base))


def test_small_female_cut_hits_1200_floor() -> None:
    # TDEE ~1337, cut -500 ~837 → floored to 1200.
    plan = _plan(sex="female", age=35, height_cm=160.0, weight_kg=45.0,
                 activity="sedentary", goal="cut")
    assert plan.targets["208"] == 1200.0
    assert "calorie_floor" in plan.clamped


def test_small_male_cut_hits_1500_floor() -> None:
    plan = _plan(sex="male", age=60, height_cm=165.0, weight_kg=55.0,
                 activity="sedentary", goal="cut")
    assert plan.targets["208"] == 1500.0
    assert "calorie_floor" in plan.clamped


def test_normal_profile_not_floored() -> None:
    plan = _plan(goal="maintain")
    assert plan.clamped == []
    assert plan.targets["208"] > 1500.0


def test_floored_plan_stays_atwater_consistent() -> None:
    plan = _plan(sex="female", age=35, height_cm=160.0, weight_kg=45.0,
                 activity="sedentary", goal="cut")
    t = plan.targets
    atwater = 4 * t["203"] + 4 * t["205"] + 9 * t["204"]
    assert abs(atwater - t["208"]) <= 5.0
