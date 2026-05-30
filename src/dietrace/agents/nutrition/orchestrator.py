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
        if estimate.grams is None:
            continue
        meal_items.append(MealItem(food=food, grams=estimate.grams))

    return log_entry(meal_items)
