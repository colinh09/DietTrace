"""Static RDA/DV reference for the micro nutrient panel.

A compact set of USDA nutrient codes with their daily reference values — either
an official RDA/AI or the FDA Daily Value used on Nutrition Facts labels. The
mapping is keyed by USDA number code so it lines up with the nutrient totals
``log_entry`` produces.

``micro_progress(totals)`` filters daily totals down to the tracked micro codes
and returns consumed / rda / pct_dv for each — the aggregate the web surface and
``/analysis`` render as the micronutrient status band.

Sources: FDA Daily Values (21 CFR 101.9) + USDA DRI tables.
"""

from __future__ import annotations

from typing import Any

# (USDA code, name, unit, daily reference value)
_MICRO_DEFS: list[tuple[str, str, str, float]] = [
    ("291", "Fiber, total dietary", "g", 28.0),
    ("307", "Sodium, Na", "mg", 2300.0),
    ("301", "Calcium, Ca", "mg", 1300.0),
    ("303", "Iron, Fe", "mg", 18.0),
    ("304", "Magnesium, Mg", "mg", 420.0),
    ("306", "Potassium, K", "mg", 4700.0),
    ("309", "Zinc, Zn", "mg", 11.0),
    ("401", "Vitamin C, total ascorbic acid", "mg", 90.0),
    ("328", "Vitamin D (D2 + D3)", "µg", 20.0),
    ("418", "Vitamin B-12", "µg", 2.4),
    ("269", "Sugars, total including NLEA", "g", 50.0),
    ("606", "Fatty acids, total saturated", "g", 20.0),
]

# Frozenset of tracked micro USDA codes — used by callers to filter totals.
MICRO_CODES: frozenset[str] = frozenset(code for code, _, _, _ in _MICRO_DEFS)


def micro_progress(totals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare a day's nutrient totals against micro RDAs.

    Filters *totals* to just the tracked micro codes, looks up each code's RDA,
    and returns consumed / rda / pct_dv. Codes absent from the day's totals are
    included with ``consumed=0.0`` so the panel always shows the full tracked set,
    not just what was eaten. Codes in *totals* that are NOT in MICRO_CODES (e.g.
    macro codes 208/203/204/205) are excluded — additive only, macro side unchanged.
    """
    by_code = {t["code"]: float(t.get("amount") or 0.0) for t in totals}
    result: list[dict[str, Any]] = []
    for code, name, unit, rda in _MICRO_DEFS:
        consumed = by_code.get(code, 0.0)
        result.append({
            "code": code,
            "name": name,
            "unit": unit,
            "consumed": consumed,
            "rda": rda,
            "pct_dv": round(consumed / rda * 100, 1) if rda > 0 else None,
        })
    return result
