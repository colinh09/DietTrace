"""Tests for POST /demo/seed.

Asserts:
- /demo/seed populates the user's /history deterministically (correct count,
  all meal texts present including the habit-mismatch meal).
- /goals is set to the demo macro targets.
- The habit-mismatch meal has needs_review=True and a review_reason.
- Re-seeding is idempotent: a second /demo/seed replaces the day with the canned
  set rather than appending duplicates (judges can re-click without stacking).
- Per-user isolation: two users each get their own isolated seed.
- Trace steps are persisted in /history for every seeded meal.
- No live Gemini/Phoenix call is made (the conftest no-network guard enforces this).
"""

from __future__ import annotations

from collections import Counter

import pytest
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
    from dietrace.web.preference_stores import (
        ConfirmationStore,
        FeedbackLog,
        PreferenceStore,
        UserProfileStore,
    )

    store = MealLogStore(tmp_path / "log.sqlite")
    goal_store = GoalStore(tmp_path / "goals.sqlite")
    app = create_app(
        meal_logger=_stub_logger,
        store=store,
        feedback_store=FeedbackStore(tmp_path / "feedback.sqlite"),
        trust_store=TrustStore(tmp_path / "trust.sqlite"),
        goal_store=goal_store,
        memory=SqliteMemory(tmp_path / "memory.sqlite"),
        confirmation_store=ConfirmationStore(tmp_path / "confirm.sqlite"),
        feedback_log=FeedbackLog(tmp_path / "fblog.sqlite"),
        preference_store=PreferenceStore(tmp_path / "pref.sqlite"),
        profile_store=UserProfileStore(tmp_path / "profile.sqlite"),
        feedback_pusher=lambda *a: False,
        tracer_init=lambda name: None,
    )
    return TestClient(app), store, goal_store


_USER = "test-demo-user"
_H = {"X-DietTrace-User": _USER}


def test_demo_seed_returns_decisions_and_tags_seeded_source(tmp_path) -> None:
    """The seed returns the agent's prior decisions (to backfill the feed) and its
    confirmations are tagged source=seed, so /preferences reports them as seeded."""
    client, _, _ = _client(tmp_path)
    resp = client.post("/demo/seed", headers=_H).json()
    decisions = resp["decisions"]
    assert decisions, "seed should return prior agent decisions for the feed"
    ops = {d["op"] for d in decisions}
    assert ops == {"add_dataset_point", "bank_feedback"}
    # Every decision carries its meal; dataset-point rows have no reason line (the
    # "Added to your dataset" label already says it), feedback rows keep theirs.
    assert all(d["meal_text"] for d in decisions)
    assert all(d["reason"] for d in decisions if d["op"] == "bank_feedback")

    prefs = client.get("/preferences", headers=_H).json()
    assert prefs["confirmations_seeded"] == prefs["confirmations"] > 0
    assert prefs["confirmations_custom"] == 0


def test_user_confirm_counts_as_custom_not_seeded(tmp_path) -> None:
    client, _, _ = _client(tmp_path)
    client.post(
        "/confirm",
        json={"meal_text": "my own meal", "items": [],
              "totals": [{"code": "208", "name": "Energy", "amount": 400.0, "unit": "kcal"}]},
        headers=_H,
    )
    prefs = client.get("/preferences", headers=_H).json()
    assert prefs["confirmations_custom"] == 1
    assert prefs["confirmations_seeded"] == 0


def test_demo_seed_returns_ok(tmp_path) -> None:
    client, _, _ = _client(tmp_path)
    resp = client.post("/demo/seed", headers=_H)
    assert resp.status_code == 200
    body = resp.json()
    assert body["seeded"] is True
    assert body["meals"] == len(DEMO_MEALS)
    assert body["goals_set"] is True


def test_demo_seed_records_trust_for_visible_meals(tmp_path) -> None:
    """The recap's 'how it's doing on your meals' reads /trust, so the seed must
    record each visible meal's captured eval — otherwise it shows 0 meals / 0%
    confidence despite a fully loaded day."""
    client, _, _ = _client(tmp_path)
    client.post("/demo/seed", headers=_H)
    trust = client.get("/trust", headers=_H).json()
    assert trust["count"] == len(DEMO_MEALS)
    assert trust["mean_confidence"] > 0


