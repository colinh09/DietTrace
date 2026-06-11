"""Tests for FoodRepository.search — alias-aware ranked lookup.

``FoodRepository.search(name) → candidates`` is an alias-aware, ranked lookup
over the food DB's ``foods`` and ``food_aliases`` tables. These
tests run against the tiny ``food_db`` fixture (egg, avocado, toast), never the
real ``data/food.sqlite``. A query matches a food by its description (name) or
any of its aliases; candidates come back ranked best-match-first so the
deterministic ``search_nutrition`` tool can pick a reproducible fdc_id.
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


def test_search_ranks_exact_above_allwords_above_substring(food_db) -> None:
    """Match quality: exact (4) > all-words (3) > substring (1).

    A mid-word prefix ("avo" of "Avocados", "macaron" of "Macaroni") is only a
    *substring* — prefix (2) requires a word boundary — so it scores 1 and the
    agent routes it to the grounded web lookup rather than pulling the wrong food.
    Real parsed queries are whole words, so this never bites them.
    """
    repo = FoodRepository(food_db)

    exact = repo.search("egg")  # alias "egg" equals the query
    all_words = repo.search("wheat")  # "wheat" is a whole word of "whole-wheat"
    substring = repo.search("avo")  # mid-word prefix of "Avocados" → substring tier

    assert exact[0].score == 4
    assert all_words[0].score == 3
    assert substring[0].score == 1
    assert exact[0].score > all_words[0].score > substring[0].score


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
    """"chicken breast" resolves to the cooked cut, never the deli roll.

    The raw cut, the plainly-cooked cut, and the processed deli slice all carry
    the words "chicken" and "breast", so each is an equal all-words text match.
    Meat is eaten cooked, so the canonical ranking prefers the cooked cut first
    (what the user actually ate), the raw cut next, and buries the deli product
    last — a deli roll should never outrank a plain breast.
    """
    repo = FoodRepository(food_db)

    candidates = repo.search("chicken breast")

    assert [c.fdc_id for c in candidates] == [
        CHICKEN_BREAST_COOKED_FDC_ID,
        CHICKEN_BREAST_RAW_FDC_ID,
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
    """"coffee" resolves to brewed coffee, never a branded coffee soymilk.

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


def test_canonical_scoring_meat_prefers_cooked() -> None:
    """Bare meat queries resolve to the cooked cut, not the raw one (calorie accuracy).

    People weigh and log the cooked portion, so a raw cut undercounts. Like the
    staple correction, the cooked form is canonical for flesh foods — across the
    animal noun and the cut, so "steak" and "ground beef" are covered too.
    """
    from dietrace.nutrition.repository import _canonical_score

    assert _canonical_score(
        "Chicken, broilers or fryers, breast, meat only, cooked, roasted", "chicken"
    ) > _canonical_score("Chicken, ground, raw", "chicken")
    assert _canonical_score(
        "Beef, ground, 80% lean meat / 20% fat, cooked", "ground beef"
    ) > _canonical_score("Beef, grass-fed, ground, raw", "ground beef")
    assert _canonical_score(
        "Beef, flank, steak, boneless, choice, cooked, grilled", "steak"
    ) > _canonical_score("Beef, flank, steak, boneless, choice, raw", "steak")
    assert _canonical_score(
        "Pork, fresh, loin, chops, boneless, cooked, broiled", "pork chop"
    ) > _canonical_score("Pork, fresh, loin, chops, boneless, raw", "pork chop")


def test_canonical_scoring_meat_raw_cut_still_beats_deli() -> None:
    """The cooked-meat reward must not let a deli roll outrank a plain raw cut.

    Raw meat is left neutral (not penalized), so the order is cooked cut, then
    raw cut, then the processed deli product — never deli above a plain cut.
    """
    from dietrace.nutrition.repository import _canonical_score

    raw = _canonical_score(
        "Chicken, broilers or fryers, breast, meat only, raw", "chicken breast"
    )
    deli = _canonical_score("Chicken breast, deli, sliced", "chicken breast")
    assert raw > deli


def test_canonical_scoring_meat_loses_to_no_meatless_substitute() -> None:
    """A bare meat query means the animal, not a vegetarian analogue of it."""
    from dietrace.nutrition.repository import _canonical_score

    assert _canonical_score(
        "Chicken, broilers or fryers, breast, meat only, cooked, roasted", "chicken"
    ) > _canonical_score("Chicken, meatless, breaded, fried", "chicken")
    # ...but a substitute the user explicitly asks for is not penalized.
    assert _canonical_score("Chicken, meatless", "meatless chicken") > _canonical_score(
        "Chicken, meatless, breaded, fried, with sauce", "meatless chicken"
    )


def test_canonical_scoring_meat_does_not_touch_produce_or_egg() -> None:
    """Fish, egg and produce keep the raw default — only listed meats flip."""
    from dietrace.nutrition.repository import _canonical_score

    # Egg's canonical USDA form is raw; it is not a cooked-meat.
    assert _canonical_score("Egg, whole, raw, fresh", "egg") > _canonical_score(
        "Egg, whole, cooked, hard-boiled", "egg"
    )
    # Salmon is intentionally absent from the set (sushi/sashimi are real), so it
    # keeps the raw-default preference at the canonical level.
    assert _canonical_score(
        "Fish, salmon, Atlantic, wild, raw", "salmon"
    ) > _canonical_score("Fish, salmon, Atlantic, wild, cooked, dry heat", "salmon")


def test_singularizer_handles_es_plurals() -> None:
    """The -es plurals must singularize correctly or the raw fruit/veg is excluded."""
    from dietrace.nutrition.repository import _singular

    assert _singular("potatoes") == "potato"
    assert _singular("peaches") == "peach"
    assert _singular("tomatoes") == "tomato"
    assert _singular("bananas") == "banana"  # plain -s still works
    assert _singular("grapes") == "grape"


def test_without_peel_is_the_whole_fruit_not_a_part() -> None:
    """"Lemons, raw, without peel" is the edible fruit and must beat "Lemon grass"."""
    from dietrace.nutrition.repository import _canonical_score

    assert _canonical_score("Lemons, raw, without peel", "lemon") > _canonical_score(
        "Lemon grass (citronella), raw", "lemon"
    )
    # A bare part still loses to the whole food.
    assert _canonical_score("Oranges, raw", "orange") > _canonical_score(
        "Orange peel, raw", "orange"
    )


def test_effective_score_demotes_unrequested_products() -> None:
    """An exact-alias product drops a tier so a raw whole food can outrank it."""
    from dietrace.nutrition.repository import _effective_score

    # "Carrot, dehydrated" matches exactly (4) but is demoted to 3 so raw (3) ties
    # and canonical wins it.
    assert _effective_score(4, "Carrot, dehydrated", "carrot") == 3
    assert _effective_score(4, "Chicken breast, deli, sliced", "chicken breast") == 3
    # Cooked staples are exempt; a requested product form is exempt.
    assert _effective_score(3, "Rice, white, cooked", "white rice") == 3
    assert _effective_score(3, "Potato flour", "potato flour") == 3


def test_organ_meat_loses_to_the_muscle_cut() -> None:
    """A bare animal query means the meat, not the organ ("duck" → not its liver)."""
    from dietrace.nutrition.repository import _canonical_score

    assert _canonical_score("Duck, meat only, raw", "duck") > _canonical_score(
        "Duck, liver, raw", "duck"
    )
    # But an explicitly-requested organ is not penalized.
    assert _canonical_score("Beef, liver, raw", "beef liver") > _canonical_score(
        "Beef, ribeye, raw", "beef liver"
    )
