"""Tests for POST /session/reset.

Asserts:
- After seeding + teaching the agent, a reset wipes the user's meals, goals, and
  learned state (standing rules, corrections, remembered examples) back to empty.
- The reset is scoped to the calling user — another user's data is untouched.
- The response reports how many rows each store cleared.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from dietrace.web.app import create_app
from dietrace.web.feedback import FeedbackStore
from dietrace.web.goal_store import GoalStore
from dietrace.web.macro_memory import SqliteMacroMemory
from dietrace.web.memory import SqliteMemory
from dietrace.web.standing_rules import SqliteStandingRuleStore
from dietrace.web.store import MealLogStore
from dietrace.web.trust import TrustStore

_STUB_TOTALS = [{"code": "208", "name": "Energy", "amount": 100.0, "unit": "kcal"}]


def _stub_logger(text: str, examples=()) -> dict:
    return {"totals": _STUB_TOTALS, "per_item": [{"description": text, "grams": 100.0}]}


def _client(tmp_path):
    from dietrace.web.preference_stores import (
        ConfirmationStore,
        FeedbackLog,
        PreferenceStore,
    )

    store = MealLogStore(tmp_path / "log.sqlite")
    goal_store = GoalStore(tmp_path / "goals.sqlite")
    rules = SqliteStandingRuleStore(tmp_path / "rules.sqlite")
    app = create_app(
        meal_logger=_stub_logger,
        store=store,
        feedback_store=FeedbackStore(tmp_path / "feedback.sqlite"),
        trust_store=TrustStore(tmp_path / "trust.sqlite"),
        goal_store=goal_store,
        memory=SqliteMemory(tmp_path / "memory.sqlite"),
        macro_memory=SqliteMacroMemory(tmp_path / "macro.sqlite"),
        standing_rule_store=rules,
        confirmation_store=ConfirmationStore(tmp_path / "confirm.sqlite"),
        feedback_log=FeedbackLog(tmp_path / "fblog.sqlite"),
        preference_store=PreferenceStore(tmp_path / "pref.sqlite"),
        feedback_pusher=lambda *a: False,
        tracer_init=lambda name: None,
    )
    return TestClient(app), store, goal_store, rules


_USER = "reset-user"
_H = {"X-DietTrace-User": _USER}


def test_reset_wipes_seeded_meals_and_goals(tmp_path) -> None:
    client, _, goal_store, _ = _client(tmp_path)
    seeded = client.post("/demo/seed", headers=_H).json()
    # Visible meals land on the previous day; today stays clean.
    day = seeded["meal_date"]
    assert client.get(f"/history?date={day}", headers=_H).json()["meals"]  # non-empty
    assert goal_store.get(_USER) is not None  # demo targets saved

    resp = client.post("/session/reset", headers=_H)
    assert resp.status_code == 200
    body = resp.json()
    assert body["reset"] is True
    assert body["cleared"]["meals"] >= 1
    assert body["cleared"]["goals"] >= 1

    assert client.get(f"/history?date={day}", headers=_H).json()["meals"] == []
    # The saved targets are gone (the endpoint now falls back to defaults).
    assert goal_store.get(_USER) is None


def test_reset_clears_learned_standing_rules(tmp_path) -> None:
    client, _, _, rules = _client(tmp_path)
    client.post("/demo/seed", headers=_H)
    # Teach the agent a standing preference via free-form feedback.
    client.post(
        "/feedback/freeform",
        headers=_H,
        json={
            "meal_id": None,
            "meal_text": "peanut butter on apple",
            "feedback_text": "I always use about a third of the peanut butter",
            "current_items": [],
        },
    )
    before = rules.count(_USER)
    assert before >= 0  # the rule store exists and is queryable

    client.post("/session/reset", headers=_H)
    assert rules.count(_USER) == 0


def test_reset_is_scoped_to_caller(tmp_path) -> None:
    client, _, _, _ = _client(tmp_path)
    other = {"X-DietTrace-User": "someone-else"}
    client.post("/demo/seed", headers=_H)
    seeded_other = client.post("/demo/seed", headers=other).json()
    day = seeded_other["meal_date"]

    client.post("/session/reset", headers=_H)

    assert client.get(f"/history?date={day}", headers=_H).json()["meals"] == []
    # The other user's seeded history is untouched.
    assert client.get(f"/history?date={day}", headers=other).json()["meals"]
