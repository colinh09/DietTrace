"""POST /feedback/freeform — wire interpret_feedback into an endpoint (14.12).

Tests assert the three done criteria:
1. The meal's totals + per_item are updated after feedback (portion_adjust / remove_item).
2. A standing_rule preference is stored per-user and the response surfaces it.
3. The response always includes kind / target_food / adjustment / rationale (visible
   adaptation), plus the updated per_item and totals so the UI can refresh in-place.

All externals (Gemini, Phoenix) are mocked; the no-network guard in conftest.py
stays intact.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from dietrace.web.app import create_app
from dietrace.web.feedback import FeedbackStore
from dietrace.web.memory import SqliteMemory
from dietrace.web.standing_rules import SqliteStandingRuleStore, StandingRule
from dietrace.web.store import MealLogStore
from dietrace.web.trust import TrustStore

# A fries meal: 300 g, 400 kcal / 4 P / 20 F / 50 C.
_FRIES_NUTRIENTS = [
    {"code": "208", "name": "Energy", "amount": 400.0, "unit": "kcal"},
    {"code": "203", "name": "Protein", "amount": 4.0, "unit": "g"},
    {"code": "204", "name": "Total lipid (fat)", "amount": 20.0, "unit": "g"},
    {"code": "205", "name": "Carbohydrate", "amount": 50.0, "unit": "g"},
]
_FRIES_ITEM = {
    "description": "french fries",
    "fdc_id": 1001,
    "grams": 300.0,
    "nutrients": _FRIES_NUTRIENTS,
}
_TOTALS = [
    {"code": "208", "name": "Energy", "amount": 400.0, "unit": "kcal"},
    {"code": "203", "name": "Protein", "amount": 4.0, "unit": "g"},
    {"code": "204", "name": "Total lipid (fat)", "amount": 20.0, "unit": "g"},
    {"code": "205", "name": "Carbohydrate", "amount": 50.0, "unit": "g"},
]
_DETAIL = {
    "per_item": [_FRIES_ITEM],
    "trace": [],
    "confidence": 0.9,
    "reasons": [],
    "axes": [],
    "needs_review": False,
    "review_reason": None,
}


def _mock_gemini(
    kind: str,
    target_food: str,
    adjustment: float | None,
    scope: str,
    rationale: str,
) -> Mock:
    payload = json.dumps(
        {
            "kind": kind,
            "target_food": target_food,
            "adjustment": adjustment,
            "scope": scope,
            "rationale": rationale,
        }
    )
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(text=payload)
    return client


def _make_app(
    tmp_path,
    *,
    freeform_client: Mock | None = None,
    pusher=lambda *a: False,
):
    store = MealLogStore(tmp_path / "log.sqlite")
    rules = SqliteStandingRuleStore(tmp_path / "rules.sqlite")
    app = create_app(
        meal_logger=lambda text, examples=None: {
            "totals": _TOTALS,
            "per_item": [_FRIES_ITEM],
        },
        store=store,
        feedback_store=FeedbackStore(tmp_path / "feedback.sqlite"),
        trust_store=TrustStore(tmp_path / "trust.sqlite"),
        memory=SqliteMemory(tmp_path / "memory.sqlite"),
        standing_rule_store=rules,
        freeform_client=freeform_client,
        feedback_pusher=pusher,
        tracer_init=lambda name: None,
    )
    return TestClient(app), store, rules


# ---------------------------------------------------------------------------
# Meal update: stored totals and per_item are rewritten
# ---------------------------------------------------------------------------


def test_portion_adjust_updates_stored_meal_totals(tmp_path) -> None:
    """After portion_adjust, the stored meal's kcal is halved in place."""
    client, store, _ = _make_app(
        tmp_path,
        freeform_client=_mock_gemini(
            "portion_adjust", "french fries", 0.5, "this_food", "half portion"
        ),
    )
    meal_id = store.add("fries", _TOTALS, detail=_DETAIL)

    resp = client.post(
        "/feedback/freeform",
        json={
            "meal_id": meal_id,
            "meal_text": "fries",
            "feedback_text": "fries were half that size",
            "current_items": [_FRIES_ITEM],
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["applied"] is True

    # Store should carry the halved totals.
    meals = store.list()
    kcal = next(t["amount"] for t in meals[0]["totals"] if t["code"] == "208")
    assert kcal == pytest.approx(200.0, abs=0.5)


def test_remove_item_updates_stored_meal(tmp_path) -> None:
    """After remove_item, the stored meal's per_item loses the removed food."""
    client, store, _ = _make_app(
        tmp_path,
        freeform_client=_mock_gemini(
            "remove_item", "french fries", None, "this_food", "didn't eat fries"
        ),
    )
    meal_id = store.add("fries", _TOTALS, detail=_DETAIL)

    resp = client.post(
        "/feedback/freeform",
        json={
            "meal_id": meal_id,
            "meal_text": "fries",
            "feedback_text": "actually no fries",
            "current_items": [_FRIES_ITEM],
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["applied"] is True
    assert body["kind"] == "remove_item"
    assert len(body["per_item"]) == 0


# ---------------------------------------------------------------------------
# Standing rule: stored as a per-user preference
# ---------------------------------------------------------------------------


def test_standing_rule_is_stored_as_preference(tmp_path) -> None:
    """standing_rule feedback persists to the standing-rule store, not the meal."""
    client, store, rules = _make_app(
        tmp_path,
        freeform_client=_mock_gemini(
            "standing_rule",
            "preworkout",
            80.0,
            "meal_type",
            "preworkout aim 80g carbs",
        ),
    )
    meal_id = store.add("fries", _TOTALS, detail=_DETAIL)

    resp = client.post(
        "/feedback/freeform",
        json={
            "meal_id": meal_id,
            "meal_text": "fries",
            "feedback_text": "from now on this is my preworkout, aim for 80g carbs",
            "current_items": [_FRIES_ITEM],
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stored_as_preference"] is True
    assert body["kind"] == "standing_rule"

    # The standing-rule store must carry the preference.
    assert rules.count("demo") == 1
    rule = rules.recall("demo", "meal_type", "preworkout")
    assert rule is not None
    assert rule.adjustment == pytest.approx(80.0)
    assert "carbs" in rule.rationale

    # The stored meal's totals must NOT have been modified (standing_rule doesn't touch the meal).
    meals = store.list()
    stored_kcal = next(t["amount"] for t in meals[0]["totals"] if t["code"] == "208")
    assert stored_kcal == pytest.approx(400.0, abs=0.5)


# ---------------------------------------------------------------------------
# Visible adaptation: the response surfaces what was learned
# ---------------------------------------------------------------------------


def test_response_surfaces_learned_adaptation(tmp_path) -> None:
    """The response includes kind, target_food, adjustment, and rationale — visible."""
    client, store, _ = _make_app(
        tmp_path,
        freeform_client=_mock_gemini(
            "portion_adjust", "french fries", 0.5, "this_food", "user eats half"
        ),
    )
    meal_id = store.add("fries", _TOTALS, detail=_DETAIL)

    resp = client.post(
        "/feedback/freeform",
        json={
            "meal_id": meal_id,
            "meal_text": "fries",
            "feedback_text": "half the fries",
            "current_items": [_FRIES_ITEM],
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "portion_adjust"
    assert body["target_food"] == "french fries"
    assert body["adjustment"] == pytest.approx(0.5)
    assert body["rationale"] == "user eats half"


# ---------------------------------------------------------------------------
# Analysis reflects the update after feedback
# ---------------------------------------------------------------------------


def test_analysis_reflects_updated_totals_after_feedback(tmp_path) -> None:
    """After freeform feedback halves a meal, /analysis shows half the calories."""
    client, store, _ = _make_app(
        tmp_path,
        freeform_client=_mock_gemini(
            "portion_adjust", "french fries", 0.5, "this_food", "half"
        ),
    )

    log_resp = client.post("/log", json={"text": "fries"})
    assert log_resp.status_code == 200
    meal_id = log_resp.json()["id"]

    before = client.get("/analysis").json()
    kcal_before = next(g["consumed"] for g in before["goals"] if g["code"] == "208")
    assert kcal_before == pytest.approx(400.0, abs=1.0)

    client.post(
        "/feedback/freeform",
        json={
            "meal_id": meal_id,
            "meal_text": "fries",
            "feedback_text": "half the fries",
            "current_items": [_FRIES_ITEM],
        },
    )

    after = client.get("/analysis").json()
    kcal_after = next(g["consumed"] for g in after["goals"] if g["code"] == "208")
    assert kcal_after == pytest.approx(200.0, abs=1.0)


# ---------------------------------------------------------------------------
# GET /feedback/standing-rules — returns stored rules for the user
# ---------------------------------------------------------------------------


def test_get_standing_rules_returns_stored_rules(tmp_path) -> None:
    """GET /feedback/standing-rules returns the user's standing preferences."""
    client, store, _ = _make_app(
        tmp_path,
        freeform_client=_mock_gemini(
            "standing_rule",
            "preworkout",
            80.0,
            "meal_type",
            "preworkout aim 80g carbs",
        ),
    )
    meal_id = store.add("fries", _TOTALS, detail=_DETAIL)

    client.post(
        "/feedback/freeform",
        json={
            "meal_id": meal_id,
            "meal_text": "fries",
            "feedback_text": "from now on preworkout aim 80g carbs",
            "current_items": [_FRIES_ITEM],
        },
    )

    resp = client.get("/feedback/standing-rules")
    assert resp.status_code == 200
    body = resp.json()
    assert "rules" in body
    assert len(body["rules"]) == 1
    assert body["rules"][0]["scope"] == "meal_type"
    assert body["rules"][0]["target_food"] == "preworkout"
    assert body["rules"][0]["adjustment"] == pytest.approx(80.0)


# ---------------------------------------------------------------------------
# Fail-soft: no crash when interpretation returns None
# ---------------------------------------------------------------------------


def test_interpret_failure_returns_graceful_error(tmp_path) -> None:
    """When Gemini returns garbage, the endpoint returns ok=False without crashing."""
    bad_client = Mock()
    bad_client.models.generate_content.return_value = SimpleNamespace(text="not json at all")

    client, store, _ = _make_app(tmp_path, freeform_client=bad_client)
    meal_id = store.add("fries", _TOTALS, detail=_DETAIL)

    resp = client.post(
        "/feedback/freeform",
        json={
            "meal_id": meal_id,
            "meal_text": "fries",
            "feedback_text": "half",
            "current_items": [_FRIES_ITEM],
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["applied"] is False


# ---------------------------------------------------------------------------
# Recall round-trip: a stored standing rule reaches a FUTURE log (real adaptation)
# ---------------------------------------------------------------------------


def test_standing_rule_is_recalled_into_a_later_log(tmp_path):
    """A stored standing rule is injected into the parse context on a later /log
    for that user — proving the rule actually shapes future meals (not just stored)."""
    captured: dict = {}

    def capturing_logger(text, examples=None):
        captured["examples"] = examples
        return {"totals": _TOTALS, "per_item": [_FRIES_ITEM]}

    rules = SqliteStandingRuleStore(tmp_path / "rules.sqlite")
    rules.remember(
        "alice",
        StandingRule(
            scope="meal_type",
            target_food="preworkout",
            adjustment=80.0,
            rationale="preworkout meals aim for 80g carbs",
        ),
    )
    app = create_app(
        meal_logger=capturing_logger,
        store=MealLogStore(tmp_path / "log.sqlite"),
        feedback_store=FeedbackStore(tmp_path / "feedback.sqlite"),
        trust_store=TrustStore(tmp_path / "trust.sqlite"),
        memory=SqliteMemory(tmp_path / "memory.sqlite"),
        standing_rule_store=rules,
        feedback_pusher=lambda *a: False,
        tracer_init=lambda name: None,
    )
    client = TestClient(app)

    # alice (has a rule) → the rule rides her parse context.
    resp = client.post(
        "/log", json={"text": "a banana"}, headers={"X-DietTrace-User": "alice"}
    )
    assert resp.status_code == 200
    assert any(
        e.get("rule") == "preworkout meals aim for 80g carbs"
        for e in captured["examples"]
    ), captured["examples"]

    # bob (no rules) → no rule context (per-user isolation).
    captured.clear()
    client.post("/log", json={"text": "a banana"}, headers={"X-DietTrace-User": "bob"})
    assert not any(e.get("rule") for e in captured["examples"])
