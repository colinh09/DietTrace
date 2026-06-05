"""The deterministic /log orchestration: parse → search → portion → calc.

One mocked Gemini parse, then the real pipeline against the fixture food DB
(egg, avocado, toast). Proves the production path returns gram-scaled totals
without any live call.
"""

from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dietrace.agents.nutrition.orchestrator import _fallback_grams, log_meal
from dietrace.nutrition.models import Food, ServingSize
from dietrace.nutrition.repository import FoodRepository
from tests.nutrition.fixtures_food_db import build_food_db


def _repo(tmp_path) -> FoodRepository:
    db_path = tmp_path / "food.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        build_food_db(conn)
    finally:
        conn.close()
    return FoodRepository(db_path)


def _parse_client(items: list[dict]) -> Mock:
    """A Gemini client mock whose structured parse returns *items*."""
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(
        text=json.dumps({"items": items})
    )
    return client


def test_logs_full_meal_with_scaled_totals(tmp_path) -> None:
    client = _parse_client(
        [
            {"food": "egg", "quantity": 2, "unit": "large"},
            {"food": "avocado", "quantity": 0.5, "unit": "fruit"},
            {"food": "toast", "quantity": 1, "unit": "slice"},
        ]
    )

    meal = log_meal("two eggs, half an avocado, slice of toast", _repo(tmp_path), client=client)

    # All three foods resolved.
    assert len(meal.per_item) == 3
    # 2 large eggs = 100 g; toast slice = 28 g — gram-scaled, not per-100g.
    grams = {item.description.split(",")[0]: item.grams for item in meal.per_item}
    assert grams["Egg"] == 100.0
    assert grams["Bread"] == 28.0
    # Totals are populated and summed across the meal.
    energy = meal.total("208")
    assert energy is not None and energy.amount > 300  # ~143 + ~161 + ~71 kcal
    assert meal.total("203") is not None  # protein totalled


def test_unmatched_unit_falls_back_to_serving(tmp_path) -> None:
    # Gemini emits a unit no serving matches ("blob"); the item must still log
    # (via the food's primary serving) rather than being dropped.
    client = _parse_client([{"food": "egg", "quantity": 2, "unit": "blob"}])

    meal = log_meal("two eggs", _repo(tmp_path), client=client)

    assert len(meal.per_item) == 1
    # Egg primary serving is 50 g; 2 × 50 = 100 g via fallback.
    assert meal.per_item[0].grams == 100.0


def test_unresolvable_item_is_skipped(tmp_path) -> None:
    client = _parse_client(
        [
            {"food": "egg", "quantity": 1, "unit": "large"},
            {"food": "unicorn meat", "quantity": 1, "unit": "slab"},
        ]
    )

    # No brand named, so the unmatched "unicorn meat" has nowhere to fall back —
    # a no-op web lookup keeps the test hermetic and proves the item is dropped.
    meal = log_meal(
        "an egg and some unicorn meat",
        _repo(tmp_path),
        client=client,
        web_lookup=lambda food, brand, client: None,
    )

    assert len(meal.per_item) == 1
    assert meal.per_item[0].description.startswith("Egg")


def test_fallback_grams_prefers_nlea_over_oversized_package() -> None:
    # When no unit resolves, the fallback must scale by the edible NLEA serving
    # (55 g) rather than the oversized package serving (340 g) listed first.
    food = Food(
        fdc_id=42,
        description="Granola, oats and honey",
        data_type="branded_food",
        serving_sizes=[
            ServingSize(amount=1.0, unit="package", gram_weight=340.0, description="1 package"),
            ServingSize(amount=1.0, unit="cup", gram_weight=55.0, description="1 NLEA serving"),
        ],
    )

    assert _fallback_grams(food, 1.0) == pytest.approx(55.0)


def test_fallback_grams_defaults_to_100g_without_servings() -> None:
    # A food with no serving sizes still resolves, at 100 g per unit.
    food = Food(fdc_id=99, description="Mystery powder", data_type="branded_food")

    assert _fallback_grams(food, 2.0) == pytest.approx(200.0)


def test_stream_meal_emits_steps_then_result(tmp_path) -> None:
    from dietrace.agents.nutrition.orchestrator import stream_meal

    client = _parse_client([{"food": "egg", "quantity": 2, "unit": "large"}])
    events = list(stream_meal("two eggs", _repo(tmp_path), client=client))

    assert events[0]["type"] == "step" and events[0]["step"] == "parse_meal"
    assert events[-1]["type"] == "result"
    steps = [e["step"] for e in events if e["type"] == "step"]
    assert {"parse_meal", "search_nutrition", "estimate_portion", "log_entry"} <= set(steps)
    result = events[-1]
    assert result["totals"] and result["per_item"]
    # The result's trace is exactly the step events that streamed.
    assert result["trace"] == [e for e in events if e["type"] == "step"]


# ──  per-portion basis ─────────────────────────────────────────────


def test_log_meal_items_carry_portion_basis(tmp_path) -> None:
    """Each per-item in the logged meal carries a non-empty portion_basis string."""
    client = _parse_client([{"food": "egg", "quantity": 1, "unit": "large"}])
    meal = log_meal("an egg", _repo(tmp_path), client=client)

    assert len(meal.per_item) == 1
    assert meal.per_item[0].portion_basis  # non-empty basis string


def test_stream_meal_estimate_step_carries_basis(tmp_path) -> None:
    """The estimate_portion trace step emits a non-empty 'basis' field."""
    from dietrace.agents.nutrition.orchestrator import stream_meal

    client = _parse_client([{"food": "egg", "quantity": 1, "unit": "large"}])
    events = list(stream_meal("an egg", _repo(tmp_path), client=client))

    portion_steps = [
        e for e in events
        if e.get("type") == "step" and e.get("step") == "estimate_portion"
    ]
    assert portion_steps, "no estimate_portion step emitted"
    for step in portion_steps:
        assert step.get("basis"), f"missing basis on step: {step}"
