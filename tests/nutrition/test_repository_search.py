"""Tests for FoodRepository.search — alias-aware ranked lookup (2.4; ).

 mandates ``FoodRepository.search(name) → candidates`` as an "alias-aware,
ranked" lookup over the food DB's ``foods`` and ``food_aliases`` tables. These
tests run against the tiny ``food_db`` fixture (egg, avocado, toast), never the
real ``data/food.sqlite``. A query matches a food by its description (name) or
any of its aliases; candidates come back ranked best-match-first so the
deterministic ``search_nutrition`` tool (3.3) can pick a reproducible fdc_id.
"""

from dietrace.nutrition.models import SearchCandidate
from dietrace.nutrition.repository import FoodRepository
from tests.nutrition.fixtures_food_db import (
    AVOCADO_FDC_ID,
    CARROT_DEHYDRATED_FDC_ID,
    CARROT_RAW_FDC_ID,
    CHICKEN_BREAST_COOKED_FDC_ID,
    CHICKEN_BREAST_RAW_FDC_ID,
    CHICKEN_DELI_FDC_ID,
    COFFEE_BREWED_FDC_ID,
    COFFEE_SOYMILK_FDC_ID,
    EGG_FDC_ID,
    ORANGE_FDC_ID,
    ORANGE_PEEL_FDC_ID,
    PEACH_FDC_ID,
    PEACH_PIE_FDC_ID,
    POTATO_FDC_ID,
    SWEET_POTATO_LEAVES_FDC_ID,
    TOAST_FDC_ID,
)


def test_search_matches_by_name(food_db) -> None:
    """A word in the description (name) finds the food."""
    repo = FoodRepository(food_db)

    candidates = repo.search("bread")

    assert [c.fdc_id for c in candidates] == [TOAST_FDC_ID]
    top = candidates[0]
    assert isinstance(top, SearchCandidate)
    assert top.description == "Bread, whole-wheat, commercially prepared"
    assert top.data_type == "sr_legacy_food"
    assert top.matched_on == "Bread, whole-wheat, commercially prepared"


def test_search_matches_by_alias(food_db) -> None:
    """A query that hits only an alias (not the description) still finds the food."""
    repo = FoodRepository(food_db)

    # "eggs" is an alias of the egg; its description ("Egg, whole, raw, fresh")
    # does not contain the substring "eggs", so this is an alias-only match.
    candidates = repo.search("eggs")

    assert [c.fdc_id for c in candidates] == [EGG_FDC_ID]
    assert candidates[0].matched_on == "eggs"


def test_search_is_case_insensitive(food_db) -> None:
    """Matching ignores case on both the query and the stored text."""
    repo = FoodRepository(food_db)

    assert [c.fdc_id for c in repo.search("AVOCADO")] == [AVOCADO_FDC_ID]


def test_search_ranks_exact_above_allwords_above_prefix(food_db) -> None:
    """Match quality: exact (4) > all-words (3) > prefix (2)."""
    repo = FoodRepository(food_db)

    exact = repo.search("egg")  # alias "egg" equals the query
    all_words = repo.search("wheat")  # "wheat" is a whole word of "whole-wheat"
    prefix = repo.search("avo")  # "Avocados"/"avocado" start with, but isn't, "avo"

    assert exact[0].score == 4
    assert all_words[0].score == 3
    assert prefix[0].score == 2
    assert exact[0].score > all_words[0].score > prefix[0].score


def test_search_finds_multi_word_query_regardless_of_order(food_db) -> None:
    """Every query word need only appear in the description (any order)."""
    repo = FoodRepository(food_db)

    # "wheat bread" matches "Bread, whole-wheat, ..." though the words are split.
    candidates = repo.search("wheat bread")

    assert [c.fdc_id for c in candidates] == [TOAST_FDC_ID]
    assert candidates[0].score == 3  # all query words present


def test_search_prefers_canonical_on_ties(food_db) -> None:
    """On an equal text score, the raw/simpler food ranks first.

    "whole" is an all-words match for both the egg ("Egg, whole, raw, fresh")
    and the toast ("Bread, whole-wheat, commercially prepared"); the egg wins
    the tie because it is "raw" and carries no processed terms.
    """
    repo = FoodRepository(food_db)

    candidates = repo.search("whole")

    assert [c.fdc_id for c in candidates] == [EGG_FDC_ID, TOAST_FDC_ID]
    assert all(c.score == candidates[0].score for c in candidates)


