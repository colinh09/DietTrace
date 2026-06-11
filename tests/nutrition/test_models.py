"""Unit tests for src/dietrace/nutrition/models.py.

These pin the food-domain value objects that the read layer hydrates
from the local SQLite food DB: Food, Nutrient, ServingSize, ConversionFactors.
The agent reads nutrients by USDA number code (208 kcal, 203 protein, 204 fat,
205 carb), so the by-code accessor is the load-bearing behavior here.
No DB or network is touched; these are plain construction tests.
"""

import pytest
from pydantic import ValidationError

from dietrace.nutrition.models import (
    ConversionFactors,
    Food,
    Nutrient,
    ServingSize,
)


def _egg() -> Food:
    """A small whole-food fixture (raw egg) with macros, a serving size, and Atwater."""
    return Food(
        fdc_id=748967,
        description="Egg, whole, raw, fresh",
        data_type="sr_legacy_food",
        nutrients=[
            Nutrient(code="208", name="Energy", amount=143.0, unit="kcal"),
            Nutrient(code="203", name="Protein", amount=12.6, unit="g"),
            Nutrient(code="204", name="Total lipid (fat)", amount=9.51, unit="g"),
            Nutrient(code="205", name="Carbohydrate, by difference", amount=0.72, unit="g"),
        ],
        serving_sizes=[
            ServingSize(amount=1.0, unit="large", description="1 large", gram_weight=50.0),
        ],
        conversion_factors=ConversionFactors(
            protein=4.36, fat=9.02, carbohydrate=3.68
        ),
    )


def test_food_constructs_with_full_panel() -> None:
    """A Food hydrates with its nutrients, serving sizes, and conversion factors."""
    egg = _egg()

    assert egg.fdc_id == 748967
    assert egg.data_type == "sr_legacy_food"
    assert len(egg.nutrients) == 4
    assert egg.serving_sizes[0].gram_weight == 50.0
    assert egg.conversion_factors is not None
    assert egg.conversion_factors.protein == 4.36


def test_nutrient_by_code_accessor() -> None:
    """nutrient(code) returns the matching Nutrient, keyed by USDA number code."""
    egg = _egg()

    energy = egg.nutrient("208")
    assert energy is not None
    assert energy.name == "Energy"
    assert energy.amount == 143.0
    assert energy.unit == "kcal"

    protein = egg.nutrient("203")
    assert protein is not None
    assert protein.amount == 12.6


def test_nutrient_by_code_missing_returns_none() -> None:
    """An absent nutrient code yields None rather than raising."""
    egg = _egg()

    assert egg.nutrient("301") is None  # calcium — not present on this fixture


def test_food_defaults_are_empty_not_none() -> None:
    """A minimal Food has empty collections and no conversion factors."""
    bare = Food(fdc_id=1, description="Water", data_type="sr_legacy_food")

    assert bare.nutrients == []
    assert bare.serving_sizes == []
    assert bare.conversion_factors is None
    assert bare.nutrient("208") is None


def test_nutrient_requires_its_fields() -> None:
    """Nutrient construction validates required fields."""
    with pytest.raises(ValidationError):
        Nutrient(code="208", name="Energy")  # missing amount + unit
