"""Unit tests for Gemini-personalised macro planning with safety bounds."""

from __future__ import annotations

from unittest.mock import MagicMock

from dietrace.macros.models import MacroProfile
from dietrace.macros.personalize import personalize_plan

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


def _base_targets(
    kcal: float = 2000.0,
    protein_pct: float = 0.30,
    carb_pct: float = 0.40,
    fat_pct: float = 0.30,
) -> dict[str, float]:
    """Build consistent base targets from percentage splits."""
    return {
        "208": kcal,
        "203": round(kcal * protein_pct / 4.0, 1),
        "205": round(kcal * carb_pct / 4.0, 1),
        "204": round(kcal * fat_pct / 9.0, 1),
    }


def _mock_client(
    rationale: str = "test rationale",
    protein_pct_delta: float = 0.0,
    fat_pct_delta: float = 0.0,
) -> MagicMock:
    response = MagicMock()
    response.text = (
        f'{{"rationale": "{rationale}", '
        f'"protein_pct_delta": {protein_pct_delta}, '
        f'"fat_pct_delta": {fat_pct_delta}}}'
    )
    client = MagicMock()
    client.models.generate_content.return_value = response
    return client


# ---------------------------------------------------------------------------
# In-range applied
# ---------------------------------------------------------------------------


class TestInRangeApplied:
    def test_protein_delta_increases_protein(self):
        profile = _profile(weight_kg=80.0)
        base = _base_targets(kcal=2000.0)
        # +2% protein: 30% → 32% → 160g
        client = _mock_client(protein_pct_delta=2.0, fat_pct_delta=0.0)
        plan = personalize_plan(profile, base, client)
        assert abs(plan.targets["203"] - 160.0) < 2.0

    def test_fat_delta_increases_fat(self):
        profile = _profile(weight_kg=80.0)
        base = _base_targets(kcal=2000.0)
        # +2% fat: 30% → 32% → ~71.1g
        client = _mock_client(protein_pct_delta=0.0, fat_pct_delta=2.0)
        plan = personalize_plan(profile, base, client)
        expected_fat = 2000.0 * 0.32 / 9.0
        assert abs(plan.targets["204"] - expected_fat) < 2.0

    def test_kcal_unchanged(self):
        profile = _profile()
        base = _base_targets(kcal=2000.0)
        client = _mock_client(protein_pct_delta=3.0, fat_pct_delta=-2.0)
        plan = personalize_plan(profile, base, client)
        assert plan.targets["208"] == 2000.0

    def test_atwater_holds(self):
        profile = _profile()
        base = _base_targets(kcal=2000.0)
        client = _mock_client(protein_pct_delta=2.0, fat_pct_delta=1.0)
        plan = personalize_plan(profile, base, client)
        p = plan.targets["203"]
        c = plan.targets["205"]
        f = plan.targets["204"]
        assert abs(4.0 * p + 4.0 * c + 9.0 * f - 2000.0) <= 5.0

    def test_source_is_ai(self):
        plan = personalize_plan(_profile(), _base_targets(), _mock_client())
        assert plan.source == "ai"

    def test_rationale_from_gemini(self):
        client = _mock_client(rationale="Increased protein for muscle retention.")
        plan = personalize_plan(_profile(), _base_targets(), client)
        assert "Increased protein" in plan.rationale

    def test_no_protein_or_fat_in_clamped_for_in_range(self):
        # weight_kg=80 → protein [96, 192], fat [33.3, 88.9] at 2000 kcal
        # +2% protein → 160g, +1% fat → ~68.9g — both in bounds
        profile = _profile(weight_kg=80.0)
        base = _base_targets(kcal=2000.0)
        client = _mock_client(protein_pct_delta=2.0, fat_pct_delta=1.0)
        plan = personalize_plan(profile, base, client)
        assert "protein" not in plan.clamped
        assert "fat" not in plan.clamped


# ---------------------------------------------------------------------------
# Out-of-range clamped (recorded)
# ---------------------------------------------------------------------------


