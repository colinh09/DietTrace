"""Unit tests for deterministic macro presets."""

from __future__ import annotations

import pytest

from dietrace.macros.presets import preset_plan

_USDA_CODES = ("208", "203", "205", "204")
_ATWATER_TOLERANCE = 5.0  # kcal; matches the compute.py test threshold


def _atwater(plan) -> float:
    t = plan.targets
    return 4.0 * t["203"] + 4.0 * t["205"] + 9.0 * t["204"]


# ---------------------------------------------------------------------------
# Calorie ballpark — each preset lands in the expected range
# ---------------------------------------------------------------------------


class TestCalorieBallpark:
    def test_cut_near_1800(self):
        plan = preset_plan("cut")
        assert abs(plan.targets["208"] - 1800) <= 50

    def test_maintain_near_2200(self):
        plan = preset_plan("maintain")
        assert abs(plan.targets["208"] - 2200) <= 50

    def test_bulk_near_2600(self):
        plan = preset_plan("bulk")
        assert abs(plan.targets["208"] - 2600) <= 50


# ---------------------------------------------------------------------------
# Atwater reconciliation — 4·P + 4·C + 9·F ≈ kcal target
# ---------------------------------------------------------------------------


class TestAtwater:
    @pytest.mark.parametrize("key", ["cut", "maintain", "bulk"])
    def test_reconciles_within_tolerance(self, key: str):
        plan = preset_plan(key)
        kcal = plan.targets["208"]
        atwater = _atwater(plan)
        assert abs(atwater - kcal) <= _ATWATER_TOLERANCE, (
            f"Atwater {atwater:.2f} kcal vs target {kcal:.2f} kcal for preset={key!r}"
        )


# ---------------------------------------------------------------------------
# Plan shape — all four USDA codes, source, clamped, steps
# ---------------------------------------------------------------------------


class TestPlanShape:
    @pytest.mark.parametrize("key", ["cut", "maintain", "bulk"])
    def test_all_four_usda_codes_present(self, key: str):
        plan = preset_plan(key)
        for code in _USDA_CODES:
            assert code in plan.targets, f"USDA code {code} missing for preset={key!r}"

    @pytest.mark.parametrize("key", ["cut", "maintain", "bulk"])
    def test_source_is_preset(self, key: str):
        plan = preset_plan(key)
        assert plan.source == "preset"

    @pytest.mark.parametrize("key", ["cut", "maintain", "bulk"])
    def test_clamped_is_empty(self, key: str):
        plan = preset_plan(key)
        assert plan.clamped == []

    @pytest.mark.parametrize("key", ["cut", "maintain", "bulk"])
    def test_all_targets_positive(self, key: str):
        plan = preset_plan(key)
        for code, val in plan.targets.items():
            assert val > 0, f"targets[{code!r}] = {val} not positive for preset={key!r}"

    @pytest.mark.parametrize("key", ["cut", "maintain", "bulk"])
    def test_rationale_non_empty(self, key: str):
        plan = preset_plan(key)
        assert plan.rationale.strip()


# ---------------------------------------------------------------------------
# Invalid key
# ---------------------------------------------------------------------------


class TestInvalidKey:
    def test_unknown_key_raises(self):
        with pytest.raises(KeyError):
            preset_plan("unknown")
