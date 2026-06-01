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
# An "orange"/"potato" query has to choose between the whole food and a
# non-edible part — the peel or the leaves. The part shares the base
# noun and is also "raw", so only a part-penalty keeps the fruit/tuber on top.
ORANGE_FDC_ID = 169097
ORANGE_PEEL_FDC_ID = 169926
POTATO_FDC_ID = 170026
SWEET_POTATO_LEAVES_FDC_ID = 168484
# A bare-ingredient query has to choose between the ingredient and a prepared or
# branded product of it: "peach" -> the fruit over "Pie, peach", and
# "coffee" -> brewed coffee over a branded coffee soymilk. The product shares the
# ingredient word (equal text match), so only a product-form penalty keeps the
# ingredient on top. COFFEE_SOYMILK is the lower fdc_id so, absent the penalty,
# it would win the tie — pinning that the penalty (not fdc_id order) decides.
PEACH_FDC_ID = 169928
PEACH_PIE_FDC_ID = 174988
COFFEE_SOYMILK_FDC_ID = 171880
COFFEE_BREWED_FDC_ID = 171881
# A non-staple produce query has to choose between the raw form and a dehydrated
# one: "carrot" -> "Carrots, raw" over "Carrots, dehydrated". Both
# carry the base noun (equal text match); the dehydrated variant has the LOWER
# fdc_id, so absent a ranking signal it would win the tie — pinning that the
# raw-preference / dry penalty (not fdc_id order) keeps the raw produce on top.
CARROT_DEHYDRATED_FDC_ID = 168153
CARROT_RAW_FDC_ID = 170393
# Basket anchors for the search-resolution regression test. Each
# rounds out the set of common foods that must not regress: an apple (bare fruit
# vs a prepared "Sauce, apple" — the 11.2 product-form pattern) and white rice (a
# staple, so cooked is canonical and raw is the wrong form). In both pairs the
# wrong variant (sauce, raw rice) has the LOWER fdc_id, so absent the canonical
# ranking it would win the tie — pinning that the ranking, not fdc_id order, wins.
APPLE_SAUCE_FDC_ID = 168151
APPLE_RAW_FDC_ID = 171688
RICE_RAW_FDC_ID = 169756
RICE_COOKED_FDC_ID = 169757

FIXTURE_FDC_IDS = (
    EGG_FDC_ID,
    AVOCADO_FDC_ID,
    TOAST_FDC_ID,
    CHICKEN_BREAST_RAW_FDC_ID,
    CHICKEN_BREAST_COOKED_FDC_ID,
    CHICKEN_DELI_FDC_ID,
    ORANGE_FDC_ID,
    ORANGE_PEEL_FDC_ID,
    POTATO_FDC_ID,
    SWEET_POTATO_LEAVES_FDC_ID,
    PEACH_FDC_ID,
    PEACH_PIE_FDC_ID,
    COFFEE_SOYMILK_FDC_ID,
    COFFEE_BREWED_FDC_ID,
    CARROT_DEHYDRATED_FDC_ID,
    CARROT_RAW_FDC_ID,
    APPLE_SAUCE_FDC_ID,
    APPLE_RAW_FDC_ID,
    RICE_RAW_FDC_ID,
    RICE_COOKED_FDC_ID,
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
    (ORANGE_FDC_ID, "Oranges, raw, all commercial varieties", "sr_legacy_food"),
    (ORANGE_PEEL_FDC_ID, "Orange peel, raw", "sr_legacy_food"),
    # "flesh and skin" names the WHOLE tuber, so its "skin" must not be read as a
    # part — only a standalone "skin"/leaves/peel is penalized.
    (POTATO_FDC_ID, "Potato, raw, flesh and skin", "sr_legacy_food"),
    (SWEET_POTATO_LEAVES_FDC_ID, "Sweet potato leaves, raw", "sr_legacy_food"),
    (PEACH_FDC_ID, "Peach, raw", "sr_legacy_food"),
    (PEACH_PIE_FDC_ID, "Pie, peach", "sr_legacy_food"),
    # A branded coffee soymilk leads with the ingredient word "coffee" yet is a
    # prepared product (the "soymilk" form), so it must lose to brewed coffee.
    (COFFEE_SOYMILK_FDC_ID, "Coffee soymilk", "branded_food"),
    (COFFEE_BREWED_FDC_ID, "Coffee, brewed", "sr_legacy_food"),
    # A dehydrated carrot is concentrated (≈8× the calories of the raw root), so
    # resolving "carrot" to it would badly overstate a meal — the raw form must
    # win.
    (CARROT_DEHYDRATED_FDC_ID, "Carrots, dehydrated", "sr_legacy_food"),
    (CARROT_RAW_FDC_ID, "Carrots, raw", "sr_legacy_food"),
    # "Sauce, apple" leads with a prepared product form ("sauce"), so the bare
    # query "apple" must resolve to the fruit, not the sauce.
    (APPLE_SAUCE_FDC_ID, "Sauce, apple, canned, unsweetened", "sr_legacy_food"),
    (APPLE_RAW_FDC_ID, "Apples, raw, with skin", "sr_legacy_food"),
    # White rice is a staple — eaten cooked — so "rice" must resolve to the cooked
    # form (~130 kcal), not the raw grain (~365 kcal): the cooked-staple correction.
    (RICE_RAW_FDC_ID, "Rice, white, long-grain, regular, raw, enriched", "sr_legacy_food"),
    (
        RICE_COOKED_FDC_ID,
        "Rice, white, long-grain, regular, cooked, enriched",
        "sr_legacy_food",
    ),
]

