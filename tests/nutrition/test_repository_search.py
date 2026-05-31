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
    EGG_FDC_ID,
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


def test_search_no_match_returns_empty(food_db) -> None:
    """A query nothing matches yields an empty list, not an error."""
    repo = FoodRepository(food_db)

    assert repo.search("quinoa") == []


def test_search_blank_query_returns_empty(food_db) -> None:
    """A blank/whitespace query matches nothing rather than every food."""
    repo = FoodRepository(food_db)

    assert repo.search("   ") == []