class TestOutOfRangeClamped:
    def test_protein_above_max_clamped(self):
        # weight_kg=70 → protein_max=168g; +8% → 190g > 168g → clamp
        profile = _profile(weight_kg=70.0)
        base = _base_targets(kcal=2000.0)
        client = _mock_client(protein_pct_delta=8.0, fat_pct_delta=0.0)
        plan = personalize_plan(profile, base, client)
        protein_max = 70.0 * 2.4
        assert plan.targets["203"] <= protein_max + 0.5
        assert "protein" in plan.clamped

    def test_protein_below_min_clamped(self):
        # weight_kg=90 → protein_min=108g; -10% → 100g < 108g → clamp
        profile = _profile(weight_kg=90.0)
        base = _base_targets(kcal=2000.0)
        client = _mock_client(protein_pct_delta=-10.0, fat_pct_delta=0.0)
        plan = personalize_plan(profile, base, client)
        protein_min = 90.0 * 1.2
        assert plan.targets["203"] >= protein_min - 0.5
        assert "protein" in plan.clamped

    def test_fat_above_max_clamped(self):
        # base fat_pct=35%, +10% → 45% → 100g > fat_max 88.9g → clamp
        profile = _profile()
        base = _base_targets(kcal=2000.0, protein_pct=0.30, carb_pct=0.35, fat_pct=0.35)
        client = _mock_client(protein_pct_delta=0.0, fat_pct_delta=10.0)
        plan = personalize_plan(profile, base, client)
        fat_max = 0.40 * 2000.0 / 9.0
        assert plan.targets["204"] <= fat_max + 0.5
        assert "fat" in plan.clamped

    def test_fat_below_min_clamped(self):
        # base fat_pct=20%, -10% → 10% → 22g < fat_min 33.3g → clamp
        profile = _profile()
        base = _base_targets(kcal=2000.0, protein_pct=0.30, carb_pct=0.50, fat_pct=0.20)
        client = _mock_client(protein_pct_delta=0.0, fat_pct_delta=-10.0)
        plan = personalize_plan(profile, base, client)
        fat_min = 0.15 * 2000.0 / 9.0
        assert plan.targets["204"] >= fat_min - 0.5
        assert "fat" in plan.clamped

    def test_clamped_list_non_empty_when_bound_hit(self):
        profile = _profile(weight_kg=70.0)
        base = _base_targets(kcal=2000.0)
        client = _mock_client(protein_pct_delta=8.0)
        plan = personalize_plan(profile, base, client)
        assert len(plan.clamped) > 0

    def test_atwater_still_holds_after_clamping(self):
        profile = _profile(weight_kg=70.0)
        base = _base_targets(kcal=2000.0)
        client = _mock_client(protein_pct_delta=8.0, fat_pct_delta=8.0)
        plan = personalize_plan(profile, base, client)
        p = plan.targets["203"]
        c = plan.targets["205"]
        f = plan.targets["204"]
        assert abs(4.0 * p + 4.0 * c + 9.0 * f - 2000.0) <= 5.0


# ---------------------------------------------------------------------------
# Drift repaired
# ---------------------------------------------------------------------------


class TestDriftRepaired:
    # base_targets where 4P+4C+9F = 2230 ≠ 2000 (drift=230 >> 5 kcal tolerance)
    # weight_kg=100 so protein 200g stays in [120, 240] (no protein clamp)
    _DRIFTED_BASE = {"208": 2000.0, "203": 200.0, "205": 200.0, "204": 70.0}
    _DRIFT_PROFILE = MacroProfile(
        age=35, sex="male", height_cm=180.0, weight_kg=100.0,
        activity="moderate", goal="maintain",
    )

    def test_drift_recorded_in_clamped(self):
        client = _mock_client(protein_pct_delta=0.0, fat_pct_delta=0.0)
        plan = personalize_plan(self._DRIFT_PROFILE, self._DRIFTED_BASE, client)
        assert "drift" in plan.clamped

    def test_atwater_consistent_after_repair(self):
        client = _mock_client(protein_pct_delta=0.0, fat_pct_delta=0.0)
        plan = personalize_plan(self._DRIFT_PROFILE, self._DRIFTED_BASE, client)
        p = plan.targets["203"]
        c = plan.targets["205"]
        f = plan.targets["204"]
        assert abs(4.0 * p + 4.0 * c + 9.0 * f - 2000.0) <= 5.0

    def test_kcal_unchanged_after_repair(self):
        client = _mock_client()
        plan = personalize_plan(self._DRIFT_PROFILE, self._DRIFTED_BASE, client)
        assert plan.targets["208"] == 2000.0

    def test_consistent_base_does_not_record_drift(self):
        profile = _profile(weight_kg=80.0)
        base = _base_targets(kcal=2000.0)  # properly constructed, drift < 5 kcal
        client = _mock_client()
        plan = personalize_plan(profile, base, client)
        assert "drift" not in plan.clamped