def test_demo_seed_reseed_does_not_stack_trust(tmp_path) -> None:
    """Re-running the seed replaces the trust rows (clear_user), never appends —
    so the recap count stays accurate after a judge re-clicks."""
    client, _, _ = _client(tmp_path)
    client.post("/demo/seed", headers=_H)
    client.post("/demo/seed", headers=_H)
    trust = client.get("/trust", headers=_H).json()
    assert trust["count"] == len(DEMO_MEALS)


def test_demo_seed_visible_today_dataset_yesterday(tmp_path) -> None:
    """The visible playground meals land on TODAY; the confirmed dataset is
    mirrored as badged rows on the PREVIOUS day (nothing hidden — the
    observability-everywhere rule)."""
    client, _, _ = _client(tmp_path)
    resp = client.post("/demo/seed", headers=_H, json={"date": "2026-06-06"}).json()
    assert resp["meal_date"] == "2026-06-06"  # playground meals = today
    assert resp["dataset_date"] == "2026-06-05"  # dataset rows = previous day

    today = client.get("/history?date=2026-06-06", headers=_H).json()["meals"]
    texts = {m["text"] for m in today}
    assert len(today) == len(DEMO_MEALS)
    for meal in DEMO_MEALS:
        assert meal["text"] in texts, f"'{meal['text']}' missing from today"
    assert all(not m.get("dataset_point") for m in today)

    # The previous day is a full simulated day (more meals than the dataset),
    # and exactly the dataset-point rows are flagged + match the held-out set.
    prev = client.get("/history?date=2026-06-05", headers=_H).json()["meals"]
    dataset_rows = [m for m in prev if m.get("dataset_point")]
    assert len(prev) > resp["confirmations"], "prev day should be a fuller day"
    assert len(dataset_rows) == resp["confirmations"]
    # Dataset-point rows carry full per-item detail (not a bare badge).
    assert all(m.get("per_item") for m in dataset_rows)


def test_demo_seed_sets_goals(tmp_path) -> None:
    """The demo seed stores per-user macro targets that /goals returns."""
    client, _, _ = _client(tmp_path)
    client.post("/demo/seed", headers=_H)

    goals_resp = client.get("/goals", headers=_H).json()
    by_code = {g["code"]: g["target"] for g in goals_resp["goals"]}
    for code, amount in DEMO_GOALS.items():
        got = by_code.get(code)
        assert got == amount, f"goal {code}: expected {amount}, got {got}"


def test_demo_seed_is_the_runner_day_with_consistent_confidence(tmp_path) -> None:
    """The seed is the marathon-runner persona — it includes the visibly
    under-counted carb meal (the 'big plate of spaghetti'), and every meal's
    confidence is the genuine mean of its eval axes (it adds up)."""
    client, _, _ = _client(tmp_path)
    resp = client.post("/demo/seed", headers=_H).json()
    meals = client.get(f"/history?date={resp['meal_date']}", headers=_H).json()["meals"]

    assert any("spaghetti" in m["text"].lower() for m in meals), (
        "the under-counted spaghetti meal should be seeded"
    )
    for m in meals:
        axes = m.get("axes") or []
        if axes:
            mean = sum(a["score"] for a in axes) / len(axes)
            assert m["confidence"] == pytest.approx(mean, abs=0.01)


def test_demo_seed_populates_learning_state(tmp_path) -> None:
    """The seed pre-loads the learning loop: confirmed datapoints (Input A) and a
    couple of corrections (Input B), so a judge can hit retune immediately."""
    client, _, _ = _client(tmp_path)
    resp = client.post("/demo/seed", headers=_H).json()
    assert resp["confirmations"] >= 3
    assert resp["corrections"] >= 1

    prefs = client.get("/preferences", headers=_H).json()
    assert prefs["confirmations"] == resp["confirmations"]
    assert prefs["corrections"] == resp["corrections"]
    assert prefs["block"] is None  # nothing learned until a retune runs
    # The confirmed meals are exposed (not just a count) so "Your agent" can list
    # them — each carries its asserted calories.
    assert len(prefs["confirmed"]) == resp["confirmations"]
    assert all(c["meal_text"] and c["calories"] > 0 for c in prefs["confirmed"])


