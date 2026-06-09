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
# Non-finite delta → soft fallback (not a silent +10 pp shift)
#
# json.loads accepts the bare ``NaN`` / ``Infinity`` tokens a model can emit in
# its raw text, and pydantic admits them by default, so a garbled delta used to
# slip through to the defensive ``max(-10, min(10, x))`` clamp — where a NaN
# coerces to the +10.0 bound, applying a real, large macro shift presented as a
# legitimate ``source="ai"`` plan. A non-finite delta is malformed model output
# of the same class as bad JSON: it must fall back to the formula targets.
# ---------------------------------------------------------------------------


class TestNonFiniteDeltaFallsBack:
    def _client(self, protein_token: str = "0.0", fat_token: str = "0.0") -> MagicMock:
        response = MagicMock()
        response.text = (
            f'{{"rationale": "shift", "protein_pct_delta": {protein_token}, '
            f'"fat_pct_delta": {fat_token}}}'
        )
        client = MagicMock()
        client.models.generate_content.return_value = response
        return client

    def test_nan_protein_delta_falls_back_to_formula(self):
        base = _base_targets(kcal=2000.0)
        plan = personalize_plan(_profile(), base, self._client(protein_token="NaN"))
        assert plan.source == "formula"
        assert plan.targets == base

    def test_infinite_fat_delta_falls_back_to_formula(self):
        base = _base_targets(kcal=2000.0)
        plan = personalize_plan(_profile(), base, self._client(fat_token="Infinity"))
        assert plan.source == "formula"
        assert plan.targets == base

    def test_negative_infinite_protein_delta_falls_back_to_formula(self):
        base = _base_targets(kcal=2000.0)
        plan = personalize_plan(_profile(), base, self._client(protein_token="-Infinity"))
        assert plan.source == "formula"
        assert plan.targets == base


# ---------------------------------------------------------------------------
# Fenced JSON response — mirrors parse_meal.py's test_strips_markdown_code_fences.
# Gemini sometimes wraps its JSON in a markdown code block even with
# response_mime_type="application/json"; _strip_fences must remove it before
# json.loads so personalize_plan doesn't silently fall back.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Credential-init failure — _default_client() raises before the try/except
# ---------------------------------------------------------------------------


class TestCredentialInitFailure:
    def test_credential_init_failure_falls_back_to_formula(self, monkeypatch):
        """If _default_client() raises (bad creds, missing package), personalize_plan
        must return the formula plan rather than propagating the exception — the same
        fail-soft guarantee the inner try/except gives for Gemini call failures."""
        from dietrace.macros import personalize as _mod

        def _bad_client():
            raise RuntimeError("vertex credentials unavailable")

        monkeypatch.setattr(_mod, "_default_client", _bad_client)

        profile = _profile()
        base = _base_targets()
        # No client injected — triggers _default_client() which now raises.
        plan = personalize_plan(profile, base)
        assert plan.source == "formula"
        assert plan.targets == base

    def test_credential_init_failure_rationale_non_empty(self, monkeypatch):
        """The fallback rationale must be a non-empty templated string."""
        from dietrace.macros import personalize as _mod

        def _import_error():
            raise ImportError("google.genai not installed")

        monkeypatch.setattr(_mod, "_default_client", _import_error)

        plan = personalize_plan(_profile(age=28, sex="female"), _base_targets())
        assert plan.rationale.strip()


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


# ---------------------------------------------------------------------------
# Carb-goes-negative guard (personalize_plan lines 232–240)
#
# When protein + fat together exceed kcal after clamping, the remainder for
# carbohydrate is negative. The guard reduces fat until carb can be 0.0 g
# and records "fat" in clamped — guaranteeing 4P + 4C + 9F = kcal exactly.
#
# Triggered by: very heavy person (weight_kg=200) on a 1800 kcal cut plan
# with Gemini requesting +10 pp protein and +10 pp fat from a 55/35/10 split.
# After deltas: protein_raw=292.5 g (in protein bounds, not clamped),
# fat_raw=90 g (> fat_max=80, clamped to 80) → carb_kcal = 1800−1170−720 = −90.
# ---------------------------------------------------------------------------


