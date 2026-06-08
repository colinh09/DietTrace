"""Tests for the nutrition agent assembly (3.6; ).

wires the five deterministic/generative tools — ``parse_meal`` →
``search_nutrition`` → ``estimate_portion`` → ``log_entry`` →
``check_against_goals`` — into an ADK ``Agent`` named
``dietrace_nutrition`` plus a ``Runner`` over an ``InMemorySessionService``,
mirroring axon's worker construction. The done criterion is that the assembly
*constructs and exposes the five tools*, so these tests pin the agent's name,
the registry (five tools, in pipeline order), the runner wiring, and that each
exposed tool delegates to its underlying implementation.

Construction runs fully offline: the ADK ``Agent``/``Runner`` take the model as
a plain string and build no client until a turn is run, and the Gemini client is
a ``Mock`` here — the no-network guard in ``conftest.py`` would block a real
Vertex call. Tools that read the food DB use the same tiny fixture SQLite the
read-layer tests use, never the real data.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from dietrace.agents.nutrition.agent import (
    AGENT_NAME,
    NutritionAgent,
    build_nutrition_agent,
    build_nutrition_tools,
)
from dietrace.llm.config import GEMINI_MODEL
from dietrace.nutrition.repository import FoodRepository
from tests.nutrition.fixtures_food_db import EGG_FDC_ID, build_food_db

# The pipeline order the registry must expose.
_PIPELINE = [
    "parse_meal",
    "search_nutrition",
    "estimate_portion",
    "log_entry",
    "check_against_goals",
]

_ENERGY, _PROTEIN = "208", "203"


@pytest.fixture
def repository(tmp_path: Path) -> FoodRepository:
    """A FoodRepository over a throwaway fixture DB, never the real data."""
    db_path = tmp_path / "food.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        build_food_db(conn)
    finally:
        conn.close()
    return FoodRepository(db_path)


def _client(text: str | None) -> Mock:
    """A Gemini client mock whose ``generate_content`` returns *text*."""
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(text=text)
    return client


def _tool(agent: NutritionAgent, name: str):
    """Return the exposed tool named *name*."""
    return next(t for t in agent.tools if t.name == name)


def test_agent_is_named_dietrace_nutrition(repository) -> None:
    """The assembled ADK agent carries the required name."""
    agent = NutritionAgent(repository, client=_client(None))

    assert AGENT_NAME == "dietrace_nutrition"
    assert agent.agent.name == "dietrace_nutrition"
    assert agent.agent.model == GEMINI_MODEL


def test_exposes_five_tools_in_pipeline_order(repository) -> None:
    """The done criterion: five tools, exposed in the  pipeline order."""
    agent = NutritionAgent(repository, client=_client(None))

    assert [t.name for t in agent.tools] == _PIPELINE


def test_runner_wired_with_in_memory_session_service(repository) -> None:
    """A Runner over an InMemorySessionService wraps the agent."""
    agent = NutritionAgent(repository, client=_client(None))

    assert isinstance(agent.runner, Runner)
    assert isinstance(agent.session_service, InMemorySessionService)
    assert agent.runner.agent is agent.agent


def test_instruction_is_loaded_and_nonempty(repository) -> None:
    """The agent's instruction comes from instruction.md and is non-empty."""
    instruction_path = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "dietrace"
        / "agents"
        / "nutrition"
        / "instruction.md"
    )
    assert instruction_path.exists()

    agent = NutritionAgent(repository, client=_client(None))
    assert agent.instruction.strip()
    assert agent.agent.instruction == agent.instruction


def test_parse_meal_tool_delegates_to_the_model(repository) -> None:
    """The parse_meal tool returns the items parsed from the mocked client."""
    client = _client('{"items": [{"food": "egg", "quantity": 2, "unit": "each"}]}')
    tools = build_nutrition_tools(repository, client=client)
    parse_meal = next(t for t in tools if t.name == "parse_meal")

    items = parse_meal.func("two eggs")

    assert items == [{"food": "egg", "quantity": 2.0, "unit": "each", "brand": ""}]


