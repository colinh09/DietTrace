"""Macro planning endpoints: POST /macros/plan, POST /macros/save, and the
per-user GET /goals + /analysis behaviour.

All externals (Gemini client) are mocked; no network calls are made.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from dietrace.web.app import create_app
from dietrace.web.feedback import FeedbackStore
from dietrace.web.goal_store import GoalStore
from dietrace.web.memory import SqliteMemory
from dietrace.web.store import MealLogStore
from dietrace.web.trust import TrustStore

# A valid profile whose formula plan passes the macro eval (protein in [1.2, 2.4] g/kg,
# fat fraction in [0.15, 0.40]).  Sedentary male at 80 kg: TDEE ≈ 2099 kcal,
# protein ≈ 157 g → 1.97 g/kg (within bounds), fat ≈ 70 g → 30 % of kcal (OK).
_PROFILE = {
    "age": 30,
    "sex": "male",
    "height_cm": 175.0,
    "weight_kg": 80.0,
    "activity": "sedentary",
    "goal": "maintain",
    "ai_help": False,
}


def _mock_genai_client(
    rationale: str = "personalised plan",
    protein_pct_delta: float = 2.0,
    fat_pct_delta: float = 0.0,
) -> MagicMock:
    """A mock google.genai client whose generate_content returns valid JSON."""
    response = MagicMock()
    response.text = (
        f'{{"rationale": "{rationale}", '
        f'"protein_pct_delta": {protein_pct_delta}, '
        f'"fat_pct_delta": {fat_pct_delta}}}'
    )
    client = MagicMock()
    client.models.generate_content.return_value = response
    return client


def _make_app(tmp_path, goal_store=None, macro_client=None):
    gs = goal_store or GoalStore(tmp_path / "goals.sqlite")
    store = MealLogStore(tmp_path / "log.sqlite")
    app = create_app(
        meal_logger=lambda text, examples=None: {"totals": [], "per_item": []},
        store=store,
        feedback_store=FeedbackStore(tmp_path / "feedback.sqlite"),
        trust_store=TrustStore(tmp_path / "trust.sqlite"),
        goal_store=gs,
        memory=SqliteMemory(tmp_path / "memory.sqlite"),
        feedback_pusher=lambda *a: False,
        tracer_init=lambda name: None,
        macro_client=macro_client,
    )
    return TestClient(app), gs, store


# ---------------------------------------------------------------------------
# POST /macros/plan — preset path
# ---------------------------------------------------------------------------


def test_plan_from_preset_returns_full_plan(tmp_path) -> None:
    client, _, _ = _make_app(tmp_path)
    resp = client.post("/macros/plan", json={"preset": "maintain"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "preset"
    assert set(body["targets"]) >= {"208", "203", "205", "204"}
    assert "rationale" in body
    assert "steps" in body
    assert "clamped" in body
    assert body["eval"] is not None
    assert "score" in body["eval"]
    assert "pass" in body["eval"]


def test_plan_from_all_presets(tmp_path) -> None:
    client, _, _ = _make_app(tmp_path)
    for preset in ("cut", "maintain", "bulk"):
        resp = client.post("/macros/plan", json={"preset": preset})
        assert resp.status_code == 200, f"Preset {preset!r} failed"
        assert resp.json()["source"] == "preset"


def test_plan_preset_eval_present(tmp_path) -> None:
    client, _, _ = _make_app(tmp_path)
    body = client.post("/macros/plan", json={"preset": "cut"}).json()
    ev = body["eval"]
    assert ev is not None
    assert isinstance(ev["score"], float)
    assert isinstance(ev["pass"], bool)
    assert "consistency" in ev
    assert "safety" in ev


# ---------------------------------------------------------------------------
# POST /macros/plan — profile path (no ai_help)
# ---------------------------------------------------------------------------


def test_plan_from_profile_formula_source(tmp_path) -> None:
    client, _, _ = _make_app(tmp_path)
    resp = client.post("/macros/plan", json=_PROFILE)
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "formula"
    assert "208" in body["targets"]
    assert body["eval"] is not None


def test_plan_profile_eval_passes_for_clean_plan(tmp_path) -> None:
    client, _, _ = _make_app(tmp_path)
    body = client.post("/macros/plan", json=_PROFILE).json()
    assert body["eval"]["pass"] is True


def test_plan_profile_steps_present(tmp_path) -> None:
    client, _, _ = _make_app(tmp_path)
    body = client.post("/macros/plan", json=_PROFILE).json()
    step_names = [s["step"] for s in body["steps"]]
    assert "bmr" in step_names
    assert "tdee" in step_names
    assert "split" in step_names


# ---------------------------------------------------------------------------
# POST /macros/plan — profile path (with ai_help, mocked client)
# ---------------------------------------------------------------------------


def test_plan_ai_help_returns_ai_source(tmp_path) -> None:
    mock_client = _mock_genai_client()
    client, _, _ = _make_app(tmp_path, macro_client=mock_client)
    profile = dict(_PROFILE, ai_help=True)
    resp = client.post("/macros/plan", json=profile)
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "ai"
    assert body["eval"] is not None


def test_plan_ai_help_eval_present(tmp_path) -> None:
    mock_client = _mock_genai_client()
    client, _, _ = _make_app(tmp_path, macro_client=mock_client)
    body = client.post("/macros/plan", json=dict(_PROFILE, ai_help=True)).json()
    ev = body["eval"]
    assert ev is not None
    assert "score" in ev and "pass" in ev


def test_plan_ai_help_soft_fallback_on_client_error(tmp_path) -> None:
    error_client = MagicMock()
    error_client.models.generate_content.side_effect = RuntimeError("Vertex unavailable")
    client, _, _ = _make_app(tmp_path, macro_client=error_client)
    body = client.post("/macros/plan", json=dict(_PROFILE, ai_help=True)).json()
    assert body["source"] == "formula"
    assert body["eval"] is not None


# ---------------------------------------------------------------------------
# POST /macros/plan — does NOT persist
# ---------------------------------------------------------------------------


def test_plan_does_not_persist_profile_or_targets(tmp_path) -> None:
    client, gs, _ = _make_app(tmp_path)
    client.post(
        "/macros/plan",
        json=_PROFILE,
        headers={"X-DietTrace-User": "alice"},
    )
    assert gs.get("alice") is None


def test_plan_preset_does_not_persist(tmp_path) -> None:
    client, gs, _ = _make_app(tmp_path)
    client.post(
        "/macros/plan",
        json={"preset": "bulk"},
        headers={"X-DietTrace-User": "alice"},
    )
    assert gs.get("alice") is None


# ---------------------------------------------------------------------------
# POST /macros/save — persists only targets
# ---------------------------------------------------------------------------


_TARGETS: dict[str, float] = {
    "208": 2200.0,
    "203": 165.0,
    "205": 220.0,
    "204": 73.0,
}


def test_save_persists_targets(tmp_path) -> None:
    client, gs, _ = _make_app(tmp_path)
    resp = client.post(
        "/macros/save",
        json={"targets": _TARGETS},
        headers={"X-DietTrace-User": "alice"},
    )
    assert resp.status_code == 200
    assert gs.get("alice") == _TARGETS


def test_save_per_user_isolation(tmp_path) -> None:
    client, gs, _ = _make_app(tmp_path)
    alice_targets = {"208": 1800.0, "203": 140.0, "205": 180.0, "204": 60.0}
    bob_targets = {"208": 2600.0, "203": 195.0, "205": 260.0, "204": 87.0}
    client.post(
        "/macros/save",
        json={"targets": alice_targets},
        headers={"X-DietTrace-User": "alice"},
    )
    client.post(
        "/macros/save",
        json={"targets": bob_targets},
        headers={"X-DietTrace-User": "bob"},
    )
    assert gs.get("alice") == alice_targets
    assert gs.get("bob") == bob_targets


def test_save_then_goals_shows_saved_targets(tmp_path) -> None:
    client, _, _ = _make_app(tmp_path)
    targets = {"208": 1800.0, "203": 140.0, "205": 180.0, "204": 60.0}
    client.post(
        "/macros/save",
        json={"targets": targets},
        headers={"X-DietTrace-User": "alice"},
    )
    resp = client.get("/goals", headers={"X-DietTrace-User": "alice"})
    goals = resp.json()["goals"]
    by_code = {g["code"]: g for g in goals}
    assert by_code["208"]["target"] == 1800.0
    assert by_code["203"]["target"] == 140.0


# ---------------------------------------------------------------------------
# GET /goals — per-user (saved overrides default, fallback when not set)
# ---------------------------------------------------------------------------


def test_goals_saved_overrides_default(tmp_path) -> None:
    client, gs, _ = _make_app(tmp_path)
    gs.save("alice", {"208": 1500.0, "203": 100.0, "205": 150.0, "204": 50.0})
    resp = client.get("/goals", headers={"X-DietTrace-User": "alice"})
    goals = resp.json()["goals"]
    by_code = {g["code"]: g for g in goals}
    assert by_code["208"]["target"] == 1500.0


def test_goals_fallback_to_default_when_none_saved(tmp_path) -> None:
    client, _, _ = _make_app(tmp_path)
    resp = client.get("/goals", headers={"X-DietTrace-User": "nobody"})
    goals = resp.json()["goals"]
    by_code = {g["code"]: g for g in goals}
    # Default energy goal is 2000 kcal.
    assert by_code["208"]["target"] == 2000.0


def test_goals_two_users_see_different_targets(tmp_path) -> None:
    client, gs, _ = _make_app(tmp_path)
    gs.save("alice", {"208": 1500.0, "203": 100.0, "205": 150.0, "204": 50.0})
    gs.save("bob", {"208": 2700.0, "203": 200.0, "205": 270.0, "204": 90.0})

    alice = {g["code"]: g for g in client.get(
        "/goals", headers={"X-DietTrace-User": "alice"}
    ).json()["goals"]}
    bob = {g["code"]: g for g in client.get(
        "/goals", headers={"X-DietTrace-User": "bob"}
    ).json()["goals"]}

    assert alice["208"]["target"] == 1500.0
    assert bob["208"]["target"] == 2700.0


def test_goals_saved_response_has_name_and_unit(tmp_path) -> None:
    client, gs, _ = _make_app(tmp_path)
    gs.save("alice", {"208": 1800.0, "203": 140.0, "205": 180.0, "204": 60.0})
    goals = client.get("/goals", headers={"X-DietTrace-User": "alice"}).json()["goals"]
    for g in goals:
        assert "name" in g and g["name"]
        assert "unit" in g and g["unit"]
        assert "target" in g
        assert "code" in g


# ---------------------------------------------------------------------------
# /analysis — honors saved targets
# ---------------------------------------------------------------------------


def test_analysis_honors_saved_targets(tmp_path) -> None:
    client, gs, store = _make_app(tmp_path)
    gs.save("alice", {"208": 1500.0, "203": 100.0, "205": 150.0, "204": 50.0})
    store.add(
        "a meal",
        [{"code": "208", "name": "Energy", "amount": 300.0, "unit": "kcal"}],
        user_id="alice",
    )
    body = client.get("/analysis", headers={"X-DietTrace-User": "alice"}).json()
    energy = next(g for g in body["goals"] if g["code"] == "208")
    assert energy["target"] == 1500.0
    assert energy["consumed"] == 300.0
    assert energy["remaining"] == 1200.0


def test_analysis_uses_default_when_no_saved_targets(tmp_path) -> None:
    client, _, _ = _make_app(tmp_path)
    body = client.get("/analysis", headers={"X-DietTrace-User": "nobody"}).json()
    energy = next(g for g in body["goals"] if g["code"] == "208")
    # Default energy target is 2000 kcal.
    assert energy["target"] == 2000.0


# ---------------------------------------------------------------------------
# Edge cases / error paths
# ---------------------------------------------------------------------------


def test_plan_missing_profile_fields_returns_422(tmp_path) -> None:
    client, _, _ = _make_app(tmp_path)
    # Empty body with no preset and no profile fields → 422, not 500.
    resp = client.post("/macros/plan", json={})
    assert resp.status_code == 422


def test_plan_unknown_preset_returns_422(tmp_path) -> None:
    client, _, _ = _make_app(tmp_path)
    resp = client.post("/macros/plan", json={"preset": "nonexistent"})
    assert resp.status_code == 422


def test_save_returns_503_when_goal_store_not_configured(tmp_path) -> None:
    # When the app is built without a goal_store (goals_db=None), /macros/save
    # must return 503, not crash with AttributeError.
    from dietrace.web.app import create_app
    from dietrace.web.feedback import FeedbackStore
    from dietrace.web.memory import SqliteMemory
    from dietrace.web.store import MealLogStore
    from dietrace.web.trust import TrustStore

    app = create_app(
        meal_logger=lambda text, examples=None: {"totals": [], "per_item": []},
        store=MealLogStore(tmp_path / "log.sqlite"),
        feedback_store=FeedbackStore(tmp_path / "feedback.sqlite"),
        trust_store=TrustStore(tmp_path / "trust.sqlite"),
        goal_store=None,
        memory=SqliteMemory(tmp_path / "memory.sqlite"),
        feedback_pusher=lambda *a: False,
        tracer_init=lambda name: None,
    )
    client = TestClient(app)
    resp = client.post(
        "/macros/save",
        json={"targets": {"208": 2000.0, "203": 150.0, "205": 200.0, "204": 67.0}},
    )
    assert resp.status_code == 503


def test_analysis_different_users_see_their_own_targets(tmp_path) -> None:
    client, gs, store = _make_app(tmp_path)
    gs.save("alice", {"208": 1400.0, "203": 110.0, "205": 140.0, "204": 47.0})
    # bob has no saved targets → uses default

    alice_body = client.get("/analysis", headers={"X-DietTrace-User": "alice"}).json()
    bob_body = client.get("/analysis", headers={"X-DietTrace-User": "bob"}).json()

    alice_energy = next(g for g in alice_body["goals"] if g["code"] == "208")
    bob_energy = next(g for g in bob_body["goals"] if g["code"] == "208")

    assert alice_energy["target"] == 1400.0
    assert bob_energy["target"] == 2000.0  # default