class TestCarbNegativeGuard:
    def _setup(self):
        """Profile + base targets + mock client that trigger the carb<0 path."""
        profile = MacroProfile(
            age=40, sex="male", height_cm=190.0, weight_kg=200.0,
            activity="moderate", goal="cut",
        )
        # Consistent 55/10/35 split (Atwater = 1800.0, no drift).
        base = {
            "208": 1800.0,
            "203": round(1800.0 * 0.55 / 4.0, 1),  # 247.5 g protein
            "205": round(1800.0 * 0.10 / 4.0, 1),  # 45.0 g carb
            "204": round(1800.0 * 0.35 / 9.0, 1),  # 70.0 g fat
        }
        response = MagicMock()
        response.text = (
            '{"rationale": "athlete needs high protein and fat",'
            ' "protein_pct_delta": 10.0, "fat_pct_delta": 10.0}'
        )
        client = MagicMock()
        client.models.generate_content.return_value = response
        return profile, base, client

    def test_carb_is_non_negative_when_guard_fires(self):
        profile, base, client = self._setup()
        plan = personalize_plan(profile, base, client)
        assert plan.targets["205"] >= 0.0

    def test_atwater_holds_when_carb_zeroed(self):
        profile, base, client = self._setup()
        plan = personalize_plan(profile, base, client)
        p, c, f = plan.targets["203"], plan.targets["205"], plan.targets["204"]
        assert abs(4.0 * p + 4.0 * c + 9.0 * f - 1800.0) <= 5.0

    def test_fat_in_clamped_when_guard_fires(self):
        profile, base, client = self._setup()
        plan = personalize_plan(profile, base, client)
        assert "fat" in plan.clamped

    def test_kcal_unchanged_when_guard_fires(self):
        profile, base, client = self._setup()
        plan = personalize_plan(profile, base, client)
        assert plan.targets["208"] == 1800.0

    def test_fat_not_added_twice_when_already_clamped_before_guard(self):
        """The guard's 'if fat not in clamped' branch is False here — fat was already
        clamped by the fat-bounds check (90g → 80g) before the guard fires, so the
        guard must not append it a second time, leaving exactly one 'fat' entry."""
        profile, base, client = self._setup()
        plan = personalize_plan(profile, base, client)
        # fat was clamped by the fat-bounds step, then the guard fires but skips append
        assert plan.clamped.count("fat") == 1


# ---------------------------------------------------------------------------
# Carb-goes-negative guard: fat appended FRESH by the guard (not pre-clamped)
#
# The True arm of  `if "fat" not in clamped: clamped.append("fat")`  is never
# exercised by TestCarbNegativeGuard because in that setup fat is clamped by the
# fat-bounds check BEFORE the guard fires.  Here fat stays within bounds — it is
# protein that is clamped up by the protein-bounds check, and the resulting
# 360 g × 4 kcal/g + 60 g × 9 kcal/g = 1980 > 1800 kcal drives carb negative.
# The guard then reduces fat and, since "fat" is not yet in clamped, appends it.
#
# Setup: weight_kg=300 → protein_lo=360 g (80 % of 1800 kcal).
# Base 10 % / 60 % / 30 % protein/carb/fat split is Atwater-consistent.
# Gemini returns +10 pp protein → protein_raw=90 g < 360 → clamped to 360.
# fat_raw=60 g sits in [30, 80] → not clamped.  carb_kcal = 1800−1440−540 = −180.
# Guard fires, reduces fat to 40 g, appends "fat" to clamped for the first time.
# ---------------------------------------------------------------------------


class TestCarbNegativeGuardFatAddedFresh:
    def _setup(self):
        profile = MacroProfile(
            age=40, sex="male", height_cm=190.0, weight_kg=300.0,
            activity="sedentary", goal="cut",
        )
        # Atwater-consistent 10 / 60 / 30 split at 1800 kcal (no drift).
        base = {
            "208": 1800.0,
            "203": round(1800.0 * 0.10 / 4.0, 1),   # 45.0 g protein
            "205": round(1800.0 * 0.60 / 4.0, 1),   # 270.0 g carb
            "204": round(1800.0 * 0.30 / 9.0, 1),   # 60.0 g fat
        }
        # +10 pp protein pushes protein_raw to 90 g (< protein_lo=360) → clamped.
        # 0 pp fat leaves fat at 60 g (within [30, 80]) → NOT clamped before guard.
        response = MagicMock()
        response.text = (
            '{"rationale": "high protein athlete",'
            ' "protein_pct_delta": 10.0, "fat_pct_delta": 0.0}'
        )
        client = MagicMock()
        client.models.generate_content.return_value = response
        return profile, base, client

    def test_fat_appended_fresh_by_guard(self):
        """The guard's True arm fires: 'fat' is not in clamped when the guard runs,
        so the guard appends it — producing exactly one 'fat' entry in clamped."""
        profile, base, client = self._setup()
        plan = personalize_plan(profile, base, client)
        assert "fat" in plan.clamped
        assert plan.clamped.count("fat") == 1

    def test_carb_non_negative_when_fat_added_fresh(self):
        profile, base, client = self._setup()
        plan = personalize_plan(profile, base, client)
        assert plan.targets["205"] >= 0.0

    def test_atwater_holds_when_fat_added_fresh(self):
        profile, base, client = self._setup()
        plan = personalize_plan(profile, base, client)
        p, c, f = plan.targets["203"], plan.targets["205"], plan.targets["204"]
        assert abs(4.0 * p + 4.0 * c + 9.0 * f - 1800.0) <= 5.0

    def test_kcal_unchanged_when_fat_added_fresh(self):
        profile, base, client = self._setup()
        plan = personalize_plan(profile, base, client)
        assert plan.targets["208"] == 1800.0
