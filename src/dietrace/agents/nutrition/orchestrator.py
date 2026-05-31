"""Deterministic meal-logging orchestration for the /log path.

Gemini parses the meal text ONCE (the only generative step); then the
search → portion → calculation pipeline runs deterministically. This is the
search/calculation split: the model never invents a number a tool can
look up, so the result is fast, reproducible, and accurate. The ADK tool-calling
agent (``build_nutrition_agent``) remains the traced "agent" artifact; this is
the production path the web ``/log`` endpoint calls.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from dietrace.agents.nutrition.estimate_portion import (
    estimate_portion,
    representative_serving,
)
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


def stream_meal(
    text: str, repository: FoodRepository, *, client: Any | None = None
) -> Iterator[dict[str, Any]]:
    """Run the meal pipeline as a live event stream — one event per step.

    Mirrors :func:`log_meal` step for step, but yields as it goes so the UI can
    show the agent's work as it happens: a ``parse_meal`` start then its result,
    then per-food ``search_nutrition`` + ``estimate_portion``, then ``log_entry``.
    The final ``{"type": "result"}`` event carries the same {per_item, totals,
    trace} a /log call returns.
    """
    trace: list[dict[str, Any]] = []

    def step(**fields: Any) -> dict[str, Any]:
        event = {"type": "step", **fields}
        trace.append(event)
        return event

    yield step(step="parse_meal", status="running", summary="reading your meal…")
    parsed = parse_meal(text, client=client)
    foods = [item.food for item in parsed.items]
    plural = "" if len(foods) == 1 else "s"
    yield step(
        step="parse_meal",
        status="done",
        summary=f"{len(foods)} food{plural} recognized",
        foods=foods,
    )

    meal_items: list[MealItem] = []
    for item in parsed.items:
        match = search_nutrition(repository, item.food)
        if match is None:
            yield step(
                step="search_nutrition",
                status="done",
                food=item.food,
                summary=f"no match for “{item.food}”",
            )
            continue
        food = repository.get(match.fdc_id)
        if food is None:
            continue
        yield step(
            step="search_nutrition",
            status="done",
            food=item.food,
            matched=match.description,
            fdc_id=match.fdc_id,
            summary=f"{item.food} → {match.description}",
        )
        estimate = estimate_portion(food, item.quantity, item.unit)
        grams = estimate.grams
        if grams is None:
            grams = _fallback_grams(food, item.quantity)
        yield step(
            step="estimate_portion",
            status="done",
            food=item.food,
            grams=grams,
            summary=f"{item.food} → {grams:.0f} g",
        )
        meal_items.append(MealItem(food=food, grams=grams))

    logged = log_entry(meal_items)
    totals = [n.model_dump() for n in logged.totals]
    per_item = [i.model_dump() for i in logged.per_item]
    yield step(step="log_entry", status="done", summary="totals computed", totals=totals)
    yield {"type": "result", "per_item": per_item, "totals": totals, "trace": trace}


def _fallback_grams(food: Food, quantity: float) -> float:
    """Grams when no unit resolves: scale the food's primary serving, else 100 g.

    Better to log an approximate portion (and let the evals score it) than to drop
    the item entirely when Gemini emits a unit no serving matches (e.g. "large").
    Prefers the food's edible/NLEA serving over an oversized package one.
    """
    primary = representative_serving(food.serving_sizes)
    if primary:
        per_unit = primary.gram_weight / primary.amount if primary.amount else primary.gram_weight
        return quantity * per_unit
    return quantity * 100.0
