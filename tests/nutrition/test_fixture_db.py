"""Tests for the tiny fixture food DB.

The real food DB (``data/food.sqlite``, 3 GB, built by the obscured ``tools/``
pipeline) is never touched by tests. Instead a ``food_db`` pytest fixture builds
a throwaway SQLite file with a handful of whole foods — an egg and an avocado
among them — so the read-layer tests (FoodRepository.get / .search) have
deterministic ground truth without the real data. This module pins that the
fixture creates the expected tables and rows and is reusable by other tests.
"""

import sqlite3

from tests.nutrition.fixtures_food_db import (
    AVOCADO_FDC_ID,
    EGG_FDC_ID,
    FIXTURE_FDC_IDS,
    TOAST_FDC_ID,
)

_EXPECTED_TABLES = {
    "foods",
    "nutrients",
    "food_nutrients",
    "serving_sizes",
    "nutrient_conversion_factors",
    "food_aliases",
}


def test_fixture_creates_expected_tables(food_db) -> None:
    """The fixture builds the read-layer schema."""
    conn = sqlite3.connect(food_db)
    try:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        conn.close()

    assert _EXPECTED_TABLES <= names


def test_fixture_seeds_egg_and_avocado(food_db) -> None:
    """The seeded foods include an egg and an avocado, keyed by fdc_id."""
    conn = sqlite3.connect(food_db)
    try:
        rows = dict(conn.execute("SELECT fdc_id, description FROM foods"))
    finally:
        conn.close()

    assert set(rows) == set(FIXTURE_FDC_IDS)
    assert "egg" in rows[EGG_FDC_ID].lower()
    assert "avocado" in rows[AVOCADO_FDC_ID].lower()


def test_fixture_nutrients_join_by_code(food_db) -> None:
    """Each food's nutrients are reachable by USDA number code."""
    conn = sqlite3.connect(food_db)
    try:
        energy = conn.execute(
            """
            SELECT fn.amount
            FROM food_nutrients fn
            JOIN nutrients n ON n.nutrient_id = fn.nutrient_id
            WHERE fn.fdc_id = ? AND n.code = '208'
            """,
            (EGG_FDC_ID,),
        ).fetchone()
    finally:
        conn.close()

    assert energy is not None
    assert energy[0] == 143.0


def test_fixture_has_serving_sizes_and_aliases(food_db) -> None:
    """Serving sizes (gram weights) and aliases are seeded for search/portion."""
    conn = sqlite3.connect(food_db)
    try:
        serving = conn.execute(
            "SELECT amount, unit, gram_weight FROM serving_sizes WHERE fdc_id = ?",
            (EGG_FDC_ID,),
        ).fetchone()
        aliases = {
            row[0]
            for row in conn.execute(
                "SELECT alias_name FROM food_aliases WHERE fdc_id = ?",
                (AVOCADO_FDC_ID,),
            )
        }
    finally:
        conn.close()

    assert serving == (1.0, "large", 50.0)
    assert "avocado" in {a.lower() for a in aliases}


def test_fixture_has_conversion_factors(food_db) -> None:
    """Atwater conversion factors are seeded where USDA provides them."""
    conn = sqlite3.connect(food_db)
    try:
        factors = conn.execute(
            """
            SELECT protein_factor, fat_factor, carbohydrate_factor
            FROM nutrient_conversion_factors
            WHERE fdc_id = ?
            """,
            (EGG_FDC_ID,),
        ).fetchone()
    finally:
        conn.close()

    assert factors == (4.36, 9.02, 3.68)


def test_fixture_is_isolated_under_tmp_path(food_db, tmp_path) -> None:
    """The fixture yields a real file under the test's own tmp path."""
    assert str(food_db).startswith(str(tmp_path))


def test_fixture_seeds_the_third_food(food_db) -> None:
    """The non-egg/avocado food (toast) is seeded too, not just declared."""
    conn = sqlite3.connect(food_db)
    try:
        toast = conn.execute(
            "SELECT description FROM foods WHERE fdc_id = ?", (TOAST_FDC_ID,)
        ).fetchone()
    finally:
        conn.close()

    assert TOAST_FDC_ID in FIXTURE_FDC_IDS
    assert toast is not None
    assert "bread" in toast[0].lower()
