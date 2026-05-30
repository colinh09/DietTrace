"""Read-only query layer over the local SQLite food DB.

The food data itself (``data/food.sqlite``, ~3 GB, built by the obscured
``tools/`` pipeline) and its schema are gitignored; only this query layer is
tracked. ``FoodRepository.get(fdc_id)`` hydrates a :class:`Food` aggregate —
its nutrient panel keyed by USDA number code (208 kcal, 203 protein, 204 fat,
205 carb — ), serving-size gram weights, and Atwater conversion factors —
so downstream tools read nutrients by code and never by name.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dietrace.nutrition.models import (
    ConversionFactors,
    Food,
    Nutrient,
    ServingSize,
)


class FoodRepository:
    """Read-only accessor over the food DB at *db_path*."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)

    def get(self, fdc_id: int) -> Food | None:
        """Return the :class:`Food` for *fdc_id*, or None if it is absent."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT fdc_id, description, data_type FROM foods WHERE fdc_id = ?",
                (fdc_id,),
            ).fetchone()
            if row is None:
                return None

            return Food(
                fdc_id=row["fdc_id"],
                description=row["description"],
                data_type=row["data_type"],
                nutrients=self._nutrients(conn, fdc_id),
                serving_sizes=self._serving_sizes(conn, fdc_id),
                conversion_factors=self._conversion_factors(conn, fdc_id),
            )
        finally:
            conn.close()

    @staticmethod
    def _nutrients(conn: sqlite3.Connection, fdc_id: int) -> list[Nutrient]:
        rows = conn.execute(
            """
            SELECT n.code, n.name, fn.amount, n.unit
            FROM food_nutrients fn
            JOIN nutrients n ON n.nutrient_id = fn.nutrient_id
            WHERE fn.fdc_id = ?
            ORDER BY n.code
            """,
            (fdc_id,),
        ).fetchall()
        return [
            Nutrient(code=r["code"], name=r["name"], amount=r["amount"], unit=r["unit"])
            for r in rows
        ]

    @staticmethod
    def _serving_sizes(conn: sqlite3.Connection, fdc_id: int) -> list[ServingSize]:
        rows = conn.execute(
            """
            SELECT amount, unit, gram_weight, description
            FROM serving_sizes
            WHERE fdc_id = ?
            ORDER BY sequence_number
            """,
            (fdc_id,),
        ).fetchall()
        return [
            ServingSize(
                amount=r["amount"],
                unit=r["unit"],
                gram_weight=r["gram_weight"],
                description=r["description"],
            )
            for r in rows
        ]

    @staticmethod
    def _conversion_factors(
        conn: sqlite3.Connection, fdc_id: int
    ) -> ConversionFactors | None:
        row = conn.execute(
            """
            SELECT protein_factor, fat_factor, carbohydrate_factor
            FROM nutrient_conversion_factors
            WHERE fdc_id = ?
            """,
            (fdc_id,),
        ).fetchone()
        if row is None:
            return None
        return ConversionFactors(
            protein=row["protein_factor"],
            fat=row["fat_factor"],
            carbohydrate=row["carbohydrate_factor"],
        )
