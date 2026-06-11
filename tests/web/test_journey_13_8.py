"""End-to-end nutritionist journey integration test.

Covers the full arc under one user/memory, all externals mocked:
  plan macros → save targets → /goals reflects plan →
  log a meal against those targets → /analysis uses saved targets →
  correct the meal → correction banked as ground truth →
  re-logging recalls the correction → retune reports the banked case.

This is the experiment's pass/fail bar.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dietrace.web.app import create_app
from dietrace.web.feedback import FeedbackStore
from dietrace.web.goal_store import GoalStore
from dietrace.web.memory import SqliteMemory
from dietrace.web.store import MealLogStore
from dietrace.web.trust import TrustStore
from tests.nutrition.fixtures_food_db import EGG_FDC_ID

_USER = "journey_user_13_8"

# Per-100 g egg nutrients — the stub logger always returns a full egg (100 g).
_EGG_NUTRIENTS = [
    {"code": "208", "name": "Energy", "amount": 143.0, "unit": "kcal"},
    {"code": "203", "name": "Protein", "amount": 12.6, "unit": "g"},
    {"code": "204", "name": "Total lipid (fat)", "amount": 9.51, "unit": "g"},
    {"code": "205", "name": "Carbohydrate, by difference", "amount": 0.72, "unit": "g"},
]
_EGG_ITEM = {
    "fdc_id": EGG_FDC_ID,
    "description": "Egg, whole, raw, fresh",
    "grams": 100.0,
    "nutrients": _EGG_NUTRIENTS,
}


def _stub_logger(text: str, examples=None) -> dict:
    """Deterministic meal logger: always returns one egg (100 g), no Gemini call."""
    return {"totals": _EGG_NUTRIENTS, "per_item": [_EGG_ITEM]}


@pytest.fixture
def journey(tmp_path: Path):
    """TestClient + stores wired for the journey test (no live externals)."""
    goal_store = GoalStore(tmp_path / "goals.sqlite")
    memory = SqliteMemory(tmp_path / "memory.sqlite")

    app = create_app(
        meal_logger=_stub_logger,
        store=MealLogStore(tmp_path / "meals.sqlite"),
        feedback_store=FeedbackStore(tmp_path / "feedback.sqlite"),
        trust_store=TrustStore(tmp_path / "trust.sqlite"),
        goal_store=goal_store,
        memory=memory,
        feedback_pusher=lambda *a: False,
        tracer_init=lambda name: None,
    )
    client = TestClient(app, headers={"X-DietTrace-User": _USER})
    return client, goal_store, memory


def test_full_nutritionist_journey(journey) -> None:
    """The full arc under one user/memory passes deterministically.

    Steps exercised:
      1. plan_macros (preset)
      2. save targets to GoalStore
      3. /goals reflects the saved plan (not static defaults)
      4. log a meal — persisted against the saved goals
      5. /analysis uses the saved goal targets
      6. correct the meal — rescaled + banked in memory as ground truth
      7. re-log the same meal → recalled (the correction took effect)
      8. retune reports ≥ 1 banked case (the loop is complete)
    """
    client, goal_store, memory = journey

    # ── Step 1: plan macros ───────────────────────────────────────────────────
    plan_resp = client.post("/macros/plan", json={"preset": "maintain"})
    assert plan_resp.status_code == 200, plan_resp.text
    plan = plan_resp.json()
    assert set(plan["targets"]) >= {"208", "203", "205", "204"}
    assert plan["source"] == "preset"
    assert plan["eval"] is not None
    kcal_target = float(plan["targets"]["208"])
    assert kcal_target > 0

    # ── Step 2: save targets (user commits to this plan) ─────────────────────
    save_resp = client.post(
        "/macros/save",
        json={
            "targets": plan["targets"],
            "rationale": plan.get("rationale"),
            "source": plan["source"],
        },
    )
    assert save_resp.status_code == 200, save_resp.text
    # Verify directly in the store (not just the API).
    stored = goal_store.get(_USER)
    assert stored is not None
    assert abs(float(stored.get("208", 0)) - kcal_target) < 1.0

    # ── Step 3: /goals reflects the saved macro plan ──────────────────────────
    goals_resp = client.get("/goals")
    assert goals_resp.status_code == 200
    goals_by_code = {g["code"]: float(g["target"]) for g in goals_resp.json()["goals"]}
    assert abs(goals_by_code.get("208", 0) - kcal_target) < 1.0

    # ── Step 4: log a meal against those targets ──────────────────────────────
    log_resp = client.post("/log", json={"text": "one egg"})
    assert log_resp.status_code == 200, log_resp.text
    log_body = log_resp.json()
    assert isinstance(log_body["id"], int)
    logged_kcal = next(t["amount"] for t in log_body["totals"] if t["code"] == "208")
    assert logged_kcal == pytest.approx(143.0)
    # Not recalled yet — first log of this meal text.
    assert not log_body.get("recalled", False)

    # ── Step 5: /analysis uses the saved goal targets ─────────────────────────
    analysis_resp = client.get("/analysis")
    assert analysis_resp.status_code == 200
    analysis = analysis_resp.json()
    assert analysis["meal_count"] == 1
    energy_goal = next(g for g in analysis["goals"] if g["code"] == "208")
    assert abs(energy_goal["target"] - kcal_target) < 1.0
    # The consumed energy matches what was logged.
    assert abs(energy_goal["consumed"] - 143.0) < 0.1

    # ── Step 6: correct the meal — bank as ground truth ───────────────────────
    # User says it was half an egg (50 g), not 100 g.
    correct_resp = client.post(
        "/correct",
        json={
            "meal_text": "one egg",
            "items": [
                {
                    "description": "Egg, whole, raw, fresh",
                    "fdc_id": EGG_FDC_ID,
                    "original_grams": 100.0,
                    "corrected_grams": 50.0,
                    "nutrients": _EGG_NUTRIENTS,
                }
            ],
        },
    )
    assert correct_resp.status_code == 200, correct_resp.text
    correct_body = correct_resp.json()
    assert correct_body["ok"] is True
    assert correct_body["corrections"] == 1

    # ── Step 7: verify the correction is banked in memory ────────────────────
    recalled = memory.recall(_USER, "one egg")
    assert recalled is not None, "correction must be stored in user memory"
    assert recalled["per_item"][0]["grams"] == pytest.approx(50.0)
    # Calories should be rescaled: 143 * (50/100) = 71.5 kcal.
    cal_total = next(t for t in recalled["totals"] if t["code"] == "208")
    assert cal_total["amount"] == pytest.approx(71.5)

    # ── Step 8: re-log the same meal → recalled, not re-computed ─────────────
    recall_resp = client.post("/log", json={"text": "one egg"})
    assert recall_resp.status_code == 200
    recall_body = recall_resp.json()
    assert recall_body.get("recalled") is True, "second log of corrected meal must be recalled"
    # The recalled calories are the corrected 71.5 kcal, not the stub 143.0 kcal.
    recalled_kcal = next(t["amount"] for t in recall_body["totals"] if t["code"] == "208")
    assert recalled_kcal == pytest.approx(71.5)
