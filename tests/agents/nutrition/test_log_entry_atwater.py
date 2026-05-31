"""Atwater edge cases for log_entry — the energy (208) special-case.

``log_entry`` recomputes energy from a food's scaled macros and Atwater
``conversion_factors`` rather than scaling the stored 208, because the
macro-derived figure is what USDA reports for those foods. The happy
path lives in ``test_log_entry.py``; this file pins the corners of that rule:

* a *missing per-macro factor* falls back to the standard Atwater value,
* a *macro absent from the panel* is simply skipped in the sum,
* energy is *synthesized* (name/unit defaulted) when the food has factors but no
  stored 208,
* the derived energy *scales with grams* like every other nutrient, and
* when there are *no macros at all* to derive energy from, the stored 208 is kept
  rather than being zeroed — the tool must not invent (here, destroy) a number it
  cannot actually compute.
"""

import pytest

from dietrace.agents.nutrition.log_entry import MealItem, log_entry
from dietrace.nutrition.models import ConversionFactors, Food, Nutrient

# USDA number codes the math reads by: energy, protein, fat, carb, sodium.
_ENERGY, _PROTEIN, _FAT, _CARB, _SODIUM = "208", "203", "204", "205", "307"


def _food(nutrients: list[Nutrient], factors: ConversionFactors | None) -> Food:
    """A minimal food carrying *nutrients* and (optionally) Atwater *factors*."""
    return Food(
        fdc_id=100001,
        description="Test food",
        data_type="sr_legacy_food",
        nutrients=nutrients,
        conversion_factors=factors,
    )


def _energy_of(food: Food, grams: float) -> Nutrient | None:
    """The single logged item's energy nutrient after logging *grams* of *food*."""
    return log_entry([MealItem(food=food, grams=grams)]).per_item[0].nutrient(_ENERGY)


def test_missing_macro_factor_falls_back_to_standard_atwater() -> None:
    """A None per-macro factor uses the standard Atwater value (fat → 9.0)."""
    food = _food(
        nutrients=[
            Nutrient(code=_ENERGY, name="Energy", amount=999.0, unit="kcal"),
            Nutrient(code=_PROTEIN, name="Protein", amount=10.0, unit="g"),
            Nutrient(code=_FAT, name="Total lipid (fat)", amount=5.0, unit="g"),
            Nutrient(code=_CARB, name="Carbohydrate", amount=20.0, unit="g"),
        ],
        # fat factor absent → standard 9.0; protein/carb use their own factors.
        factors=ConversionFactors(protein=4.0, fat=None, carbohydrate=4.0),
    )

    # 10·4 + 5·9 + 20·4 = 40 + 45 + 80 = 165 (the stored 999 is ignored).
    assert _energy_of(food, 100.0).amount == pytest.approx(165.0)


def test_macro_absent_from_panel_is_skipped_in_atwater() -> None:
    """A macro missing from the panel contributes nothing to the energy sum."""
    food = _food(
        nutrients=[
            Nutrient(code=_PROTEIN, name="Protein", amount=10.0, unit="g"),
            Nutrient(code=_CARB, name="Carbohydrate", amount=20.0, unit="g"),
            # no fat nutrient at all
        ],
        factors=ConversionFactors(protein=4.0, fat=9.0, carbohydrate=4.0),
    )

    # 10·4 + 20·4 = 120; the absent fat adds nothing.
    assert _energy_of(food, 100.0).amount == pytest.approx(120.0)


def test_energy_is_synthesized_when_no_stored_208() -> None:
    """With factors but no stored 208, energy is created with default name/unit."""
    food = _food(
        nutrients=[
            Nutrient(code=_PROTEIN, name="Protein", amount=10.0, unit="g"),
            Nutrient(code=_FAT, name="Total lipid (fat)", amount=5.0, unit="g"),
            Nutrient(code=_CARB, name="Carbohydrate", amount=20.0, unit="g"),
        ],
        factors=ConversionFactors(protein=4.0, fat=9.0, carbohydrate=4.0),
    )

    energy = _energy_of(food, 100.0)
    assert energy is not None
    assert energy.amount == pytest.approx(165.0)  # 40 + 45 + 80
    assert energy.name == "Energy"
    assert energy.unit == "kcal"


def test_atwater_energy_scales_with_grams() -> None:
    """The macro-derived energy scales by grams like the macros it is built from."""
    food = _food(
        nutrients=[
            Nutrient(code=_ENERGY, name="Energy", amount=140.0, unit="kcal"),
            Nutrient(code=_PROTEIN, name="Protein", amount=12.0, unit="g"),
            Nutrient(code=_FAT, name="Total lipid (fat)", amount=10.0, unit="g"),
            Nutrient(code=_CARB, name="Carbohydrate", amount=1.0, unit="g"),
        ],
        factors=ConversionFactors(protein=4.0, fat=9.0, carbohydrate=4.0),
    )

    # At 50 g: macros halve → 6·4 + 5·9 + 0.5·4 = 24 + 45 + 2 = 71.
    assert _energy_of(food, 50.0).amount == pytest.approx(71.0)


def test_stored_208_is_kept_when_no_macros_to_derive_energy() -> None:
    """Factors present but no macros → keep the (scaled) stored 208, never zero it.

    With nothing to feed Atwater, the tool cannot compute an energy figure; it must
    fall back to the food's stored 208 rather than reporting 0 kcal.
    """
    food = _food(
        nutrients=[
            Nutrient(code=_ENERGY, name="Energy", amount=200.0, unit="kcal"),
            Nutrient(code=_SODIUM, name="Sodium, Na", amount=15.0, unit="mg"),
            # no protein/fat/carb at all
        ],
        factors=ConversionFactors(protein=4.0, fat=9.0, carbohydrate=4.0),
    )

    energy = _energy_of(food, 50.0)
    assert energy is not None
    assert energy.amount == pytest.approx(100.0)  # 200 scaled to 50 g, not 0


def test_empty_meal_has_no_items_and_no_totals() -> None:
    """Logging no items yields empty per-item and totals, not an error."""
    meal = log_entry([])

    assert meal.per_item == []
    assert meal.totals == []
    assert meal.total(_ENERGY) is None
