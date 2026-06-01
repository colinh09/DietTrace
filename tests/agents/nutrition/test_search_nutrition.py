"""Tests for search_nutrition — deterministic food lookup (3.3; ).

``search_nutrition(repository, food)`` is the search half of the
search/calculation split: it turns free text into a reproducible
``fdc_id`` plus that food's per-100 g nutrient panel and USDA ``data_type``, all
read deterministically from the food DB read layer (``dietrace.nutrition``) —
the LLM never invents a number a lookup can return. It wraps ``FoodRepository``:
``search`` picks the best-ranked candidate and ``get`` hydrates it.

These tests run against the same tiny fixture SQLite the read-layer tests use
(an egg, an avocado, a slice of toast), so the done criterion — a reproducible
``fdc_id`` for a fixture food — is exercised end to end through the repository,
never the real 3 GB data.
"""

import sqlite3
from pathlib import Path

import pytest

from dietrace.agents.nutrition.search_nutrition import NutritionMatch, search_nutrition
from dietrace.nutrition.repository import FoodRepository
from tests.nutrition.fixtures_food_db import (
    AVOCADO_FDC_ID,
    EGG_FDC_ID,
    build_food_db,
)

# USDA number codes the panel is read by: energy, protein, fat, carb.
_ENERGY, _PROTEIN, _FAT, _CARB = "208", "203", "204", "205"


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


def test_returns_reproducible_fdc_id_for_a_fixture_food(repository) -> None:
    """"egg" resolves to the egg's fdc_id, the same one on every call."""
    first = search_nutrition(repository, "egg")
    second = search_nutrition(repository, "egg")

    assert isinstance(first, NutritionMatch)
    assert first.fdc_id == EGG_FDC_ID
    assert second.fdc_id == EGG_FDC_ID


def test_returns_per_100g_nutrients_by_code(repository) -> None:
    """The match carries the per-100 g panel, read by USDA number code."""
    match = search_nutrition(repository, "egg")

    assert match.nutrient(_ENERGY).amount == pytest.approx(143.0)
    assert match.nutrient(_PROTEIN).amount == pytest.approx(12.6)
    assert match.nutrient(_FAT).amount == pytest.approx(9.51)
    assert match.nutrient(_CARB).amount == pytest.approx(0.72)


def test_returns_data_type(repository) -> None:
    """The match reports the food's USDA data_type."""
    match = search_nutrition(repository, "avocado")

    assert match.fdc_id == AVOCADO_FDC_ID
    assert match.data_type == "sr_legacy_food"


def test_alias_match_resolves_to_canonical_food(repository) -> None:
    """An alias ("whole wheat bread") resolves through to the toast's fdc_id."""
    match = search_nutrition(repository, "whole wheat bread")

    assert match is not None
    assert match.description.lower().startswith("bread")


def test_no_match_is_fail_soft(repository) -> None:
    """A food absent from the DB returns None rather than raising."""
    assert search_nutrition(repository, "dragonfruit") is None


def test_blank_query_returns_none(repository) -> None:
    """A blank query matches nothing and returns None."""
    assert search_nutrition(repository, "   ") is None


def test_missing_nutrient_code_is_none(repository) -> None:
    """A code absent from the food's panel has no nutrient on the match."""
    match = search_nutrition(repository, "egg")

    assert match.nutrient("999") is None


def test_overlay_pins_a_common_food_over_the_ranked_search(repository) -> None:
    """A curated overlay entry wins regardless of what the ranked search would pick."""
    # Deliberately pin "toast" to the egg fdc_id — the pin must override ranking.
    match = search_nutrition(repository, "toast", overlay={"toast": EGG_FDC_ID})
    assert match is not None
    assert match.fdc_id == EGG_FDC_ID
    assert match.score == 4  # pinned matches are treated as exact


def test_overlay_miss_falls_through_to_ranked_search(repository) -> None:
    match = search_nutrition(repository, "avocado", overlay={"banana": EGG_FDC_ID})
    assert match is not None
    assert match.fdc_id == AVOCADO_FDC_ID  # not pinned → ranked search decides
