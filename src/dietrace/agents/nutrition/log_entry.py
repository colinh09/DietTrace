"""Deterministic macro/micro math for a logged meal.

``log_entry(items)`` is the calculation half of the search/calculation split
: given foods already resolved to gram weights (by ``estimate_portion``),
it scales each food's per-100 g nutrient panel by its grams and sums the panels
into meal totals — the agent never invents a number a tool can compute.

Energy (USDA code 208) is special-cased. When a food carries Atwater
``conversion_factors``, energy is recomputed from the scaled macros
(``protein_g · f_p + fat_g · f_f + carb_g · f_c``) rather than scaling the
stored 208, because the macro-derived figure is what USDA itself reports for
those foods; a per-macro factor that is absent falls back to the standard
Atwater value. Without conversion factors the stored per-100 g energy is scaled
like any other nutrient.
"""

from __future__ import annotations

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


class LoggedItem(BaseModel):
    """A single item's portion: its identity plus the scaled nutrient panel.

    ``nutrients`` holds absolute amounts for ``grams`` of the food (not
    per-100 g), with energy (208) already resolved via Atwater when available.
    """

    fdc_id: int
    description: str
    grams: float
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


def _atwater_kcal(scaled: dict[str, Nutrient], factors: ConversionFactors) -> float:
    """Energy from the scaled macros and *factors*, defaulting missing factors."""
    own = {_PROTEIN: factors.protein, _FAT: factors.fat, _CARB: factors.carbohydrate}
    kcal = 0.0
    for code, std in _STD_ATWATER.items():
        macro = scaled.get(code)
        if macro is None:
            continue
        factor = own[code] if own[code] is not None else std
        kcal += macro.amount * factor
    return kcal


def _scaled_panel(food: Food, grams: float) -> list[Nutrient]:
    """Scale *food*'s per-100 g panel to *grams*, resolving energy by Atwater."""
    ratio = grams / 100.0
    scaled = {
        n.code: Nutrient(code=n.code, name=n.name, amount=n.amount * ratio, unit=n.unit)
        for n in food.nutrients
    }
    if food.conversion_factors is not None:
        existing = scaled.get(_ENERGY)
        scaled[_ENERGY] = Nutrient(
            code=_ENERGY,
            name=existing.name if existing else "Energy",
            amount=_atwater_kcal(scaled, food.conversion_factors),
            unit=existing.unit if existing else "kcal",
        )
    return list(scaled.values())


def log_entry(items: list[MealItem]) -> LoggedMeal:
    """Compute per-item and total nutrients for a gram-resolved meal.

    Each item's panel is its food's per-100 g nutrients scaled by grams, with
    energy taken from Atwater factors when present. Totals sum the per-item
    panels code by code, preserving each nutrient's name and unit.
    """
    per_item = [
        LoggedItem(
            fdc_id=item.food.fdc_id,
            description=item.food.description,
            grams=item.grams,
            nutrients=_scaled_panel(item.food, item.grams),
        )
        for item in items
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
