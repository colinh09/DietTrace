"""Deterministic meal-logging orchestration for the /log path.

Gemini parses the meal text ONCE (the only generative step); then the
search → portion → calculation pipeline runs deterministically. This is the
search/calculation split: the model never invents a number a tool can
look up, so the result is fast, reproducible, and accurate. The ADK tool-calling
agent (``build_nutrition_agent``) remains the traced "agent" artifact; this is
the production path the web ``/log`` endpoint calls.
"""

from __future__ import annotations

from typing import Any

from dietrace.agents.nutrition.estimate_portion import estimate_portion
from dietrace.agents.nutrition.log_entry import LoggedMeal, MealItem, log_entry
from dietrace.agents.nutrition.parse_meal import parse_meal
from dietrace.agents.nutrition.search_nutrition import search_nutrition
from dietrace.nutrition.models import Food
from dietrace.nutrition.repository import FoodRepository


def log_meal(
    text: str, repository: FoodRepository, *, client: Any | None = None
) -> LoggedMeal:
    """Log *text* into scaled nutrient totals via parse → search → portion → calc.

    One Gemini call parses the meal (mockable via *client*); every later step is a
    deterministic read/computation against the food DB. Items that do not resolve
    (no food match, or no gram estimate) are skipped rather than raising, so a
    partially-understood meal still logs what it can.
    """
    parsed = parse_meal(text, client=client)

    meal_items: list[MealItem] = []
    for item in parsed.items:
        match = search_nutrition(repository, item.food)
        if match is None:
            continue
        food = repository.get(match.fdc_id)
        if food is None:
            continue
        estimate = estimate_portion(food, item.quantity, item.unit)
        grams = estimate.grams
        if grams is None:
            grams = _fallback_grams(food, item.quantity)
        meal_items.append(MealItem(food=food, grams=grams))

    return log_entry(meal_items)


def _fallback_grams(food: Food, quantity: float) -> float:
    """Grams when no unit resolves: scale the food's primary serving, else 100 g.

    Better to log an approximate portion (and let the evals score it) than to drop
    the item entirely when Gemini emits a unit no serving matches (e.g. "large").
    """
    if food.serving_sizes:
        primary = food.serving_sizes[0]
        per_unit = primary.gram_weight / primary.amount if primary.amount else primary.gram_weight
        return quantity * per_unit
    return quantity * 100.0
