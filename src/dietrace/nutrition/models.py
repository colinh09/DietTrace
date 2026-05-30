"""Food-domain value objects for the read layer.

These mirror the tracked-but-obscured SQLite food DB: a ``Food`` aggregates its
``Nutrient`` panel, ``ServingSize`` gram weights, and Atwater
``ConversionFactors``. The agent reads nutrients by USDA number code — 208 kcal,
203 protein, 204 fat, 205 carb — never by name, so results stay
reproducible; ``Food.nutrient(code)`` is that accessor.
"""

from __future__ import annotations

from pydantic import BaseModel


class Nutrient(BaseModel):
    """A single nutrient amount per 100 g, identified by its USDA number code."""

    code: str
    name: str
    amount: float
    unit: str


class ServingSize(BaseModel):
    """A household portion and its weight in grams (e.g. "1 large" egg = 50 g)."""

    amount: float
    unit: str
    gram_weight: float
    description: str | None = None


class ConversionFactors(BaseModel):
    """Atwater energy factors (kcal per gram) for protein, fat, and carbohydrate."""

    protein: float | None = None
    fat: float | None = None
    carbohydrate: float | None = None


class Food(BaseModel):
    """A food and its full nutrient panel, serving sizes, and conversion factors."""

    fdc_id: int
    description: str
    data_type: str
    nutrients: list[Nutrient] = []
    serving_sizes: list[ServingSize] = []
    conversion_factors: ConversionFactors | None = None

    def nutrient(self, code: str) -> Nutrient | None:
        """Return the nutrient matching *code* (USDA number), or None if absent."""
        for nutrient in self.nutrients:
            if nutrient.code == code:
                return nutrient
        return None
