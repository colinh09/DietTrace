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

import re
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
        if not Path(self._db_path).exists():
            return None
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

        Word-aware and canonical-preferring: a food matches when every
        query word appears in its description, or an alias matches the query.
        Each hit is scored by match quality — exact (4) > all-words (3) >
        prefix (2) > substring (1) — and ties break toward the most canonical
        food (raw/whole, fewer processed terms, shorter name) then by ``fdc_id``.
        So "broccoli" resolves to "Broccoli, raw" over a cooked variant and
        "greek yogurt" finds "Yogurt, Greek" despite the word order. A blank query
        matches nothing.
        """
        query = name.strip().lower()
        if not query:
            return []
        if not Path(self._db_path).exists():
            return []
        words = query.split()

        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            # Candidates: every query word present in the description, OR an alias
            # containing the whole query (aliases are word-tokenized at build).
            where_words = " AND ".join("LOWER(f.description) LIKE ?" for _ in words)
            rows = conn.execute(
                f"""
                SELECT f.fdc_id, f.description, f.data_type
                FROM foods f
                WHERE ({where_words})
                   OR f.fdc_id IN (
                       SELECT fdc_id FROM food_aliases WHERE LOWER(alias_name) LIKE ?
                   )
                """,
                (*(f"%{w}%" for w in words), f"%{query}%"),
            ).fetchall()

            ranked: list[tuple[int, float, SearchCandidate]] = []
            for row in rows:
                aliases = [
                    r["alias_name"]
                    for r in conn.execute(
                        "SELECT alias_name FROM food_aliases WHERE fdc_id = ?",
                        (row["fdc_id"],),
                    ).fetchall()
                ]
                score, matched_on = _text_score(query, [row["description"], *aliases])
                if score == 0:
                    continue
                ranked.append(
                    (
                        score,
                        _canonical_score(row["description"], query),
                        SearchCandidate(
                            fdc_id=row["fdc_id"],
                            description=row["description"],
                            data_type=row["data_type"],
                            score=score,
                            matched_on=matched_on,
                        ),
                    )
                )

            ranked.sort(key=lambda r: (-r[0], -r[1], r[2].fdc_id))
            return [candidate for _, _, candidate in ranked]
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


# Terms marking a processed / non-canonical food form; their presence lowers a
# candidate's rank so a plain "raw"/"whole" food wins over prepared variants.
_PROCESSED_TERMS = frozenset({
    "cooked", "boiled", "roasted", "fried", "baked", "grilled", "steamed",
    "braised", "dried", "dehydrated", "frozen", "canned", "dry", "honey",
    "salted", "unsalted", "sweetened", "sweet", "flavor", "flavored", "powder",
    "juice", "milk", "sliced", "formulated", "reduced", "nonfat",
    "lowfat", "drained", "prepared", "commercially", "mesquite", "smoked",
    "seasoned", "rotisserie", "creamed", "candied", "pickled", "instant",
    "concentrate", "puree", "pureed", "powdered",
})

# Terms marking a deli / luncheon-meat product (a processed roll or slice). These
# are penalized harder than a plain cooking method so "chicken breast" resolves
# to a raw or plainly-cooked cut rather than a deli roll: a
# deli item must not outrank a cooked cut merely for having fewer cooking words.
_DELI_TERMS = frozenset({
    "deli", "luncheon", "lunchmeat", "roll", "loaf", "spread", "patty",
    "nugget", "prepackaged",
})

# Staple grains/legumes are eaten cooked, so for THESE foods "cooked" is the
# canonical form and "raw"/"dry" is the wrong one — the opposite of the default
# raw-preference (which is right for fruit, veg, nuts). So "a cup of white rice"
# resolves to cooked rice (~205 kcal), not raw rice (~700 kcal).
_COOKED_STAPLES = frozenset({
    "rice", "pasta", "spaghetti", "macaroni", "noodle", "noodles", "oat", "oats",
    "oatmeal", "lentil", "lentils", "bean", "beans", "quinoa", "barley", "grits",
    "couscous", "bulgur", "farro", "millet", "cornmeal", "polenta",
})
_DRY_TERMS = frozenset({"raw", "dry", "dried", "uncooked", "unprepared"})


def _singular(word: str) -> str:
    """Drop a trailing plural 's' so "banana" matches "Bananas" (light stemming)."""
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def _tokens(text: str) -> set[str]:
    """The lower-case alphanumeric word tokens of *text*, singularized."""
    return {_singular(t) for t in re.findall(r"[a-z0-9]+", text.lower())}


def _text_score(query: str, fields: list[str]) -> tuple[int, str]:
    """Best relevance score of *query* across *fields* (and the field that won).

    exact (4) > all query words present as whole words (3) > prefix (2) >
    loose substring (1) > no match (0). Word matching is singular/plural-aware.
    """
    qtokens = _tokens(query)
    best, best_field = 0, ""
    for field in fields:
        lowered = field.lower()
        if lowered == query:
            score = 4
        elif qtokens and qtokens <= _tokens(field):
            score = 3
        elif lowered.startswith(query):
            score = 2
        elif query in lowered:
            score = 1
        else:
            score = 0
        if score > best:
            best, best_field = score, field
    return best, best_field


def _canonical_score(description: str, query: str = "") -> float:
    """Higher for a more canonical food description, given the *query*.

    Defaults to preferring raw/whole/simple/short. Two corrections: a **staple**
    (rice, oats, pasta, beans) prefers *cooked* and is penalized for *raw* — it's
    eaten cooked; and a **head-noun match** (the query word is the description's
    primary noun, not a buried modifier) is rewarded, so "apple" → "Apples, raw"
    beats the unrelated "Rose-apples, raw". Deli markers still cost the most.
    """
    toks = _tokens(description)
    score = 0.0
    if _COOKED_STAPLES & toks:
        if {"cooked", "boiled"} & toks:
            score += 4.0  # outweighs the processed-term penalty on "cooked"
        if _DRY_TERMS & toks:
            score -= 3.0
    elif "raw" in toks:
        score += 3.0
    if "whole" in toks:
        score += 0.5
    # The primary noun is the head word of the first comma/paren segment.
    primary = re.split(r"[,(]", description.lower(), maxsplit=1)[0].split()
    head = _singular(primary[0]) if primary else ""
    if head and head in _tokens(query):
        score += 1.5
    score -= float(len(_PROCESSED_TERMS & toks))
    score -= 2.0 * len(_DELI_TERMS & toks)
    score -= 0.02 * len(description)
    return score