def test_demo_seed_persona_loader(tmp_path) -> None:
    """The persona loader swaps the whole demo: the bodybuilder persona loads its
    own visible day, goals, and learning seed, and reports rich persona metadata
    (label + the on-screen under-count) for the explainer modal."""
    client, _, goal_store = _client(tmp_path)
    resp = client.post(
        "/demo/seed", headers=_H, json={"persona": "bodybuilder"}
    ).json()

    persona = resp["persona"]
    assert persona["key"] == "bodybuilder"
    assert "Bodybuilder" in persona["label"]
    # The on-screen under-count is one of the visible meals.
    assert any(persona["hook_meal"] in t for t in persona["meal_texts"])
    assert len(persona["correction_texts"]) == resp["corrections"]

    # Bodybuilder targets (higher protein) replaced the runner defaults.
    assert goal_store.get(_USER)["203"] == 220.0  # protein g

    # The persona's freeform profile is seeded as standing corrector context.
    profile = client.get("/profile", headers=_H).json()["profile_text"]
    assert "bodybuilder" in profile.lower()

    # Re-seeding the runner replaces it cleanly (idempotent across personas).
    again = client.post("/demo/seed", headers=_H, json={"persona": "runner"}).json()
    assert again["persona"]["key"] == "runner"
    day = again["meal_date"]
    texts = {m["text"] for m in client.get(f"/history?date={day}", headers=_H).json()["meals"]}
    assert any("spaghetti" in t.lower() for t in texts)
    assert not any("turkey" in t.lower() for t in texts)  # no bodybuilder meals linger


def test_demo_seed_is_idempotent(tmp_path) -> None:
    """Re-seeding replaces the day rather than appending duplicates.

    Clicking "see it in action" twice should reset to exactly the canned set,
    not stack two copies of every meal.
    """
    client, _, _ = _client(tmp_path)

    client.post("/demo/seed", headers=_H, json={"date": "2026-06-06"})
    resp = client.post("/demo/seed", headers=_H, json={"date": "2026-06-06"}).json()

    hist = client.get(f"/history?date={resp['meal_date']}", headers=_H).json()
    all_texts = [m["text"] for m in hist["meals"]]
    assert len(all_texts) == len(DEMO_MEALS)
    counts = Counter(all_texts)
    for meal in DEMO_MEALS:
        assert counts[meal["text"]] == 1, f"'{meal['text']}' should appear exactly once"


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

    a = client.post("/demo/seed", headers={"X-DietTrace-User": "alice"}).json()
    b = client.post("/demo/seed", headers={"X-DietTrace-User": "bob"}).json()

    alice = client.get(
        f"/history?date={a['meal_date']}", headers={"X-DietTrace-User": "alice"}
    ).json()
    bob = client.get(
        f"/history?date={b['meal_date']}", headers={"X-DietTrace-User": "bob"}
    ).json()
    assert len(alice["meals"]) == len(DEMO_MEALS)
    assert len(bob["meals"]) == len(DEMO_MEALS)


def test_demo_seed_trace_persisted_in_history(tmp_path) -> None:
    """Every seeded meal in /history carries its trace (parse_meal → log_entry)."""
    client, _, _ = _client(tmp_path)
    resp = client.post("/demo/seed", headers=_H).json()

    hist = client.get(f"/history?date={resp['meal_date']}", headers=_H).json()
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


def test_demo_seed_everyday_persona(tmp_path) -> None:
    """The third (generalist) persona — a busy average person eating a bit healthier
    and losing a little weight — loads its own visible day, per-user balanced (not
    athletic) goals, and a learning seed, so a non-athlete judge sees themselves."""
    client, _, goal_store = _client(tmp_path)
    resp = client.post("/demo/seed", headers=_H, json={"persona": "everyday"}).json()

    persona = resp["persona"]
    assert persona["key"] == "everyday"

    # The visible playground meals landed on TODAY.
    day = resp["meal_date"]
    meals = client.get(f"/history?date={day}", headers=_H).json()["meals"]
    assert len(meals) == len(persona["meal_texts"]) > 0
    # The on-screen under-count (an eaten-out portion-creep meal) is one of them.
    assert any(persona["hook_meal"] in t for t in persona["meal_texts"])

    # Per-user goals are the balanced maintenance-minus-small-deficit targets
    # (NOT an athlete's split): a gentle deficit with even macros.
    goals = goal_store.get(_USER)
    assert goals["208"] == 2000.0  # moderate activity, a gentle deficit (recomp)
    assert goals["203"] == 150.0   # enough protein for muscle, not an athlete's split

    # The learning loop is pre-seeded and corrections stay DISJOINT from the
    # held-out confirmations (asserted exhaustively below).
    assert resp["confirmations"] >= 3
    assert resp["corrections"] >= 1
    assert len(persona["correction_texts"]) == resp["corrections"]


