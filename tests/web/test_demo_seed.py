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


def test_demo_seed_today_empty_meals_spread_dataset_on_older_day(tmp_path) -> None:
    """Today (offset 0) is EMPTY — the judge logs their own first meal there. The
    persona's visible meals are spread across yesterday (day 1) AND two-days-ago
    (day 2), roughly half each (not crammed onto one day). The held-out dataset
    rows live on the older day (day 2), badged but never hidden."""
    client, _, _ = _client(tmp_path)
    resp = client.post("/demo/seed", headers=_H, json={"date": "2026-06-07"}).json()
    assert resp["meal_date"] == "2026-06-07"  # today — left clean
    assert resp["dataset_date"] == "2026-06-05"  # older day (today − 2)

    # Today is empty.
    today = client.get("/history?date=2026-06-07", headers=_H).json()["meals"]
    assert today == []

    day1 = client.get("/history?date=2026-06-06", headers=_H).json()["meals"]
    day2 = client.get("/history?date=2026-06-05", headers=_H).json()["meals"]

    # The persona's visible playground meals are spread across BOTH prior days —
    # each day carries some of them, so neither is crammed and neither is empty.
    want = {m["text"] for m in DEMO_MEALS}
    day1_persona = {m["text"] for m in day1 if not m.get("dataset_point")} & want
    day2_persona = {m["text"] for m in day2 if not m.get("dataset_point")} & want
    assert day1_persona, "day 1 should carry some of the persona's visible meals"
    assert day2_persona, "day 2 should carry some of the persona's visible meals"
    assert day1_persona | day2_persona == want  # all accounted for across the two days

    # The dataset-point rows all sit on the older day (day 2), flagged + matching
    # the held-out set, and carry full per-item detail (not a bare badge).
    assert not any(m.get("dataset_point") for m in day1)
    dataset_rows = [m for m in day2 if m.get("dataset_point")]
    assert len(dataset_rows) == resp["confirmations"]
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
    resp = client.post("/demo/seed", headers=_H, json={"date": "2026-06-07"}).json()
    # The visible meals are spread across the two prior days (today is empty).
    day1 = client.get("/history?date=2026-06-06", headers=_H).json()["meals"]
    day2 = client.get("/history?date=2026-06-05", headers=_H).json()["meals"]
    meals = day1 + day2

    assert any("spaghetti" in m["text"].lower() for m in meals), (
        "the under-counted spaghetti meal should be seeded"
    )
    # meals_logged counts ALL real logged meals = the visible days (6) + the prior
    # day's non-dataset-point meals (4), distinct from the held-out confirmations.
    assert resp["persona"]["meals_logged"] == 10
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
    again = client.post(
        "/demo/seed", headers=_H, json={"persona": "runner", "date": "2026-06-07"}
    ).json()
    assert again["persona"]["key"] == "runner"
    # Today is empty; the runner's meals are on the two prior days.
    assert client.get("/history?date=2026-06-07", headers=_H).json()["meals"] == []
    texts = {
        m["text"]
        for d in ("2026-06-06", "2026-06-05")
        for m in client.get(f"/history?date={d}", headers=_H).json()["meals"]
    }
    assert any("spaghetti" in t.lower() for t in texts)
    # No bodybuilder-only meals linger ("whey"/"sausage" appear only in his seed).
    assert not any("whey" in t.lower() or "sausage" in t.lower() for t in texts)


def test_demo_seed_is_idempotent(tmp_path) -> None:
    """Re-seeding replaces the day rather than appending duplicates.

    Clicking "see it in action" twice should reset to exactly the canned set,
    not stack two copies of every meal.
    """
    client, _, _ = _client(tmp_path)

    client.post("/demo/seed", headers=_H, json={"date": "2026-06-07"})
    client.post("/demo/seed", headers=_H, json={"date": "2026-06-07"})

    # Across the two prior days each visible persona meal appears exactly once
    # (re-seeding replaces the day, never stacks duplicates).
    counts = Counter(
        m["text"]
        for d in ("2026-06-06", "2026-06-05")
        for m in client.get(f"/history?date={d}", headers=_H).json()["meals"]
        if not m.get("dataset_point")
    )
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

    client.post(
        "/demo/seed", headers={"X-DietTrace-User": "alice"}, json={"date": "2026-06-07"}
    )
    client.post(
        "/demo/seed", headers={"X-DietTrace-User": "bob"}, json={"date": "2026-06-07"}
    )

    def visible_texts(uid: str) -> set:
        return {
            m["text"]
            for d in ("2026-06-06", "2026-06-05")
            for m in client.get(
                f"/history?date={d}", headers={"X-DietTrace-User": uid}
            ).json()["meals"]
            if not m.get("dataset_point")
        }

    want = {m["text"] for m in DEMO_MEALS}
    assert want <= visible_texts("alice")
    assert want <= visible_texts("bob")


