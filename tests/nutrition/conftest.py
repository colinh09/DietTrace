"""Shared fixtures for the nutrition read-layer tests."""

import sqlite3
from pathlib import Path

import pytest

from tests.nutrition.fixtures_food_db import build_food_db


@pytest.fixture
def food_db(tmp_path: Path) -> Path:
    """Build a throwaway SQLite food DB and yield its path.

    Reusable by the FoodRepository.get / .search tests (2.3 / 2.4): each gets a
    fresh, isolated file under the test's ``tmp_path``, seeded with the fixture
    foods (egg, avocado, toast) and never the real ``data/food.sqlite``.
    """
    db_path = tmp_path / "food.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        build_food_db(conn)
    finally:
        conn.close()
    return db_path