def test_everyday_persona_registered_for_picker() -> None:
    """The generalist persona is registered in PERSONAS so the picker (the frontend
    DEMO_PERSONAS) and the SeededModal switcher list it alongside the two athletes."""
    from dietrace.web.demo_seed import EVERYDAY, PERSONAS

    assert "everyday" in PERSONAS
    assert PERSONAS["everyday"] is EVERYDAY
    # Four distinct selectable personas: runner + bodybuilder + everyday generalist
    # + the creator's real dogfooded log.
    assert {"runner", "bodybuilder", "everyday", "creator"} <= set(PERSONAS)


def test_demo_seed_creator_persona(tmp_path) -> None:
    """The creator's-log persona replays a real exported account: every logged meal
    is the visible day, the confirmed meals are the held-out gate set, and the real
    corrections are banked — all deterministic and offline (no Gemini)."""
    from dietrace.web.demo_seed import CREATOR

    client, _, goal_store = _client(tmp_path)
    resp = client.post("/demo/seed", headers=_H, json={"persona": "creator"}).json()

    persona = resp["persona"]
    assert persona["key"] == "creator"
    assert persona["label"] == "The creator's log"

    # The creator's visible day is spread across two days: the first + last meal
    # (his preworkout dates + post-workout whey) land on TODAY, the other five on
    # the PRIOR day, so his log reads like a real two-day window rather than seven
    # meals stacked on one day.
    assert len(CREATOR.meals) == 7
    today = resp["meal_date"]
    prev = resp["dataset_date"]
    today_meals = client.get(f"/history?date={today}", headers=_H).json()["meals"]
    prev_meals = client.get(f"/history?date={prev}", headers=_H).json()["meals"]

    today_texts = {m["text"] for m in today_meals}
    # Exactly the two pinned-to-today meals (index 0 + 6) are on today.
    assert today_texts == {CREATOR.meals[0]["text"], CREATOR.meals[6]["text"]}
    # The other five visible meals are on the prior day (alongside, but distinct
    # from, the two badged held-out dataset-point rows).
    prev_visible = [m for m in prev_meals if not m.get("dataset_point")]
    assert {m["text"] for m in prev_visible} == {
        CREATOR.meals[i]["text"] for i in (1, 2, 3, 4, 5)
    }

    # All seven visible meals are accounted for across the two days.
    assert today_texts | {m["text"] for m in prev_visible} == {
        m["text"] for m in CREATOR.meals
    }

    # The on-screen under-count he corrected is one of the visible meals.
    assert any(persona["hook_meal"] in t for t in persona["meal_texts"])

    # His own real targets replaced the runner defaults.
    assert goal_store.get(_USER)["208"] == 2635.0
    assert goal_store.get(_USER)["203"] == 230.6

    # His confirmed meals are the held-out gate set; his real corrections banked.
    assert resp["confirmations"] == len(CREATOR.confirmations) >= 2
    assert resp["corrections"] == len(persona["correction_texts"]) >= 4

    # His freeform profile is seeded as standing corrector context.
    profile = client.get("/profile", headers=_H).json()["profile_text"]
    assert "lean physique" in profile.lower()


def test_persona_corrections_are_disjoint_from_dataset_points() -> None:
    """A seeded correction must NOT target a held-out dataset point — otherwise the
    corrector learns from a meal it's then graded on (training on the test set), which
    skews the gate and the retune-trigger counts. Keep corrections and dataset points
    disjoint, for every persona."""
    from dietrace.web.demo_seed import PERSONAS

    for persona in PERSONAS.values():
        dataset_meals = {c["meal_text"] for c in persona.confirmations}
        correction_meals = {f["meal_text"] for f in persona.feedback}
        overlap = dataset_meals & correction_meals
        assert not overlap, (
            f"{persona.key}: corrections overlap held-out dataset points "
            f"(training on the test): {overlap}"
        )