# fdc_id -> {nutrient code: amount per 100 g}, USDA-grounded.
_FOOD_NUTRIENTS = {
    EGG_FDC_ID: {"208": 143.0, "203": 12.6, "204": 9.51, "205": 0.72},
    AVOCADO_FDC_ID: {"208": 160.0, "203": 2.0, "204": 14.66, "205": 8.53},
    TOAST_FDC_ID: {"208": 254.0, "203": 12.3, "204": 3.55, "205": 43.1},
    CHICKEN_BREAST_RAW_FDC_ID: {"208": 120.0, "203": 22.5, "204": 2.62, "205": 0.0},
    CHICKEN_BREAST_COOKED_FDC_ID: {"208": 165.0, "203": 31.0, "204": 3.57, "205": 0.0},
    CHICKEN_DELI_FDC_ID: {"208": 92.0, "203": 17.0, "204": 1.5, "205": 2.0},
    ORANGE_FDC_ID: {"208": 47.0, "203": 0.94, "204": 0.12, "205": 11.75},
    ORANGE_PEEL_FDC_ID: {"208": 97.0, "203": 1.5, "204": 0.2, "205": 25.0},
    POTATO_FDC_ID: {"208": 77.0, "203": 2.05, "204": 0.09, "205": 17.49},
    SWEET_POTATO_LEAVES_FDC_ID: {"208": 42.0, "203": 4.0, "204": 0.51, "205": 8.0},
    PEACH_FDC_ID: {"208": 39.0, "203": 0.91, "204": 0.25, "205": 9.54},
    PEACH_PIE_FDC_ID: {"208": 223.0, "203": 1.8, "204": 9.5, "205": 33.0},
    COFFEE_SOYMILK_FDC_ID: {"208": 43.0, "203": 2.5, "204": 1.5, "205": 5.0},
    COFFEE_BREWED_FDC_ID: {"208": 1.0, "203": 0.12, "204": 0.02, "205": 0.0},
    CARROT_DEHYDRATED_FDC_ID: {"208": 341.0, "203": 8.12, "204": 1.49, "205": 79.6},
    CARROT_RAW_FDC_ID: {"208": 41.0, "203": 0.93, "204": 0.24, "205": 9.58},
    APPLE_SAUCE_FDC_ID: {"208": 42.0, "203": 0.17, "204": 0.05, "205": 11.29},
    APPLE_RAW_FDC_ID: {"208": 52.0, "203": 0.26, "204": 0.17, "205": 13.81},
    RICE_RAW_FDC_ID: {"208": 365.0, "203": 7.13, "204": 0.66, "205": 79.95},
    RICE_COOKED_FDC_ID: {"208": 130.0, "203": 2.69, "204": 0.28, "205": 28.17},
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
