"""Search-resolution regression basket.

–11.3 each tuned ``_canonical_score`` so a bare common-food query
resolves to the sensible whole/raw/ingredient form rather than a non-edible
part, a prepared product, or a dehydrated variant. Those fixes are individually
covered in ``test_repository_search.py``; this module pins a *basket* of
everyday foods end-to-end through ``FoodRepository.search`` so a future ranking
edit can't silently regress one of them.

Every basket pair is an equal text match (both candidates carry the query's base
noun), so the ordering is decided purely by the canonical ranking — exactly what
these tests guard. The runner-up has the LOWER ``fdc_id`` in each fixture pair,
so absent the ranking signal it would win the tie: the assertion that the
canonical form comes first proves the ranking (not ``fdc_id`` order) decides.
"""

import pytest

from dietrace.nutrition.repository import FoodRepository
from tests.nutrition.fixtures_food_db import (
    APPLE_RAW_FDC_ID,
    APPLE_SAUCE_FDC_ID,
    CARROT_DEHYDRATED_FDC_ID,
    CARROT_RAW_FDC_ID,
    ORANGE_FDC_ID,
    ORANGE_PEEL_FDC_ID,
    PEACH_FDC_ID,
    PEACH_PIE_FDC_ID,
    RICE_COOKED_FDC_ID,
    RICE_RAW_FDC_ID,
)

# (query, canonical winner, the variant it must outrank) — one per common food
# named in , each exercising a 11.1–11.3 pattern:
#   apple  — bare ingredient beats a prepared product (sauce)        [11.2]
#   rice   — staple prefers cooked over raw                          [cooked-staple]
#   orange — whole fruit beats a non-edible part (peel)              [11.1]
#   carrot — raw produce beats a dehydrated variant                 [11.3]
#   peach  — bare ingredient beats a prepared product (pie)          [11.2]
_BASKET = [
    ("apple", APPLE_RAW_FDC_ID, APPLE_SAUCE_FDC_ID),
    ("rice", RICE_COOKED_FDC_ID, RICE_RAW_FDC_ID),
    ("orange", ORANGE_FDC_ID, ORANGE_PEEL_FDC_ID),
    ("carrot", CARROT_RAW_FDC_ID, CARROT_DEHYDRATED_FDC_ID),
    ("peach", PEACH_FDC_ID, PEACH_PIE_FDC_ID),
]


@pytest.mark.parametrize("query, winner_fdc_id, runner_up_fdc_id", _BASKET)
def test_common_food_resolves_to_canonical_match(
    food_db, query, winner_fdc_id, runner_up_fdc_id
) -> None:
    """Each common food resolves to its canonical match, ahead of the variant."""
    repo = FoodRepository(food_db)

    candidates = repo.search(query)

    assert [c.fdc_id for c in candidates] == [winner_fdc_id, runner_up_fdc_id]
    # Equal text score: only the canonical ranking separates the pair.
    assert all(c.score == candidates[0].score for c in candidates)
