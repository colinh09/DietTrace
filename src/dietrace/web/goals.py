"""Daily macro/calorie goals for the web surface.

A small config of daily targets — calories, protein, carbohydrate, fat — keyed by
USDA number code (208/203/205/204, ) so they line up with the nutrient totals
``log_entry`` produces. Defaults are env-overridable (``DIETRACE_GOAL_*``), exposed
at ``GET /goals``, and drive the remaining-vs-target figures in ``/analysis``.
"""

from __future__ import annotations

import os
from typing import Any

# (env var, USDA code, name, unit, default daily target).
_GOAL_DEFS: list[tuple[str, str, str, str, float]] = [
    ("DIETRACE_GOAL_CALORIES", "208", "Energy", "kcal", 2000.0),
    ("DIETRACE_GOAL_PROTEIN", "203", "Protein", "g", 150.0),
    ("DIETRACE_GOAL_CARB", "205", "Carbohydrate", "g", 200.0),
    ("DIETRACE_GOAL_FAT", "204", "Total lipid (fat)", "g", 65.0),
]


def load_goals() -> list[dict[str, Any]]:
    """Daily macro/calorie targets, env-overridable.

    Read at call time so an env override applies without rebuilding the app.
    """
    return [
        {
            "code": code,
            "name": name,
            "target": float(os.environ.get(env_var, default)),
            "unit": unit,
        }
        for env_var, code, name, unit, default in _GOAL_DEFS
    ]
