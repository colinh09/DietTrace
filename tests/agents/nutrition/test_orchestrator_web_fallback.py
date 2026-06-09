"""The branded-item gate: when the DB can't honor a brand, log the web result.

A search for "bacon cheeseburger" returns *some* chain's cheeseburger; for a Five
Guys order that DB match is the wrong restaurant, so the orchestrator must route to
the grounded web lookup instead. These tests inject both the parse client and the
web lookup so the gate logic is exercised with no live call: the lookup is invoked
only when the DB match doesn't satisfy the brand, and its food is what gets logged.
"""

from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

from dietrace.agents.nutrition.orchestrator import log_meal, stream_meal
from dietrace.nutrition.models import Food, Nutrient, ServingSize
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
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(
        text=json.dumps({"items": items})
    )
    return client


def _web_food() -> Food:
    """A stand-in grounded result: one 250 g serving panel keyed by USDA code."""
    return Food(
        fdc_id=0,
        description="Five Guys bacon cheeseburger",
        data_type="web_grounded",
        nutrients=[Nutrient(code="208", name="Energy", amount=312.0, unit="kcal")],
        serving_sizes=[
            ServingSize(amount=1.0, unit="serving", gram_weight=250.0, description="web serving")
        ],
    )


def test_branded_item_absent_from_db_logs_the_web_result(tmp_path) -> None:
    client = _parse_client(
        [{"food": "bacon cheeseburger", "quantity": 1, "unit": "", "brand": "Five Guys"}]
    )
    calls: list[tuple[str, str]] = []

    def web_lookup(food: str, brand: str, _client) -> Food:
        calls.append((food, brand))
        return _web_food()

    meal = log_meal(
        "a Five Guys bacon cheeseburger",
        _repo(tmp_path),
        client=client,
        web_lookup=web_lookup,
    )

    # The web lookup ran with the brand, and its 250 g serving was logged.
    assert calls == [("bacon cheeseburger", "Five Guys")]
    assert len(meal.per_item) == 1
    assert meal.per_item[0].description == "Five Guys bacon cheeseburger"
    assert meal.per_item[0].grams == 250.0
    energy = meal.total("208")
    assert energy is not None and round(energy.amount) == 780  # 312/100 × 250 g


def test_substring_only_match_is_not_trusted_and_tries_the_web(tmp_path) -> None:
    # "read" only matches "Bread, …" as a loose substring (score 1) — too weak to
    # trust (cf. "pho" → a candy bar via "symPHOny"), so the web is tried instead.
    client = _parse_client([{"food": "read", "quantity": 1, "unit": "", "brand": ""}])
    calls: list[str] = []

    def web_lookup(food: str, brand: str, _client) -> Food:
        calls.append(food)
        return _web_food()

    meal = log_meal("read", _repo(tmp_path), client=client, web_lookup=web_lookup)

    assert calls == ["read"]  # weak DB match bypassed in favor of the web
    assert meal.per_item[0].description == "Five Guys bacon cheeseburger"


def test_unbranded_db_match_never_calls_the_web(tmp_path) -> None:
    # A plain food the DB carries must resolve locally — no grounded call.
    client = _parse_client([{"food": "egg", "quantity": 1, "unit": "large"}])
    called = False

    def web_lookup(food: str, brand: str, _client) -> Food | None:
        nonlocal called
        called = True
        return None

    meal = log_meal("an egg", _repo(tmp_path), client=client, web_lookup=web_lookup)

    assert called is False
    assert meal.per_item[0].description.startswith("Egg")


def test_weak_db_match_is_logged_when_the_web_lookup_comes_back_empty(tmp_path) -> None:
    # The last-resort branch (: "keeps the DB match as a last resort over
    # dropping the item"): a substring-only match ("read" → "Bread", score 1) is too
    # weak to win outright, so the web is tried — but when the grounded lookup itself
    # returns nothing, dropping the item would lose nutrition the DB *can* approximate.
    # The weak DB match must be logged rather than the meal coming back empty.
    client = _parse_client([{"food": "read", "quantity": 1, "unit": "", "brand": ""}])
    calls: list[str] = []

    def web_lookup(food: str, brand: str, _client) -> Food | None:
        calls.append(food)
        return None  # grounded lookup found nothing

    meal = log_meal("read", _repo(tmp_path), client=client, web_lookup=web_lookup)

    assert calls == ["read"]  # the web was tried before falling back
    assert len(meal.per_item) == 1  # item NOT dropped
    assert meal.per_item[0].description.startswith("Bread")  # the weak match stands
    assert meal.per_item[0].grams > 0  # resolved to a usable portion


def test_stream_emits_a_web_search_step_for_a_branded_fallback(tmp_path) -> None:
    client = _parse_client(
        [{"food": "bacon cheeseburger", "quantity": 1, "unit": "", "brand": "Five Guys"}]
    )

    events = list(
        stream_meal(
            "a Five Guys bacon cheeseburger",
            _repo(tmp_path),
            client=client,
            web_lookup=lambda food, brand, c: _web_food(),
        )
    )

    steps = [e["step"] for e in events if e["type"] == "step"]
    assert "web_search" in steps
    web = next(e for e in events if e.get("step") == "web_search")
    assert "Five Guys bacon cheeseburger" in web["summary"]
    assert events[-1]["type"] == "result" and events[-1]["per_item"]
