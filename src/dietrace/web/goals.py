"""Daily macro/calorie goals for the web surface.

A small config of daily targets — calories, protein, carbohydrate, fat — keyed by
USDA number code (208/203/205/204, ) so they line up with the nutrient totals
``log_entry`` produces. Defaults are env-overridable (``DIETRACE_GOAL_*``), exposed
at ``GET /goals``, and drive the remaining-vs-target figures in ``/analysis``.
"""

from __future__ import annotations

import math
import os
from typing import Any

# (env var, USDA code, name, unit, default daily target).
_GOAL_DEFS: list[tuple[str, str, str, str, float]] = [
    ("DIETRACE_GOAL_CALORIES", "208", "Energy", "kcal", 2000.0),
    ("DIETRACE_GOAL_PROTEIN", "203", "Protein", "g", 150.0),
    ("DIETRACE_GOAL_CARB", "205", "Carbohydrate", "g", 200.0),
    ("DIETRACE_GOAL_FAT", "204", "Total lipid (fat)", "g", 65.0),
]


def _target(env_var: str, default: float) -> float:
    """The daily target for *env_var*, falling back to *default* fail-soft.

    A non-numeric override (e.g. ``DIETRACE_GOAL_PROTEIN=abc``) must not crash
    ``/goals`` or ``/analysis`` — degrade to the built-in default rather than
    letting ``float()`` raise. ``nan``/``inf`` parse
    without raising but are equally malformed: a non-finite target poisons the
    ``/analysis`` remaining-vs-target math and serializes as invalid JSON
    (``NaN``/``Infinity``), so they fall back to the default too.
    """
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if math.isfinite(value) else default


def load_goals() -> list[dict[str, Any]]:
    """Daily macro/calorie targets, env-overridable.

    Read at call time so an env override applies without rebuilding the app.
    """
    return [
        {
            "code": code,
            "name": name,
            "target": _target(env_var, default),
            "unit": unit,
        }
        for env_var, code, name, unit, default in _GOAL_DEFS
    ]
