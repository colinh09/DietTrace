"""Read-only query layer over the local SQLite food DB.

The food data itself (``data/food.sqlite``, ~3 GB, built by the obscured
``tools/`` pipeline) and its schema are gitignored; only this query layer is
tracked. ``FoodRepository.get(fdc_id)`` hydrates a :class:`Food` aggregate —
its nutrient panel keyed by USDA number code (208 kcal, 203 protein, 204 fat,
205 carb — ), serving-size gram weights, and Atwater conversion factors —
so downstream tools read nutrients by code and never by name.
``FoodRepository.search(name)`` is the alias-aware, ranked entry point that
turns free text into a reproducible ``fdc_id`` for ``get`` to hydrate.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dietrace.nutrition.models import (
    ConversionFactors,
    Food,
    Nutrient,
    SearchCandidate,
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

    def search(self, name: str) -> list[SearchCandidate]:
        """Return candidates matching *name* by description or alias, best first.

        Alias-aware: a query hits a food through its description (name)
        or any ``food_aliases`` row. Each hit is scored by match quality —
        exact (3) > prefix (2) > substring (1), case-insensitive — and the list
        is ordered by descending score, breaking ties by ``fdc_id`` so results
        are deterministic. A blank query matches nothing.
        """
        query = name.strip().lower()
        if not query:
            return []

        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            like = f"%{query}%"
            rows = conn.execute(
                """
                SELECT f.fdc_id, f.description, f.data_type
                FROM foods f
                WHERE LOWER(f.description) LIKE ?
                   OR f.fdc_id IN (
                       SELECT fdc_id FROM food_aliases
                       WHERE LOWER(alias_name) LIKE ?
                   )
                """,
                (like, like),
            ).fetchall()

            candidates = []
            for row in rows:
                aliases = [
                    r["alias_name"]
                    for r in conn.execute(
                        "SELECT alias_name FROM food_aliases WHERE fdc_id = ?",
                        (row["fdc_id"],),
                    ).fetchall()
                ]
                score, matched_on = self._best_match(
                    query, [row["description"], *aliases]
                )
                candidates.append(
                    SearchCandidate(
                        fdc_id=row["fdc_id"],
                        description=row["description"],
                        data_type=row["data_type"],
                        score=score,
                        matched_on=matched_on,
                    )
                )

            candidates.sort(key=lambda c: (-c.score, c.fdc_id))
            return candidates
        finally:
            conn.close()

    @staticmethod
    def _best_match(query: str, fields: list[str]) -> tuple[int, str]:
        """Score *query* against *fields*; return the best (score, matched text).

        Exact match scores 3, a prefix 2, any other substring 1, no match 0.
        The first field reaching the best score wins the tie, keeping the
        matched text stable.
        """
        best_score = 0
        best_field = ""
        for field in fields:
            lowered = field.lower()
            if lowered == query:
                score = 3
            elif lowered.startswith(query):
                score = 2
            elif query in lowered:
                score = 1
            else:
                score = 0
            if score > best_score:
                best_score = score
                best_field = field
        return best_score, best_field

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
