"""Measure food-name resolution accuracy (recall@1) against the curated overlay.

The curated common-foods overlay (``mappings/common_foods.json``) doubles as a
labeled eval set: each ``name → canonical fdc_id`` is a ground-truth pair. This
script reports recall@1 for the **ranked search alone** (overlay off — the honest
measure of the lexical retrieval) and **with the overlay** (the shipped behavior),
so future retrieval work (FNDDS, hybrid BM25+embeddings) can be measured against a
fixed number instead of eyeballed.

    set -a && . ./.env && set +a
    python scripts/measure_resolution.py
"""

from __future__ import annotations

import os

from dietrace.agents.nutrition.search_nutrition import search_nutrition
from dietrace.nutrition.overlay import load_overlay
from dietrace.nutrition.repository import FoodRepository


def main() -> None:
    repo = FoodRepository(os.environ.get("DIETRACE_FOOD_DB", "data/food.sqlite"))
    truth = load_overlay()
    if not truth:
        print("No overlay/ground-truth found.")
        return

    ranked_hits = 0
    overlay_hits = 0
    misses: list[str] = []
    for name, expected in sorted(truth.items()):
        ranked = search_nutrition(repo, name, overlay={})  # overlay disabled
        if ranked is not None and ranked.fdc_id == expected:
            ranked_hits += 1
        else:
            misses.append(name)
        pinned = search_nutrition(repo, name)  # shipped behavior (overlay on)
        if pinned is not None and pinned.fdc_id == expected:
            overlay_hits += 1

    n = len(truth)
    print(f"cases: {n}")
    print(f"ranked search alone : recall@1 = {ranked_hits}/{n} = {ranked_hits / n:.1%}")
    print(f"with curated overlay: recall@1 = {overlay_hits}/{n} = {overlay_hits / n:.1%}")
    print(f"\nranked-search misses ({len(misses)}): {', '.join(misses)}")


if __name__ == "__main__":
    main()
