"""Tests for POST /demo/seed.

Asserts:
- /demo/seed populates the user's /history deterministically (correct count,
  all meal texts present including the habit-mismatch meal).
- /goals is set to the demo macro targets.
- The habit-mismatch meal has needs_review=True and a review_reason.
- Two calls add two sets of meals (deterministic, not idempotent by design — judges
  can re-seed and still see the full populated state).
- Per-user isolation: two users each get their own isolated seed.
- Trace steps are persisted in /history for every seeded meal.
- No live Gemini/Phoenix call is made (the conftest no-network guard enforces this).
"""

from __future__ import annotations

from collections import Counter

from fastapi.testclient import TestClient

from dietrace.web.app import create_app
from dietrace.web.demo_seed import DEMO_GOALS, DEMO_MEALS
from dietrace.web.feedback import FeedbackStore
from dietrace.web.goal_store import GoalStore
from dietrace.web.memory import SqliteMemory
from dietrace.web.store import MealLogStore
from dietrace.web.trust import TrustStore

_STUB_TOTALS = [{"code": "208", "name": "Energy", "amount": 100.0, "unit": "kcal"}]


def _stub_logger(text: str, examples=()) -> dict:
    return {"totals": _STUB_TOTALS, "per_item": [{"description": text, "grams": 100.0}]}


def _client(tmp_path):
    store = MealLogStore(tmp_path / "log.sqlite")
    goal_store = GoalStore(tmp_path / "goals.sqlite")
    app = create_app(
        meal_logger=_stub_logger,
        store=store,
        feedback_store=FeedbackStore(tmp_path / "feedback.sqlite"),
        trust_store=TrustStore(tmp_path / "trust.sqlite"),
        goal_store=goal_store,
        memory=SqliteMemory(tmp_path / "memory.sqlite"),
        feedback_pusher=lambda *a: False,
        tracer_init=lambda name: None,
    )
    return TestClient(app), store, goal_store


_USER = "test-demo-user"
_H = {"X-DietTrace-User": _USER}

_MISMATCH_TEXT = "peanut butter on apple"


def test_demo_seed_returns_ok(tmp_path) -> None:
    client, _, _ = _client(tmp_path)
    resp = client.post("/demo/seed", headers=_H)
    assert resp.status_code == 200
    body = resp.json()
    assert body["seeded"] is True
    assert body["meals"] == len(DEMO_MEALS)
    assert body["goals_set"] is True


def test_demo_seed_populates_history(tmp_path) -> None:
    """Seeding inserts exactly len(DEMO_MEALS) meals for today."""
    client, _, _ = _client(tmp_path)
    client.post("/demo/seed", headers=_H)

    hist = client.get("/history", headers=_H).json()
    texts = {m["text"] for m in hist["meals"]}
    assert len(hist["meals"]) == len(DEMO_MEALS)
    for meal in DEMO_MEALS:
        assert meal["text"] in texts, f"'{meal['text']}' missing from /history"


def test_demo_seed_sets_goals(tmp_path) -> None:
    """The demo seed stores per-user macro targets that /goals returns."""
    client, _, _ = _client(tmp_path)
    client.post("/demo/seed", headers=_H)

    goals_resp = client.get("/goals", headers=_H).json()
    by_code = {g["code"]: g["target"] for g in goals_resp["goals"]}
    for code, amount in DEMO_GOALS.items():
        got = by_code.get(code)
        assert got == amount, f"goal {code}: expected {amount}, got {got}"


def test_demo_seed_includes_mismatch_meal(tmp_path) -> None:
    """The over-portioned snack appears in /history with needs_review=True."""
    client, _, _ = _client(tmp_path)
    client.post("/demo/seed", headers=_H)

    hist = client.get("/history", headers=_H).json()
    mismatch = next((m for m in hist["meals"] if m["text"] == _MISMATCH_TEXT), None)
    assert mismatch is not None, f"habit-mismatch meal '{_MISMATCH_TEXT}' not in /history"
    assert mismatch.get("needs_review") is True
    assert mismatch.get("review_reason"), "mismatch meal has no review_reason"


def test_demo_seed_deterministic_content(tmp_path) -> None:
    """Two calls produce the same meal texts in the same order (deterministic)."""
    client, _, _ = _client(tmp_path)

    client.post("/demo/seed", headers=_H)
    client.post("/demo/seed", headers=_H)

    hist = client.get("/history", headers=_H).json()
    all_texts = [m["text"] for m in hist["meals"]]
    assert len(all_texts) == 2 * len(DEMO_MEALS)
    counts = Counter(all_texts)
    for meal in DEMO_MEALS:
        assert counts[meal["text"]] == 2, f"'{meal['text']}' should appear exactly twice"


def test_demo_seed_per_user_isolation(tmp_path) -> None:
    """Two users each get their own isolated seeded history."""
    store = MealLogStore(tmp_path / "log.sqlite")
    goal_store = GoalStore(tmp_path / "goals.sqlite")
    app = create_app(
        meal_logger=_stub_logger,
        store=store,
        feedback_store=FeedbackStore(tmp_path / "feedback.sqlite"),
        trust_store=TrustStore(tmp_path / "trust.sqlite"),
        goal_store=goal_store,
        memory=SqliteMemory(tmp_path / "memory.sqlite"),
        feedback_pusher=lambda *a: False,
        tracer_init=lambda name: None,
    )
    client = TestClient(app)

    client.post("/demo/seed", headers={"X-DietTrace-User": "alice"})
    client.post("/demo/seed", headers={"X-DietTrace-User": "bob"})

    alice = client.get("/history", headers={"X-DietTrace-User": "alice"}).json()
    bob = client.get("/history", headers={"X-DietTrace-User": "bob"}).json()
    assert len(alice["meals"]) == len(DEMO_MEALS)
    assert len(bob["meals"]) == len(DEMO_MEALS)


def test_demo_seed_trace_persisted_in_history(tmp_path) -> None:
    """Every seeded meal in /history carries its trace (parse_meal → log_entry)."""
    client, _, _ = _client(tmp_path)
    client.post("/demo/seed", headers=_H)

    hist = client.get("/history", headers=_H).json()
    for meal in hist["meals"]:
        trace = meal.get("trace")
        assert trace, f"meal '{meal['text']}' has no trace"
        steps = [s["step"] for s in trace]
        assert "parse_meal" in steps, f"parse_meal missing from '{meal['text']}' trace"
        assert "log_entry" in steps, f"log_entry missing from '{meal['text']}' trace"


def test_demo_seed_goals_not_set_without_goal_store(tmp_path) -> None:
    """When no goal_store is wired, /demo/seed still seeds meals (goals_set=False)."""
    store = MealLogStore(tmp_path / "log.sqlite")
    app = create_app(
        meal_logger=_stub_logger,
        store=store,
        feedback_store=FeedbackStore(tmp_path / "feedback.sqlite"),
        trust_store=TrustStore(tmp_path / "trust.sqlite"),
        goal_store=None,
        memory=SqliteMemory(tmp_path / "memory.sqlite"),
        feedback_pusher=lambda *a: False,
        tracer_init=lambda name: None,
    )
    client = TestClient(app)

    resp = client.post("/demo/seed", headers=_H)
    assert resp.status_code == 200
    body = resp.json()
    assert body["seeded"] is True
    assert body["goals_set"] is False
    assert body["meals"] == len(DEMO_MEALS)
