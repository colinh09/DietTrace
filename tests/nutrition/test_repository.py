"""Tests for src/dietrace/nutrition/repository.py — FoodRepository.get.

The read layer hydrates a ``Food`` from the local SQLite food DB by
``fdc_id``: its nutrient panel keyed by USDA number code (208 kcal, 203 protein,
204 fat, 205 carb), serving-size gram weights, and Atwater conversion
factors. These tests run against the tiny ``food_db`` fixture (egg, avocado,
toast), never the real 3 GB ``data/food.sqlite``.
"""

from dietrace.nutrition.models import Food
from dietrace.nutrition.repository import FoodRepository
from tests.nutrition.fixtures_food_db import (
    AVOCADO_FDC_ID,
    EGG_FDC_ID,
    TOAST_FDC_ID,
)


def test_get_returns_food_with_nutrients_by_code(food_db) -> None:
    """get(fdc_id) hydrates the macro panel reachable by USDA number code."""
    repo = FoodRepository(food_db)

    egg = repo.get(EGG_FDC_ID)

    assert isinstance(egg, Food)
    assert egg.fdc_id == EGG_FDC_ID
    assert egg.description == "Egg, whole, raw, fresh"
    assert egg.data_type == "sr_legacy_food"

    energy = egg.nutrient("208")
    assert energy is not None
    assert energy.name == "Energy"
    assert energy.amount == 143.0
    assert energy.unit == "kcal"

    assert egg.nutrient("203").amount == 12.6
    assert egg.nutrient("204").amount == 9.51
    assert egg.nutrient("205").amount == 0.72


def test_get_returns_serving_sizes(food_db) -> None:
    """Serving-size gram weights come back ordered for portion estimation."""
    repo = FoodRepository(food_db)

    avocado = repo.get(AVOCADO_FDC_ID)

    assert [(s.amount, s.unit, s.gram_weight) for s in avocado.serving_sizes] == [
        (1.0, "fruit", 201.0),
        (0.5, "fruit", 100.5),
    ]
    assert avocado.serving_sizes[0].description == "1 fruit, without skin and seed"


def test_get_returns_conversion_factors(food_db) -> None:
    """Atwater factors hydrate when USDA provides them."""
    repo = FoodRepository(food_db)

    egg = repo.get(EGG_FDC_ID)

    assert egg.conversion_factors is not None
    assert egg.conversion_factors.protein == 4.36
    assert egg.conversion_factors.fat == 9.02
    assert egg.conversion_factors.carbohydrate == 3.68


def test_get_without_conversion_factors_is_none(food_db) -> None:
    """A food the fixture omits Atwater factors for has no conversion_factors."""
    repo = FoodRepository(food_db)

    toast = repo.get(TOAST_FDC_ID)

    assert toast.conversion_factors is None
    assert toast.nutrient("208").amount == 254.0


def test_get_unknown_fdc_id_returns_none(food_db) -> None:
    """An fdc_id absent from the DB yields None rather than raising."""
    repo = FoodRepository(food_db)

    assert repo.get(999999) is None


def test_get_fails_soft_when_db_missing(tmp_path) -> None:
    """A missing DB file degrades to None instead of raising (fail-soft)."""
    missing = FoodRepository(tmp_path / "does_not_exist.sqlite")

    assert missing.get(1001) is None


def test_search_fails_soft_when_db_missing(tmp_path) -> None:
    """A missing DB file degrades to no candidates instead of raising (fail-soft)."""
    missing = FoodRepository(tmp_path / "does_not_exist.sqlite")

    assert missing.search("egg") == []
