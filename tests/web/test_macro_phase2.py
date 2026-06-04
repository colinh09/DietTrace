"""Macros Phase 2 — adherence on /macros/plan, the Phoenix push on /macros/save,
and the /macros/retune alignment-lift endpoint.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from dietrace.web.app import create_app
from dietrace.web.feedback import FeedbackStore
from dietrace.web.goal_store import GoalStore
from dietrace.web.macro_memory import SqliteMacroMemory, push_macro_preference
from dietrace.web.memory import SqliteMemory
from dietrace.web.store import MealLogStore
from dietrace.web.trust import TrustStore

_PROFILE = {
    "age": 30, "sex": "male", "height_cm": 178.0, "weight_kg": 80.0,
    "activity": "sedentary", "goal": "maintain", "ai_help": False,
}
_HIGH = {"targets": {"208": 2000, "203": 200, "204": 44, "205": 200}, "source": "preset"}


def _client(tmp_path, pusher=None) -> TestClient:
    app = create_app(
        meal_logger=lambda text, examples=None: {"totals": [], "per_item": []},
        store=MealLogStore(tmp_path / "log.sqlite"),
        feedback_store=FeedbackStore(tmp_path / "fb.sqlite"),
        trust_store=TrustStore(tmp_path / "trust.sqlite"),
        goal_store=GoalStore(tmp_path / "goals.sqlite"),
        memory=SqliteMemory(tmp_path / "mem.sqlite"),
        macro_memory=SqliteMacroMemory(tmp_path / "macro_mem.sqlite"),
        macro_pref_pusher=pusher or (lambda u, s: False),
        feedback_pusher=lambda *a: False,
        tracer_init=lambda name: None,
    )
    return TestClient(app)


def test_plan_includes_adherence_when_personalized(tmp_path) -> None:
    c = _client(tmp_path)
    c.post("/macros/save", json=_HIGH, headers={"X-DietTrace-User": "a"})
    body = c.post("/macros/plan", json=_PROFILE, headers={"X-DietTrace-User": "a"}).json()
    assert body["personalized"] is True
    assert body["adherence"] is not None
    assert 0.0 <= body["adherence"]["score"] <= 1.0


def test_plan_has_no_adherence_without_preference(tmp_path) -> None:
    c = _client(tmp_path)
    body = c.post("/macros/plan", json=_PROFILE, headers={"X-DietTrace-User": "b"}).json()
    assert body["adherence"] is None


def test_save_calls_pusher_and_reports_banked(tmp_path) -> None:
    pusher = MagicMock(return_value=True)
    c = _client(tmp_path, pusher=pusher)
    r = c.post("/macros/save", json=_HIGH, headers={"X-DietTrace-User": "a"}).json()
    assert r["banked"] is True
    pusher.assert_called_once()
    user_arg, split_arg = pusher.call_args.args
    assert user_arg == "a"
    assert split_arg["protein_pct"] == 0.4  # 200 g * 4 / 2000


def test_retune_shows_alignment_lift(tmp_path) -> None:
    c = _client(tmp_path)
    c.post("/macros/save", json=_HIGH, headers={"X-DietTrace-User": "a"})
    r = c.post("/macros/retune", json=_PROFILE, headers={"X-DietTrace-User": "a"}).json()
    assert r["cases"] == 1
    assert r["after"] > r["before"]
    assert r["improved"] is True
    assert r["protein_shift"] > 0  # tuned up toward the high-protein preference


def test_retune_zero_cases_without_preference(tmp_path) -> None:
    c = _client(tmp_path)
    r = c.post("/macros/retune", json=_PROFILE, headers={"X-DietTrace-User": "z"}).json()
    assert r["cases"] == 0
    assert r["improved"] is False


def test_push_macro_preference_fail_soft_without_creds(monkeypatch) -> None:
    monkeypatch.delenv("PHOENIX_API_KEY", raising=False)
    monkeypatch.delenv("PHOENIX_BASE_URL", raising=False)
    assert push_macro_preference("a", {"protein_pct": 0.3, "fat_pct": 0.3}) is False