def test_search_chicken_breast_prefers_plain_cut_over_deli(food_db) -> None:
    """"chicken breast" resolves to a plain cut, never the deli roll.

    The raw cut, the plainly-cooked cut, and the processed deli slice all carry
    the words "chicken" and "breast", so each is an equal all-words text match.
    The canonical ranking must then prefer the raw cut first, the cooked cut
    next, and bury the deli product last — a deli roll should never outrank a
    plainly-cooked breast just because it has fewer cooking words.
    """
    repo = FoodRepository(food_db)

    candidates = repo.search("chicken breast")

    assert [c.fdc_id for c in candidates] == [
        CHICKEN_BREAST_RAW_FDC_ID,
        CHICKEN_BREAST_COOKED_FDC_ID,
        CHICKEN_DELI_FDC_ID,
    ]
    assert all(c.score == candidates[0].score for c in candidates)
    assert candidates[-1].fdc_id == CHICKEN_DELI_FDC_ID


def test_search_orange_prefers_fruit_over_peel(food_db) -> None:
    """"orange" resolves to the fruit, never the non-edible peel.

    Both "Oranges, raw, ..." and "Orange peel, raw" carry the base noun and are
    "raw", so each is an equal all-words text match; only the part-penalty on
    "peel" keeps the fruit ranked above its peel.
    """
    repo = FoodRepository(food_db)

    candidates = repo.search("orange")

    assert [c.fdc_id for c in candidates] == [ORANGE_FDC_ID, ORANGE_PEEL_FDC_ID]
    assert all(c.score == candidates[0].score for c in candidates)


def test_search_potato_prefers_tuber_over_leaves(food_db) -> None:
    """"potato" resolves to the tuber, not the leaves; "flesh and skin" is whole.

    The tuber's description says "flesh and skin", which names the whole food —
    that "skin" must not be read as a non-edible part. "Sweet potato leaves" is a
    part and is penalized, so the tuber ranks first.
    """
    repo = FoodRepository(food_db)

    candidates = repo.search("potato")

    assert [c.fdc_id for c in candidates] == [
        POTATO_FDC_ID,
        SWEET_POTATO_LEAVES_FDC_ID,
    ]


def test_search_peach_prefers_fruit_over_pie(food_db) -> None:
    """"peach" resolves to the fruit, never the prepared pie.

    Both “Peach, raw” and “Pie, peach” carry the word “peach” and are equal
    all-words text matches; the pie is a prepared product whose primary noun is
    "pie", so it must rank below the bare fruit.
    """
    repo = FoodRepository(food_db)

    candidates = repo.search("peach")

    assert [c.fdc_id for c in candidates] == [PEACH_FDC_ID, PEACH_PIE_FDC_ID]
    assert all(c.score == candidates[0].score for c in candidates)


def test_search_coffee_prefers_brewed_over_branded_soymilk(food_db) -> None:
    """"coffee" resolves to brewed coffee, never a branded coffee soymilk (11.2).

    "Coffee, brewed" and the branded "Coffee soymilk" both carry "coffee" and
    tie on text relevance; without a product-form penalty the soymilk (the lower
    fdc_id) would win the tie. Penalizing the "soymilk" product form keeps the
    plain brewed ingredient on top.
    """
    repo = FoodRepository(food_db)

    candidates = repo.search("coffee")

    assert [c.fdc_id for c in candidates] == [
        COFFEE_BREWED_FDC_ID,
        COFFEE_SOYMILK_FDC_ID,
    ]
    assert all(c.score == candidates[0].score for c in candidates)


def test_canonical_scoring_product_forms_lose_to_ingredient() -> None:
    """A bare ingredient outranks a prepared/branded product of it."""
    from dietrace.nutrition.repository import _canonical_score

    # A prepared pie loses to the bare fruit.
    assert _canonical_score("Peaches, raw", "peach") > _canonical_score(
        "Pie, peach", "peach"
    )
    # A branded coffee soymilk loses to brewed coffee even though both lead with
    # the ingredient word — the unrequested "soymilk" product form is penalized.
    assert _canonical_score("Coffee, brewed", "coffee") > _canonical_score(
        "Coffee soymilk", "coffee"
    )
    # A sauce / candy product loses to the bare ingredient too.
    assert _canonical_score("Apples, raw", "apple") > _canonical_score(
        "Sauce, apple", "apple"
    )
    # But a product the user explicitly asked for is NOT penalized: "peach pie"
    # scores the pie higher than the bare-ingredient query "peach" does.
    assert _canonical_score("Pie, peach", "peach pie") > _canonical_score(
        "Pie, peach", "peach"
    )


