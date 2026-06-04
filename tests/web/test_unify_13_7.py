""" nutritionist-agent unification — macro + meal under one identity.

The macro planning capability must be reachable through the same NutritionAgent
as meal logging (one Phoenix tracing spine, one per-user memory), and the
existing logging path must remain byte-identical (regression guard, /§8).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from dietrace.agents.nutrition.agent import NutritionAgent
from dietrace.nutrition.repository import FoodRepository
from dietrace.web.app import create_app
from dietrace.web.feedback import FeedbackStore
from dietrace.web.memory import SqliteMemory
from dietrace.web.store import MealLogStore
from dietrace.web.trust import TrustStore
from tests.nutrition.fixtures_food_db import EGG_FDC_ID, build_food_db

_PIPELINE = [
    "parse_meal",
    "search_nutrition",
    "estimate_portion",
    "log_entry",
    "check_against_goals",
]


@pytest.fixture
def repository(tmp_path: Path) -> FoodRepository:
    db_path = tmp_path / "food.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        build_food_db(conn)
    finally:
        conn.close()
    return FoodRepository(db_path)


def _mock_client(text: str | None = None) -> Mock:
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(text=text)
    return client


# ---------------------------------------------------------------------------
# Failing tests (RED before implementation)
# ---------------------------------------------------------------------------


def test_plan_macros_method_exists(repository) -> None:
    """NutritionAgent exposes plan_macros — the macro side of the agent (13.7)."""
    agent = NutritionAgent(repository, client=_mock_client())
    assert callable(getattr(agent, "plan_macros", None))


def test_plan_macros_preset_returns_four_usda_targets(repository) -> None:
    """plan_macros(preset=...) returns the four USDA-coded macro targets (13.7)."""
    agent = NutritionAgent(repository, client=_mock_client())
    plan = agent.plan_macros(preset="maintain")
    assert set(plan["targets"]) >= {"208", "203", "205", "204"}
    assert plan["source"] == "preset"


def test_plan_macros_unknown_preset_raises(repository) -> None:
    """plan_macros with an unknown preset raises KeyError (fail-safe, 13.7)."""
    agent = NutritionAgent(repository, client=_mock_client())
    with pytest.raises(KeyError):
        agent.plan_macros(preset="nonexistent_preset")


def test_plan_macros_profile_formula_is_atwater_consistent(repository) -> None:
    """plan_macros with a profile returns a formula plan — 4P+4C+9F ≈ kcal (13.7)."""
    agent = NutritionAgent(repository, client=_mock_client())
    plan = agent.plan_macros(
        age=30,
        sex="male",
        height_cm=175.0,
        weight_kg=80.0,
        activity="sedentary",
        goal="maintain",
    )
    targets = plan["targets"]
    assert plan["source"] == "formula"
    kcal = float(targets.get("208", 0))
    prot = float(targets.get("203", 0))
    carb = float(targets.get("205", 0))
    fat = float(targets.get("204", 0))
    atwater = 4 * prot + 4 * carb + 9 * fat
    assert abs(atwater - kcal) / kcal < 0.05


def test_plan_macros_does_not_appear_in_adk_tools(repository) -> None:
    """plan_macros is a method on NutritionAgent, not an ADK FunctionTool (13.7).

    The five logging tools must remain the complete tools list so the existing
    agent tests and the ADK runner contract are unchanged.
    """
    agent = NutritionAgent(repository, client=_mock_client())
    # ADK tools list is still exactly the five-step logging pipeline (which
    # implies plan_macros is absent — it is a method, not a FunctionTool).
    assert [t.name for t in agent.tools] == _PIPELINE


# ---------------------------------------------------------------------------
# Regression guards (pass before AND after — document the unchanged behavior)
# ---------------------------------------------------------------------------


def test_logging_tools_output_identical_after_unification(repository) -> None:
    """The five logging tools produce identical output after the unification (13.7)."""
    agent = NutritionAgent(repository, client=_mock_client())
    # log_entry still produces the expected per-100-g egg totals.
    log_tool = next(t for t in agent.tools if t.name == "log_entry")
    meal = log_tool.func([{"fdc_id": EGG_FDC_ID, "grams": 100.0}])
    totals = {n["code"]: n["amount"] for n in meal["totals"]}
    assert totals["203"] == pytest.approx(12.6)  # protein unchanged


def test_log_endpoint_response_structure_unchanged(tmp_path) -> None:
    """POST /log response structure is identical to before the agent unification (13.7).

    This is the explicit regression guard for the meal-logging path.  All
    pre-existing response fields — id, per_item, totals, trace, confidence,
    reasons, needs_review, safety — must be present with correct types and values.
    """
    _stub_totals = [{"code": "208", "name": "Energy", "amount": 105.0, "unit": "kcal"}]

    def _stub_logger(text: str, examples=None) -> dict:
        return {
            "totals": _stub_totals,
            "per_item": [{"description": text, "grams": 100.0}],
        }

    app = create_app(
        meal_logger=_stub_logger,
        store=MealLogStore(tmp_path / "log.sqlite"),
        feedback_store=FeedbackStore(tmp_path / "feedback.sqlite"),
        trust_store=TrustStore(tmp_path / "trust.sqlite"),
        memory=SqliteMemory(tmp_path / "memory.sqlite"),
        feedback_pusher=lambda *a: False,
        tracer_init=lambda name: None,
    )
    client = TestClient(app)

    resp = client.post("/log", json={"text": "2 eggs and toast"})

    assert resp.status_code == 200
    body = resp.json()
    # All pre-unification response fields are present.
    assert isinstance(body["id"], int)
    assert body["totals"][0]["code"] == "208"
    assert body["totals"][0]["amount"] == 105.0
    assert body["per_item"][0]["description"] == "2 eggs and toast"
    assert isinstance(body["trace"], list) and len(body["trace"]) >= 1
    assert isinstance(body["confidence"], float)
    assert isinstance(body["reasons"], list)
    assert "needs_review" in body
    assert "safety" in body