def test_search_nutrition_tool_delegates_to_the_repository(repository) -> None:
    """The search_nutrition tool resolves a fixture food to its fdc_id."""
    agent = NutritionAgent(repository, client=_client(None))

    match = _tool(agent, "search_nutrition").func("egg")

    assert match["fdc_id"] == EGG_FDC_ID
    assert match["data_type"] == "sr_legacy_food"


def test_search_nutrition_tool_returns_none_on_miss(repository) -> None:
    """A query that matches nothing returns None (fail-soft)."""
    agent = NutritionAgent(repository, client=_client(None))

    assert _tool(agent, "search_nutrition").func("nonexistent food") is None


def test_estimate_portion_tool_resolves_food_by_fdc_id(repository) -> None:
    """The estimate_portion tool looks the food up by fdc_id, then estimates grams."""
    agent = NutritionAgent(repository, client=_client(None))

    estimate = _tool(agent, "estimate_portion").func(EGG_FDC_ID, 1.0, "large")

    assert estimate["grams"] == pytest.approx(50.0)
    assert estimate["source"] == "serving_size"


def test_estimate_portion_tool_unknown_food_fails_soft(repository) -> None:
    """An unknown fdc_id yields grams=None rather than raising."""
    agent = NutritionAgent(repository, client=_client(None))

    estimate = _tool(agent, "estimate_portion").func(-1, 1.0, "each")

    assert estimate["grams"] is None
    assert estimate["confidence"] == 0.0


def test_log_entry_tool_computes_totals(repository) -> None:
    """The log_entry tool resolves foods by fdc_id and totals their nutrients."""
    agent = NutritionAgent(repository, client=_client(None))

    meal = _tool(agent, "log_entry").func([{"fdc_id": EGG_FDC_ID, "grams": 100.0}])

    totals = {n["code"]: n["amount"] for n in meal["totals"]}
    assert totals[_PROTEIN] == pytest.approx(12.6)
    assert meal["per_item"][0]["fdc_id"] == EGG_FDC_ID


def test_check_against_goals_tool_reports_status(repository) -> None:
    """The check_against_goals tool compares totals to goals and labels each."""
    agent = NutritionAgent(repository, client=_client(None))

    totals = [{"code": _ENERGY, "name": "Energy", "amount": 100.0, "unit": "kcal"}]
    goals = [{"code": _ENERGY, "name": "Energy", "target": 100.0, "unit": "kcal"}]
    check = _tool(agent, "check_against_goals").func(totals, goals)

    assert check["statuses"][0]["status"] == "within"


def test_build_factory_is_fail_soft_without_phoenix(repository, monkeypatch) -> None:
    """build_nutrition_agent constructs the agent; tracing is a no-op without a key."""
    monkeypatch.delenv("PHOENIX_API_KEY", raising=False)

    agent = build_nutrition_agent(repository, client=_client(None))

    assert isinstance(agent, NutritionAgent)
    assert [t.name for t in agent.tools] == _PIPELINE


def test_build_factory_survives_tracing_misconfig(repository, monkeypatch) -> None:
    """A Phoenix misconfig must not block agent construction.

    With PHOENIX_API_KEY set but PHOENIX_COLLECTOR_ENDPOINT missing, init_tracer
    raises RuntimeError; the factory should swallow it like the web lifespan does,
    so the agent still builds rather than crashing on a tracing setup error.
    """
    monkeypatch.setenv("PHOENIX_API_KEY", "test-key")
    monkeypatch.delenv("PHOENIX_COLLECTOR_ENDPOINT", raising=False)

    agent = build_nutrition_agent(repository, client=_client(None))

    assert isinstance(agent, NutritionAgent)
    assert [t.name for t in agent.tools] == _PIPELINE