def test_canonical_scoring_parts_lose_to_whole() -> None:
    """Non-edible parts (peel, rind, leaves, stalk, skin) rank below the whole."""
    from dietrace.nutrition.repository import _canonical_score

    assert _canonical_score("Oranges, raw", "orange") > _canonical_score(
        "Orange peel, raw", "orange"
    )
    assert _canonical_score("Lemon, raw", "lemon") > _canonical_score(
        "Lemon peel, raw", "lemon"
    )
    # "flesh and skin" is the whole tuber, so it must outrank a leaf part and
    # must not itself be penalized for the word "skin".
    assert _canonical_score(
        "Potato, raw, flesh and skin", "potato"
    ) > _canonical_score("Sweet potato leaves, raw", "potato")
    # USDA's whole-fruit names "with skin" / "without skin" describe the edible
    # food, so they must not be read as a bare "skin" part.
    assert _canonical_score("Apples, raw, with skin", "apple") > _canonical_score(
        "Apple peel, raw", "apple"
    )


def test_search_carrot_prefers_raw_over_dehydrated(food_db) -> None:
    """"carrot" resolves to the raw form, never the dehydrated one.

    "Carrots, raw" and "Carrots, dehydrated" both carry the base noun "carrot"
    and tie on text relevance; the dehydrated variant has the lower fdc_id, so
    absent a ranking signal it would win the tie. The raw-preference (and the
    "dehydrated" processed-term penalty) keeps the raw produce on top — a
    non-staple fruit/veg is eaten raw, not dried.
    """
    repo = FoodRepository(food_db)

    candidates = repo.search("carrot")

    assert [c.fdc_id for c in candidates] == [
        CARROT_RAW_FDC_ID,
        CARROT_DEHYDRATED_FDC_ID,
    ]
    assert all(c.score == candidates[0].score for c in candidates)


def test_canonical_scoring_raw_produce_beats_dehydrated() -> None:
    """Raw non-staple produce outranks its dehydrated/dried form.

    The dry/processed penalties order produce correctly while leaving the staple
    cooked-preference intact: a staple still prefers cooked over its dry form.
    """
    from dietrace.nutrition.repository import _canonical_score

    # Non-staple produce: raw beats both dehydrated and dried.
    assert _canonical_score("Carrots, raw", "carrot") > _canonical_score(
        "Carrots, dehydrated", "carrot"
    )
    assert _canonical_score("Apricots, raw", "apricot") > _canonical_score(
        "Apricots, dehydrated", "apricot"
    )
    assert _canonical_score("Carrots, raw", "carrot") > _canonical_score(
        "Carrots, dried", "carrot"
    )
    # No regression: a staple still prefers cooked over its dry form, so the
    # produce penalties did not flip the staple correction.
    assert _canonical_score("Rice, white, cooked", "white rice") > _canonical_score(
        "Rice, white, raw, enriched", "white rice"
    )


def test_search_no_match_returns_empty(food_db) -> None:
    """A query nothing matches yields an empty list, not an error."""
    repo = FoodRepository(food_db)

    assert repo.search("quinoa") == []


def test_search_blank_query_returns_empty(food_db) -> None:
    """A blank/whitespace query matches nothing rather than every food."""
    repo = FoodRepository(food_db)

    assert repo.search("   ") == []


def test_canonical_scoring_corrections() -> None:
    """The two ranking fixes: staples prefer cooked, and head-noun beats compound."""
    from dietrace.nutrition.repository import _canonical_score

    # Staples (rice, oats, pasta) are eaten cooked → cooked outranks raw.
    assert _canonical_score("Rice, white, cooked", "white rice") > _canonical_score(
        "Rice, white, raw, enriched", "white rice"
    )
    # Non-staples keep the raw preference.
    assert _canonical_score("Broccoli, raw", "broccoli") > _canonical_score(
        "Broccoli, cooked, boiled", "broccoli"
    )
    # The query's base food (head noun) beats an unrelated hyphenated compound.
    assert _canonical_score("Apples, raw, without skin", "apple") > _canonical_score(
        "Rose-apples, raw", "apple"
    )
    assert _canonical_score("Bananas, raw", "banana") > _canonical_score(
        "Pepper, banana, raw", "banana"
    )
