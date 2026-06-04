"""End-to-end macro learning: save → the next plan is personalized (the closure).

The agent learns the user's macro preference the same way it learns food portions:
saving targets remembers the split, and a later plan for that user biases toward
it — per-user, safe (still passes its eval), and not for anyone else.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from dietrace.web.app import create_app
from dietrace.web.feedback import FeedbackStore
from dietrace.web.goal_store import GoalStore
from dietrace.web.macro_memory import SqliteMacroMemory
from dietrace.web.memory import SqliteMemory
from dietrace.web.store import MealLogStore
from dietrace.web.trust import TrustStore

_PROFILE = {
    "age": 30, "sex": "male", "height_cm": 178.0, "weight_kg": 80.0,
    "activity": "sedentary", "goal": "maintain", "ai_help": False,
}
# A high-protein split (40% protein, ~20% fat of 2000 kcal) and a low-protein one.
_HIGH_PROTEIN = {"targets": {"208": 2000, "203": 200, "204": 44, "205": 200}, "source": "preset"}
_LOW_PROTEIN = {"targets": {"208": 2000, "203": 100, "204": 78, "205": 280}, "source": "preset"}


def _client(tmp_path) -> TestClient:
    app = create_app(
        meal_logger=lambda text, examples=None: {"totals": [], "per_item": []},
        store=MealLogStore(tmp_path / "log.sqlite"),
        feedback_store=FeedbackStore(tmp_path / "fb.sqlite"),
        trust_store=TrustStore(tmp_path / "trust.sqlite"),
        goal_store=GoalStore(tmp_path / "goals.sqlite"),
        memory=SqliteMemory(tmp_path / "mem.sqlite"),
        macro_memory=SqliteMacroMemory(tmp_path / "macro_mem.sqlite"),
        feedback_pusher=lambda *a: False,
        tracer_init=lambda name: None,
    )
    return TestClient(app)


def _protein_pct(body: dict) -> float:
    t = body["targets"]
    return 4 * t["203"] / t["208"]


def test_plan_not_personalized_before_any_save(tmp_path) -> None:
    c = _client(tmp_path)
    r = c.post("/macros/plan", json=_PROFILE, headers={"X-DietTrace-User": "alice"})
    assert r.json()["personalized"] is False


def test_high_protein_preference_is_learned_and_safe(tmp_path) -> None:
    c = _client(tmp_path)
    assert c.post("/macros/save", json=_HIGH_PROTEIN,
                  headers={"X-DietTrace-User": "alice"}).status_code == 200
    body = c.post("/macros/plan", json=_PROFILE,
                  headers={"X-DietTrace-User": "alice"}).json()
    assert body["personalized"] is True
    assert _protein_pct(body) > 0.33  # biased up toward the high-protein preference
    assert body["targets"]["203"] <= 2.4 * 80 + 0.5  # but clamped to the safe ceiling
    assert body["eval"]["pass"] is True


def test_low_protein_preference_is_learned(tmp_path) -> None:
    c = _client(tmp_path)
    c.post("/macros/save", json=_LOW_PROTEIN, headers={"X-DietTrace-User": "carol"})
    body = c.post("/macros/plan", json=_PROFILE,
                  headers={"X-DietTrace-User": "carol"}).json()
    assert body["personalized"] is True
    assert _protein_pct(body) < 0.25  # biased down — it learns the actual preference
    assert body["eval"]["pass"] is True


def test_preference_is_per_user(tmp_path) -> None:
    c = _client(tmp_path)
    c.post("/macros/save", json=_HIGH_PROTEIN, headers={"X-DietTrace-User": "alice"})
    body = c.post("/macros/plan", json=_PROFILE,
                  headers={"X-DietTrace-User": "bob"}).json()
    assert body["personalized"] is False


def test_preset_plan_personalized_after_save(tmp_path) -> None:
    c = _client(tmp_path)
    c.post("/macros/save", json=_HIGH_PROTEIN, headers={"X-DietTrace-User": "alice"})
    body = c.post("/macros/plan", json={"preset": "maintain"},
                  headers={"X-DietTrace-User": "alice"}).json()
    assert body["personalized"] is True
    assert body["eval"]["pass"] is True
