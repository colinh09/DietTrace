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

from dietrace.agents.nutrition.orchestrator import log_meal
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


def test_unresolvable_item_is_skipped(tmp_path) -> None:
    client = _parse_client(
        [
            {"food": "egg", "quantity": 1, "unit": "large"},
            {"food": "unicorn meat", "quantity": 1, "unit": "slab"},
        ]
    )

    meal = log_meal("an egg and some unicorn meat", _repo(tmp_path), client=client)

    assert len(meal.per_item) == 1
    assert meal.per_item[0].description.startswith("Egg")
