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

import math
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


def _finite_amount(value: Any) -> float:
    """Coerce a total's amount to a finite float, treating junk as 0.0.

    pydantic admits non-finite floats (``NaN``/``±inf``) and a garbled tool-call or
    corrupted total can supply one; unguarded it flows into ``consumed``/``pct_dv``,
    surfacing in the UI and serializing as the invalid-JSON token ``NaN``/``Infinity``
    out of ``/analysis``. So a missing, uncoercible, or non-finite amount reads as
    nothing consumed (0.0), mirroring the isfinite guard in check_against_goals /
    estimate_portion / parse_meal (fail-soft).
    """
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return 0.0
    return amount if math.isfinite(amount) else 0.0


def micro_progress(totals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare a day's nutrient totals against micro RDAs.

    Filters *totals* to just the tracked micro codes, looks up each code's RDA,
    and returns consumed / rda / pct_dv. Codes absent from the day's totals are
    included with ``consumed=0.0`` so the panel always shows the full tracked set,
    not just what was eaten. Codes in *totals* that are NOT in MICRO_CODES (e.g.
    macro codes 208/203/204/205) are excluded — additive only, macro side unchanged.
    """
    # Read the code defensively (.get, not [...]) so a partial/malformed total — a
    # code-less dict from a garbled tool-call or a corrupted aggregate — is skipped
    # rather than raising KeyError and taking down the whole panel; mirrors the
    # already-defensive amount handling and online ``_totals_by_code`` (fail-soft).
    by_code = {
        code: _finite_amount(t.get("amount"))
        for t in totals
        if (code := t.get("code")) is not None
    }
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
