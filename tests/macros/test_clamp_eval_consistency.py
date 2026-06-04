"""A guarded plan must pass its own safety eval (review fix #4).

Regression test for the rounding flake: personalize_plan clamps fat to the 40%
ceiling, stores it rounded to 0.1 g (88.9 g at 2000 kcal = 0.40005 of kcal), and
evaluate_macro_plan must NOT flag that sub-0.1 g rounding as out-of-bounds.
"""

from __future__ import annotations

import json

from dietrace.macros.eval import evaluate_macro_plan
from dietrace.macros.models import MacroProfile
from dietrace.macros.personalize import personalize_plan


class _FakeResp:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModels:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def generate_content(self, **_kwargs: object) -> _FakeResp:
        return _FakeResp(json.dumps(self._payload))


class _FakeClient:
    def __init__(self, payload: dict) -> None:
        self.models = _FakeModels(payload)


def test_fat_clamped_plan_passes_its_own_eval() -> None:
    profile = MacroProfile(
        age=30, sex="male", height_cm=178.0, weight_kg=80.0,
        activity="moderate", goal="maintain",
    )
    base = {"208": 2000.0, "203": 150.0, "204": 67.0, "205": 200.0}
    # LLM pushes fat well past the 40% ceiling so the clamp fires.
    client = _FakeClient({"rationale": "more fat", "protein_pct_delta": 0.0,
                          "fat_pct_delta": 15.0})

    plan = personalize_plan(profile, base, client=client)
    assert "fat" in plan.clamped, "expected the fat clamp to fire"

    result = evaluate_macro_plan(profile, plan)
    assert result["pass"] is True, result["reasons"]
    assert "fat_out_of_bounds" not in result["flags"]
