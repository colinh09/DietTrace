"""Deterministic food lookup over the read layer.

``search_nutrition(repository, food)`` is the *search* half of the mandatory
search/calculation split: it turns free text into a reproducible
``fdc_id`` plus that food's per-100 g nutrient panel and USDA ``data_type``,
read deterministically from the food DB read layer — the LLM parses and
orchestrates but never invents a number a lookup can return.

It wraps :class:`FoodRepository`: ``search`` ranks candidates (alias-aware) and
the best one's ``fdc_id`` is hydrated via ``get`` into the full per-100 g panel,
keyed by USDA number code (208 kcal, 203 protein, 204 fat, 205 carb, …), never
by name. A query that matches nothing returns ``None`` rather than
raising, keeping the agent loop fail-soft.
"""

from __future__ import annotations

from pydantic import BaseModel

from dietrace.nutrition.models import Nutrient
from dietrace.nutrition.overlay import overlay_fdc_id
from dietrace.nutrition.repository import FoodRepository


class NutritionMatch(BaseModel):
    """A resolved food: its reproducible ``fdc_id`` and per-100 g nutrients.

    ``per_100g`` is the matched food's nutrient panel as stored (amounts per
    100 g), and ``data_type`` is the USDA category (e.g. ``sr_legacy_food``,
    ``branded_food``) so downstream scoring can tell full-micro whole foods from
    label-only branded ones.
    """

    fdc_id: int
    description: str
    data_type: str
    per_100g: list[Nutrient] = []
    # Match strength from the ranked search: exact (4) > all-words (3) > prefix (2)
    # > loose substring (1). A 1 means the query was only a substring of some word
    # ("pho" in "symPHOny") — too weak to trust over a grounded web lookup.
    score: int = 0

    def nutrient(self, code: str) -> Nutrient | None:
        """Return the per-100 g nutrient for *code* (USDA number), or None."""
        for nutrient in self.per_100g:
            if nutrient.code == code:
                return nutrient
        return None


def search_nutrition(
    repository: FoodRepository, food: str, overlay: dict[str, int] | None = None
) -> NutritionMatch | None:
    """Look up *food* against the read layer, best match first.

    A curated common-foods *overlay* is consulted first: if *food* is a pinned
    common name, its hand-verified ``fdc_id`` is returned directly (score 4, the
    deterministic head-of-distribution fix). Otherwise the ranked search runs and
    the top candidate is hydrated. Returns ``None`` when nothing matches.
    """
    pinned = overlay_fdc_id(food, overlay)
    if pinned is not None:
        hydrated = repository.get(pinned)
        if hydrated is not None:
            return NutritionMatch(
                fdc_id=hydrated.fdc_id,
                description=hydrated.description,
                data_type=hydrated.data_type,
                per_100g=hydrated.nutrients,
                score=4,
            )

    candidates = repository.search(food)
    if not candidates:
        return None

    hydrated = repository.get(candidates[0].fdc_id)
    if hydrated is None:
        return None

    return NutritionMatch(
        fdc_id=hydrated.fdc_id,
        description=hydrated.description,
        data_type=hydrated.data_type,
        per_100g=hydrated.nutrients,
        score=candidates[0].score,
    )