# ---------------------------------------------------------------------------
# Client raises → soft fallback
# ---------------------------------------------------------------------------


class TestSoftFallback:
    def test_exception_returns_base_targets(self):
        base = _base_targets(kcal=2000.0)
        profile = _profile()
        client = MagicMock()
        client.models.generate_content.side_effect = RuntimeError("Vertex unavailable")
        plan = personalize_plan(profile, base, client)
        assert plan.targets == base

    def test_exception_source_is_formula(self):
        base = _base_targets()
        profile = _profile()
        client = MagicMock()
        client.models.generate_content.side_effect = Exception("timeout")
        plan = personalize_plan(profile, base, client)
        assert plan.source == "formula"

    def test_exception_rationale_non_empty(self):
        base = _base_targets()
        profile = _profile(age=25, sex="female", activity="light", goal="cut")
        client = MagicMock()
        client.models.generate_content.side_effect = Exception("timeout")
        plan = personalize_plan(profile, base, client)
        assert plan.rationale.strip()

    def test_exception_rationale_mentions_profile(self):
        base = _base_targets()
        profile = _profile(age=25, sex="female", activity="light", goal="cut")
        client = MagicMock()
        client.models.generate_content.side_effect = Exception("timeout")
        plan = personalize_plan(profile, base, client)
        # Templated rationale should mention at least one profile attribute
        combined = plan.rationale.lower()
        assert any(word in combined for word in ["25", "female", "light", "cut", "personalisation"])

    def test_empty_response_text_falls_back(self):
        base = _base_targets()
        profile = _profile()
        response = MagicMock()
        response.text = None
        client = MagicMock()
        client.models.generate_content.return_value = response
        plan = personalize_plan(profile, base, client)
        assert plan.targets == base
        assert plan.source == "formula"

    def test_invalid_json_falls_back(self):
        base = _base_targets()
        profile = _profile()
        response = MagicMock()
        response.text = "not json at all"
        client = MagicMock()
        client.models.generate_content.return_value = response
        plan = personalize_plan(profile, base, client)
        assert plan.targets == base
        assert plan.source == "formula"

    def test_fallback_preserves_base_kcal(self):
        base = _base_targets(kcal=1800.0)
        profile = _profile()
        client = MagicMock()
        client.models.generate_content.side_effect = RuntimeError("fail")
        plan = personalize_plan(profile, base, client)
        assert plan.targets["208"] == 1800.0


# ---------------------------------------------------------------------------
# Fenced JSON response — mirrors parse_meal.py's test_strips_markdown_code_fences.
# Gemini sometimes wraps its JSON in a markdown code block even with
# response_mime_type="application/json"; _strip_fences must remove it before
# json.loads so personalize_plan doesn't silently fall back.
# ---------------------------------------------------------------------------


class TestFencedResponse:
    def _fenced_client(self, fence_tag: str = "json") -> MagicMock:
        payload = (
            '{"rationale": "more protein for muscle", '
            '"protein_pct_delta": 3.0, "fat_pct_delta": 0.0}'
        )
        response = MagicMock()
        response.text = f"```{fence_tag}\n{payload}\n```"
        client = MagicMock()
        client.models.generate_content.return_value = response
        return client

    def test_json_fenced_response_is_parsed_not_fallen_back(self):
        """A ```json ... ``` wrapper is stripped and the plan uses source='ai', not 'formula'."""
        plan = personalize_plan(_profile(), _base_targets(), self._fenced_client("json"))
        assert plan.source == "ai"

    def test_json_fenced_rationale_is_extracted(self):
        plan = personalize_plan(_profile(), _base_targets(), self._fenced_client("json"))
        assert "protein" in plan.rationale.lower()

    def test_plain_fenced_response_is_also_parsed(self):
        """A plain ``` ... ``` fence (no language tag) is also stripped correctly."""
        plan = personalize_plan(_profile(), _base_targets(), self._fenced_client(""))
        assert plan.source == "ai"
