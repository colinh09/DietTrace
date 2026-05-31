"""Builder for the tiny test fixture food DB.

The production read layer queries ``data/food.sqlite`` — a 3 GB SQLite file
built by the obscured ``tools/`` pipeline and never committed. Tests instead
build a throwaway DB with a few whole foods (an egg, an avocado, a slice of
toast) carrying USDA-grounded per-100 g nutrients, serving-size gram weights,
Atwater conversion factors, and aliases. That is enough ground truth for the
FoodRepository.get / .search tests (2.3 / 2.4) to run fully offline.

The schema mirrors the tracked read layer's tables: ``foods`` keyed by
``fdc_id``, a ``nutrients`` catalog joined through ``food_nutrients`` by USDA
number code (208 kcal, 203 protein, 204 fat, 205 carb — ),
``serving_sizes``, ``nutrient_conversion_factors``, and ``food_aliases``.
"""

from __future__ import annotations

import sqlite3

EGG_FDC_ID = 748967
AVOCADO_FDC_ID = 171705
TOAST_FDC_ID = 172686
# A "chicken breast" query has to choose among a raw cut, a plainly-cooked cut,
# and a processed deli roll: all three carry the words "chicken" and
# "breast", so the canonical ranking — not text relevance — must break the tie.
CHICKEN_BREAST_RAW_FDC_ID = 171477
CHICKEN_BREAST_COOKED_FDC_ID = 171534
CHICKEN_DELI_FDC_ID = 172865

FIXTURE_FDC_IDS = (
    EGG_FDC_ID,
    AVOCADO_FDC_ID,
    TOAST_FDC_ID,
    CHICKEN_BREAST_RAW_FDC_ID,
    CHICKEN_BREAST_COOKED_FDC_ID,
    CHICKEN_DELI_FDC_ID,
)

_SCHEMA = """
CREATE TABLE foods (
    fdc_id      INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    data_type   TEXT NOT NULL
);

CREATE TABLE nutrients (
    nutrient_id INTEGER PRIMARY KEY,
    code        TEXT NOT NULL,
    name        TEXT NOT NULL,
    unit        TEXT NOT NULL
);

CREATE TABLE food_nutrients (
    fdc_id      INTEGER NOT NULL REFERENCES foods(fdc_id),
    nutrient_id INTEGER NOT NULL REFERENCES nutrients(nutrient_id),
    amount      REAL NOT NULL,
    PRIMARY KEY (fdc_id, nutrient_id)
);

CREATE TABLE serving_sizes (
    fdc_id          INTEGER NOT NULL REFERENCES foods(fdc_id),
    amount          REAL NOT NULL,
    unit            TEXT NOT NULL,
    gram_weight     REAL NOT NULL,
    description     TEXT,
    sequence_number INTEGER
);

CREATE TABLE nutrient_conversion_factors (
    fdc_id              INTEGER PRIMARY KEY REFERENCES foods(fdc_id),
    protein_factor      REAL,
    fat_factor          REAL,
    carbohydrate_factor REAL
);

CREATE TABLE food_aliases (
    fdc_id     INTEGER NOT NULL REFERENCES foods(fdc_id),
    alias_name TEXT NOT NULL
);
"""

# USDA number code, name, unit — the macro panel the agent reads.
_NUTRIENTS = [
    (1, "208", "Energy", "kcal"),
    (2, "203", "Protein", "g"),
    (3, "204", "Total lipid (fat)", "g"),
    (4, "205", "Carbohydrate, by difference", "g"),
]

# (fdc_id, description, data_type)
_FOODS = [
    (EGG_FDC_ID, "Egg, whole, raw, fresh", "sr_legacy_food"),
    (AVOCADO_FDC_ID, "Avocados, raw, all commercial varieties", "sr_legacy_food"),
    (TOAST_FDC_ID, "Bread, whole-wheat, commercially prepared", "sr_legacy_food"),
    (
        CHICKEN_BREAST_RAW_FDC_ID,
        "Chicken, broilers or fryers, breast, meat only, raw",
        "sr_legacy_food",
    ),
    (
        CHICKEN_BREAST_COOKED_FDC_ID,
        "Chicken, broilers or fryers, breast, meat only, cooked, roasted",
        "sr_legacy_food",
    ),
    (CHICKEN_DELI_FDC_ID, "Chicken breast, deli, sliced", "branded_food"),
]

