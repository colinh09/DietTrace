"""Deterministic macro/micro math for a logged meal.

``log_entry(items)`` is the calculation half of the search/calculation split:
given foods already resolved to gram weights (by ``estimate_portion``),
it scales each food's per-100 g nutrient panel by its grams and sums the panels
into meal totals — the agent never invents a number a tool can compute.

Energy (USDA code 208) is special-cased. When a food carries Atwater
``conversion_factors``, energy is recomputed from the scaled macros
(``protein_g · f_p + fat_g · f_f + carb_g · f_c``) rather than scaling the
stored 208, because the macro-derived figure is what USDA itself reports for
those foods; a per-macro factor that is absent falls back to the standard
Atwater value. When a food has conversion factors but no macros to derive energy
from, the stored 208 is kept (not zeroed). Without conversion factors the stored
per-100 g energy is scaled like any other nutrient.
"""

from __future__ import annotations

import math

from pydantic import BaseModel

from dietrace.nutrition.models import ConversionFactors, Food, Nutrient

# USDA number codes the math reads by, never by name.
_ENERGY, _PROTEIN, _FAT, _CARB = "208", "203", "204", "205"

# Standard Atwater factors (kcal per gram) — the fallback when a food's own
# conversion factor for a macro is missing.
_STD_ATWATER: dict[str, float] = {_PROTEIN: 4.0, _FAT: 9.0, _CARB: 4.0}


class MealItem(BaseModel):
    """One food of the meal resolved to its portion weight in grams."""

    food: Food
    grams: float
    portion_basis: str = ""


class LoggedItem(BaseModel):
    """A single item's portion: its identity plus the scaled nutrient panel.

    ``nutrients`` holds absolute amounts for ``grams`` of the food (not
    per-100 g), with energy (208) already resolved via Atwater when available.
    ``portion_basis`` explains why this gram weight was chosen — e.g. "matched
    serving: 1 cup" or "counted 10 piece(s) — 1 nut".
    """

    fdc_id: int
    description: str
    grams: float
    portion_basis: str = ""
    nutrients: list[Nutrient] = []

    def nutrient(self, code: str) -> Nutrient | None:
        """Return this item's scaled nutrient for *code*, or None if absent."""
        for nutrient in self.nutrients:
            if nutrient.code == code:
                return nutrient
        return None


class LoggedMeal(BaseModel):
    """The result of :func:`log_entry`: per-item panels and summed totals."""

    per_item: list[LoggedItem] = []
    totals: list[Nutrient] = []

    def total(self, code: str) -> Nutrient | None:
        """Return the summed total nutrient for *code*, or None if absent."""
        for nutrient in self.totals:
            if nutrient.code == code:
                return nutrient
        return None


def _atwater_kcal(
    scaled: dict[str, Nutrient], factors: ConversionFactors
) -> float | None:
    """Energy from the scaled macros and *factors*, or None if no macro is present.

    A missing per-macro factor falls back to the standard Atwater value. When the
    panel carries no macros at all there is nothing to derive energy from, so this
    returns None and the caller keeps the food's stored 208 rather than zeroing it.
    """
    own = {_PROTEIN: factors.protein, _FAT: factors.fat, _CARB: factors.carbohydrate}
    kcal = 0.0
    found = False
    for code, std in _STD_ATWATER.items():
        macro = scaled.get(code)
        if macro is None:
            continue
        found = True
        factor = own[code] if own[code] is not None else std
        kcal += macro.amount * factor
    return kcal if found else None


def _scaled_panel(food: Food, grams: float) -> list[Nutrient]:
    """Scale *food*'s per-100 g panel to *grams*, resolving energy by Atwater."""
    ratio = grams / 100.0
    scaled = {
        n.code: Nutrient(code=n.code, name=n.name, amount=n.amount * ratio, unit=n.unit)
        for n in food.nutrients
    }
    if food.conversion_factors is not None:
        atwater = _atwater_kcal(scaled, food.conversion_factors)
        if atwater is not None:
            existing = scaled.get(_ENERGY)
            scaled[_ENERGY] = Nutrient(
                code=_ENERGY,
                name=existing.name if existing else "Energy",
                amount=atwater,
                unit=existing.unit if existing else "kcal",
            )
    return list(scaled.values())


def log_entry(items: list[MealItem]) -> LoggedMeal:
    """Compute per-item and total nutrients for a gram-resolved meal.

    Each item's panel is its food's per-100 g nutrients scaled by grams, with
    energy taken from Atwater factors when present. Totals sum the per-item
    panels code by code, preserving each nutrient's name and unit.

    An item whose ``grams`` is non-finite (NaN/±inf) or non-positive is dropped:
    this step is also an ADK ``FunctionTool`` the model calls directly with its
    own grams, and such a weight scales every nutrient to a non-finite amount
    (or, when negative, *subtracts* from the totals) — one bad item would poison
    every downstream macro. The food was already resolved to a gram weight, so an
    unusable weight means the item is omitted rather than corrupting the meal
    (mirrors the non-finite guard in ``estimate_portion``/``parse_meal``).
    """
    per_item = [
        LoggedItem(
            fdc_id=item.food.fdc_id,
            description=item.food.description,
            grams=item.grams,
            portion_basis=item.portion_basis,
            nutrients=_scaled_panel(item.food, item.grams),
        )
        for item in items
        if math.isfinite(item.grams) and item.grams > 0
    ]

    totals: dict[str, Nutrient] = {}
    for logged in per_item:
        for nutrient in logged.nutrients:
            running = totals.get(nutrient.code)
            if running is None:
                totals[nutrient.code] = nutrient.model_copy()
            else:
                running.amount += nutrient.amount

    return LoggedMeal(per_item=per_item, totals=list(totals.values()))
