"""Tests for log_entry — deterministic macro/micro math (3.2; ).

``log_entry(items)`` takes foods already resolved to gram weights and scales
each food's per-100 g nutrient panel by its grams, then sums the panel across
items into totals. Energy (USDA code 208) is computed from Atwater conversion
factors when the food carries them, otherwise the per-100 g energy is scaled
directly — this is the deterministic calculation half of the search/calculation
split, so the agent never invents numbers a tool can derive.

The done criterion is per-item *and* total values for a 2-item meal; the foods
are built directly with round per-100 g numbers so the arithmetic is exact.
"""

import pytest

from dietrace.agents.nutrition.log_entry import (
    LoggedMeal,
    MealItem,
    log_entry,
)
from dietrace.nutrition.models import ConversionFactors, Food, Nutrient

# USDA number codes the math reads by: energy, protein, fat, carb.
_ENERGY, _PROTEIN, _FAT, _CARB = "208", "203", "204", "205"


def _egg() -> Food:
    """Egg with Atwater factors — energy must come from the factors, not 208."""
    return Food(
        fdc_id=748967,
        description="Egg, whole, raw, fresh",
        data_type="sr_legacy_food",
        nutrients=[
            Nutrient(code=_ENERGY, name="Energy", amount=140.0, unit="kcal"),
            Nutrient(code=_PROTEIN, name="Protein", amount=12.0, unit="g"),
            Nutrient(code=_FAT, name="Total lipid (fat)", amount=10.0, unit="g"),
            Nutrient(code=_CARB, name="Carbohydrate", amount=1.0, unit="g"),
        ],
        conversion_factors=ConversionFactors(protein=4.0, fat=9.0, carbohydrate=4.0),
    )


def _toast() -> Food:
    """Toast with no conversion factors — energy is the scaled per-100 g 208."""
    return Food(
        fdc_id=172686,
        description="Bread, whole-wheat, commercially prepared",
        data_type="sr_legacy_food",
        nutrients=[
            Nutrient(code=_ENERGY, name="Energy", amount=250.0, unit="kcal"),
            Nutrient(code=_PROTEIN, name="Protein", amount=13.0, unit="g"),
            Nutrient(code=_FAT, name="Total lipid (fat)", amount=4.0, unit="g"),
            Nutrient(code=_CARB, name="Carbohydrate", amount=43.0, unit="g"),
        ],
    )


def _meal() -> LoggedMeal:
    """A 2-item meal: 100 g of egg + 28 g of toast."""
    return log_entry([MealItem(food=_egg(), grams=100.0), MealItem(food=_toast(), grams=28.0)])


def test_per_item_scales_macros_by_grams() -> None:
    """Each item's macros are its per-100 g amount × grams / 100."""
    meal = _meal()

    egg, toast = meal.per_item
    assert egg.fdc_id == 748967
    assert egg.grams == pytest.approx(100.0)
    assert egg.nutrient(_PROTEIN).amount == pytest.approx(12.0)
    assert egg.nutrient(_FAT).amount == pytest.approx(10.0)
    assert egg.nutrient(_CARB).amount == pytest.approx(1.0)

    assert toast.grams == pytest.approx(28.0)
    assert toast.nutrient(_PROTEIN).amount == pytest.approx(3.64)
    assert toast.nutrient(_FAT).amount == pytest.approx(1.12)
    assert toast.nutrient(_CARB).amount == pytest.approx(12.04)


def test_per_item_energy_uses_atwater_when_present() -> None:
    """The egg's energy is Atwater (12·4 + 10·9 + 1·4 = 142), not the raw 208 (140)."""
    egg = _meal().per_item[0]

    assert egg.nutrient(_ENERGY).amount == pytest.approx(142.0)
    assert egg.nutrient(_ENERGY).unit == "kcal"


def test_per_item_energy_scales_208_without_factors() -> None:
    """The toast has no factors, so energy is the per-100 g 208 scaled: 250 × 0.28."""
    toast = _meal().per_item[1]

    assert toast.nutrient(_ENERGY).amount == pytest.approx(70.0)


def test_totals_sum_each_nutrient_across_items() -> None:
    """Totals add the per-item panels code by code, energy included."""
    totals = _meal()

    assert totals.total(_ENERGY).amount == pytest.approx(212.0)  # 142 + 70
    assert totals.total(_PROTEIN).amount == pytest.approx(15.64)  # 12 + 3.64
    assert totals.total(_FAT).amount == pytest.approx(11.12)  # 10 + 1.12
    assert totals.total(_CARB).amount == pytest.approx(13.04)  # 1 + 12.04


def test_totals_carry_nutrient_metadata() -> None:
    """A total nutrient keeps its code/name/unit, not just the summed amount."""
    protein = _meal().total(_PROTEIN)

    assert protein.code == _PROTEIN
    assert protein.name == "Protein"
    assert protein.unit == "g"


def test_missing_nutrient_total_is_none() -> None:
    """A code absent from every item has no total."""
    assert _meal().total("999") is None