def test_demo_seed_trace_persisted_in_history(tmp_path) -> None:
    """Every seeded meal in /history carries its trace (parse_meal → log_entry)."""
    client, _, _ = _client(tmp_path)
    client.post("/demo/seed", headers=_H, json={"date": "2026-06-07"}).json()

    meals = [
        m
        for d in ("2026-06-06", "2026-06-05")
        for m in client.get(f"/history?date={d}", headers=_H).json()["meals"]
    ]
    for meal in meals:
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


def test_only_two_athletes_selectable_everyday_creator_archived() -> None:
    """Only the runner + bodybuilder are selectable; the everyday + creator personas
    are archived — kept defined (so they can be restored) but out of PERSONAS, hence
    out of the picker (the frontend DEMO_PERSONAS) and the SeededModal switcher."""
    from dietrace.web.demo_seed import (
        ARCHIVED_PERSONAS,
        BODYBUILDER,
        CREATOR,
        EVERYDAY,
        PERSONAS,
        RUNNER,
    )

    assert set(PERSONAS) == {"runner", "bodybuilder"}
    assert PERSONAS["runner"] is RUNNER
    assert PERSONAS["bodybuilder"] is BODYBUILDER
    # The archived personas are still DEFINED and retained (not deleted).
    assert "everyday" not in PERSONAS and "creator" not in PERSONAS
    assert ARCHIVED_PERSONAS == {"everyday": EVERYDAY, "creator": CREATOR}


def test_archived_persona_definitions_and_files_retained() -> None:
    """The archived personas keep their Persona definitions AND their JSON files, so
    they can be restored by moving them back into PERSONAS — nothing was deleted."""
    from pathlib import Path

    import dietrace.web.demo_seed as ds

    assert ds.EVERYDAY.meals and ds.EVERYDAY.confirmations and ds.EVERYDAY.feedback
    assert ds.CREATOR.meals and ds.CREATOR.confirmations and ds.CREATOR.feedback
    seed_dir = Path(ds.__file__).parent
    assert (seed_dir / "demo_seed_everyday.json").exists()
    assert (seed_dir / "demo_seed_creator.json").exists()


@pytest.mark.parametrize("persona_key", ["runner", "bodybuilder"])
def test_feedback_meals_are_visible_and_badged(tmp_path, persona_key) -> None:
    """Each banked correction's meal is ALSO logged as a visible meal (using the
    same feedback meal_text), spread across the two prior days. /history badges it
    has_feedback by TEXT-MATCH against the banked feedback, so it renders the
    feedback review state with no frontend change."""
    from dietrace.web.demo_seed import PERSONAS

    client, _, _ = _client(tmp_path)
    client.post(
        "/demo/seed", headers=_H, json={"persona": persona_key, "date": "2026-06-07"}
    )

    visible = [
        m
        for d in ("2026-06-06", "2026-06-05")
        for m in client.get(f"/history?date={d}", headers=_H).json()["meals"]
        if not m.get("dataset_point")
    ]
    by_text = {m["text"]: m for m in visible}

    feedback_texts = [f["meal_text"] for f in PERSONAS[persona_key].feedback]
    assert feedback_texts, "persona should have banked feedback"
    for ft in feedback_texts:
        assert ft in by_text, f"feedback meal '{ft}' is not a visible logged meal"
        meal = by_text[ft]
        assert meal.get("has_feedback") is True, f"'{ft}' should be badged has_feedback"
        # The under-count is real agent output carried into the seed (per-item + trace).
        assert meal.get("per_item"), f"'{ft}' should carry its captured per-item panel"
        assert meal.get("trace"), f"'{ft}' should carry its captured trace"


def test_persona_corrections_are_disjoint_from_dataset_points() -> None:
    """A seeded correction must NOT target a held-out dataset point — otherwise the
    corrector learns from a meal it's then graded on (training on the test set), which
    skews the gate and the retune-trigger counts. Keep corrections and dataset points
    disjoint, for every persona."""
    from dietrace.web.demo_seed import ARCHIVED_PERSONAS, PERSONAS

    for persona in (*PERSONAS.values(), *ARCHIVED_PERSONAS.values()):
        dataset_meals = {c["meal_text"] for c in persona.confirmations}
        correction_meals = {f["meal_text"] for f in persona.feedback}
        overlap = dataset_meals & correction_meals
        assert not overlap, (
            f"{persona.key}: corrections overlap held-out dataset points "
            f"(training on the test): {overlap}"
        )