# fdc_id -> {nutrient code: amount per 100 g}, USDA-grounded.
_FOOD_NUTRIENTS = {
    EGG_FDC_ID: {"208": 143.0, "203": 12.6, "204": 9.51, "205": 0.72},
    AVOCADO_FDC_ID: {"208": 160.0, "203": 2.0, "204": 14.66, "205": 8.53},
    TOAST_FDC_ID: {"208": 254.0, "203": 12.3, "204": 3.55, "205": 43.1},
    CHICKEN_BREAST_RAW_FDC_ID: {"208": 120.0, "203": 22.5, "204": 2.62, "205": 0.0},
    CHICKEN_BREAST_COOKED_FDC_ID: {"208": 165.0, "203": 31.0, "204": 3.57, "205": 0.0},
    CHICKEN_DELI_FDC_ID: {"208": 92.0, "203": 17.0, "204": 1.5, "205": 2.0},
}

# fdc_id -> list of (amount, unit, gram_weight, description, sequence_number)
_SERVING_SIZES = {
    EGG_FDC_ID: [(1.0, "large", 50.0, "1 large", 1)],
    AVOCADO_FDC_ID: [
        (1.0, "fruit", 201.0, "1 fruit, without skin and seed", 1),
        (0.5, "fruit", 100.5, "half an avocado", 2),
    ],
    TOAST_FDC_ID: [(1.0, "slice", 28.0, "1 slice", 1)],
}

# fdc_id -> (protein_factor, fat_factor, carbohydrate_factor); None where USDA omits.
_CONVERSION_FACTORS = {
    EGG_FDC_ID: (4.36, 9.02, 3.68),
    AVOCADO_FDC_ID: (4.27, 8.37, 3.6),
}

# fdc_id -> list of alias names (alias-aware search, 2.4).
_ALIASES = {
    EGG_FDC_ID: ["egg", "eggs", "whole egg"],
    AVOCADO_FDC_ID: ["avocado", "avocados"],
    TOAST_FDC_ID: ["toast", "whole wheat bread", "wholewheat toast"],
}


def build_food_db(conn: sqlite3.Connection) -> None:
    """Create the read-layer tables and seed the fixture foods into *conn*."""
    conn.executescript(_SCHEMA)
    conn.executemany("INSERT INTO nutrients VALUES (?, ?, ?, ?)", _NUTRIENTS)
    conn.executemany("INSERT INTO foods VALUES (?, ?, ?)", _FOODS)

    code_to_id = {code: nutrient_id for nutrient_id, code, _, _ in _NUTRIENTS}
    conn.executemany(
        "INSERT INTO food_nutrients VALUES (?, ?, ?)",
        [
            (fdc_id, code_to_id[code], amount)
            for fdc_id, panel in _FOOD_NUTRIENTS.items()
            for code, amount in panel.items()
        ],
    )
    conn.executemany(
        "INSERT INTO serving_sizes VALUES (?, ?, ?, ?, ?, ?)",
        [
            (fdc_id, *serving)
            for fdc_id, servings in _SERVING_SIZES.items()
            for serving in servings
        ],
    )
    conn.executemany(
        "INSERT INTO nutrient_conversion_factors VALUES (?, ?, ?, ?)",
        [(fdc_id, *factors) for fdc_id, factors in _CONVERSION_FACTORS.items()],
    )
    conn.executemany(
        "INSERT INTO food_aliases VALUES (?, ?)",
        [
            (fdc_id, alias)
            for fdc_id, aliases in _ALIASES.items()
            for alias in aliases
        ],
    )
    conn.commit()
