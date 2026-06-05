"""Deterministic meal-logging orchestration for the /log path.

Gemini parses the meal text ONCE (the only generative step); then the
search → portion → calculation pipeline runs deterministically. This is the
search/calculation split: the model never invents a number a tool can
look up, so the result is fast, reproducible, and accurate. The ADK tool-calling
agent (``build_nutrition_agent``) remains the traced "agent" artifact; this is
the production path the web ``/log`` endpoint calls.

When the USDA DB can't honor a *branded* item (it rarely carries restaurant
meals), resolution falls back to a grounded web lookup (``web_nutrition``) rather
than logging some other chain's lookalike — the one place the agent reads a
number it didn't compute, kept narrow and fail-soft.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from typing import Any

from dietrace.agents.nutrition.estimate_portion import (
    estimate_portion,
    representative_serving,
)
from dietrace.agents.nutrition.log_entry import LoggedMeal, MealItem, log_entry
from dietrace.agents.nutrition.parse_meal import ParsedItem, parse_meal
from dietrace.agents.nutrition.search_nutrition import search_nutrition
from dietrace.agents.nutrition.web_nutrition import web_nutrition
from dietrace.nutrition.models import Food
from dietrace.nutrition.repository import FoodRepository

# A web lookup: (food, brand, client) -> a synthetic Food or None. Injectable so
# the orchestration logic is testable without a live grounded call.
WebLookup = Callable[[str, str, Any | None], Food | None]


def _default_web_lookup(food: str, brand: str, client: Any | None) -> Food | None:
    return web_nutrition(food, brand, client=client)


def _brand_satisfied(brand: str, description: str) -> bool:
    """True when every significant word of *brand* appears in *description*.

    The signal that a DB match actually *is* the branded item the user named: a
    search for "bacon cheeseburger" happily returns McDonald's, but its
    description won't contain "five" and "guys", so a Five Guys order is correctly
    judged unsatisfied and routed to the web. Short tokens (≤2 chars) are ignored
    so "in"/"n'" style filler doesn't decide the match.
    """
    brand_tokens = {t for t in re.findall(r"[a-z0-9]+", brand.lower()) if len(t) > 2}
    if not brand_tokens:
        return True  # no brand named — the plain DB match stands
    desc_tokens = set(re.findall(r"[a-z0-9]+", description.lower()))
    return brand_tokens <= desc_tokens


def _resolve_food(
    repository: FoodRepository,
    item: ParsedItem,
    web_lookup: WebLookup,
    client: Any | None,
) -> tuple[Food | None, str, str | None]:
    """Resolve one parsed item to a ``(Food, source, label)`` the pipeline can log.

    Prefers a USDA DB match; for a branded item the DB can't honor, or one it
    misses entirely, falls back to the grounded web lookup. Keeps the DB match as a
    last resort over dropping the item. ``source`` is "usda" | "web" | "none".
    """
    match = search_nutrition(repository, item.food)
    usda_food = repository.get(match.fdc_id) if match else None

    # A strong DB match that honors any named brand wins. A substring-only match
    # (score 1, e.g. "pho" → a candy bar via "symPHOny") is too weak to trust.
    if match and usda_food and match.score > 1 and _brand_satisfied(item.brand, match.description):
        return usda_food, "usda", match.description

    # No confident DB match (weak/absent), or a brand the DB didn't honor — try the web.
    web_food = web_lookup(item.food, item.brand, client)
    if web_food is not None:
        return web_food, "web", web_food.description

    if usda_food and match:
        return usda_food, "usda", match.description  # weak match beats dropping it
    return None, "none", None


def _grams_for(food: Food, item: ParsedItem) -> tuple[float, str]:
    """Grams and a plain-English basis for *item* against *food*.

    Returns ``(grams, basis)`` — the basis explains which serving or measure
    was used so the UI can show "why this food got Xg".
    """
    estimate = estimate_portion(food, item.quantity, item.unit)
    if estimate.grams is not None:
        return estimate.grams, estimate.basis
    # estimate_portion couldn't resolve the unit — fall back to the food's
    # reference serving (or 100 g/unit when no servings are listed).
    grams = _fallback_grams(food, item.quantity)
    primary = representative_serving(food.serving_sizes)
    if primary:
        serving_label = primary.description or primary.unit or "serving"
        basis = f"unit unresolved → reference serving ({serving_label})"
    else:
        basis = "unit unresolved → estimated 100 g/unit"
    return grams, basis


def log_meal(
    text: str,
    repository: FoodRepository,
    *,
    client: Any | None = None,
    web_lookup: WebLookup = _default_web_lookup,
    examples: list[dict[str, Any]] | None = None,
) -> LoggedMeal:
    """Log *text* into scaled nutrient totals via parse → search → portion → calc.

    One Gemini call parses the meal (mockable via *client*, steered by the user's
    few-shot *examples* when given); each item then resolves against the food DB,
    falling back to a grounded web lookup for a branded item the DB can't honor.
    Items that resolve to nothing are skipped rather than raising, so a
    partially-understood meal still logs what it can.
    """
    parsed = parse_meal(text, client=client, examples=examples)

    meal_items: list[MealItem] = []
    for item in parsed.items:
        food, _source, _label = _resolve_food(repository, item, web_lookup, client)
        if food is None:
            continue
        grams, basis = _grams_for(food, item)
        meal_items.append(MealItem(food=food, grams=grams, portion_basis=basis))

    return log_entry(meal_items)


def stream_meal(
    text: str,
    repository: FoodRepository,
    *,
    client: Any | None = None,
    web_lookup: WebLookup = _default_web_lookup,
    examples: list[dict[str, Any]] | None = None,
) -> Iterator[dict[str, Any]]:
    """Run the meal pipeline as a live event stream — one event per step.

    Mirrors :func:`log_meal` step for step, but yields as it goes so the UI can
    show the agent's work as it happens: a ``parse_meal`` start then its result,
    then per-food ``search_nutrition`` (and a ``web_search`` step when the item
    falls back to the grounded lookup) + ``estimate_portion``, then ``log_entry``.
    The final ``{"type": "result"}`` event carries the same {per_item, totals,
    trace} a /log call returns.
    """
    trace: list[dict[str, Any]] = []

    def step(**fields: Any) -> dict[str, Any]:
        event = {"type": "step", **fields}
        trace.append(event)
        return event

    yield step(step="parse_meal", status="running", summary="reading your meal…")
    parsed = parse_meal(text, client=client, examples=examples)
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
        food, source, label = _resolve_food(repository, item, web_lookup, client)
        if food is None:
            yield step(
                step="search_nutrition",
                status="done",
                food=item.food,
                summary=f"no match for “{item.food}”",
            )
            continue

        named = f"{item.brand} {item.food}".strip() if item.brand else item.food
        if source == "web":
            yield step(
                step="search_nutrition",
                status="done",
                food=item.food,
                summary=f"“{named}” isn't in USDA — searching the web",
            )
            yield step(
                step="web_search",
                status="done",
                food=item.food,
                matched=label,
                summary=f"{named} → {label}",
            )
        else:
            yield step(
                step="search_nutrition",
                status="done",
                food=item.food,
                matched=label,
                fdc_id=food.fdc_id,
                summary=f"{named} → {label}",
            )

        grams, basis = _grams_for(food, item)
        yield step(
            step="estimate_portion",
            status="done",
            food=item.food,
            grams=grams,
            basis=basis,
            summary=f"{item.food} → {grams:.0f} g",
        )
        meal_items.append(MealItem(food=food, grams=grams, portion_basis=basis))

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
