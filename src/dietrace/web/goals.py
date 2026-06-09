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
    (``NaN``/``Infinity``), so they fall back to the default too. A zero or
    negative target is finite but just as malformed — it breaks the progress
    bars (``consumed / target`` divides by zero or a negative) and violates the
    ``target > 0`` invariant — so non-positive overrides also fall back.
    """
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if math.isfinite(value) and value > 0.0 else default


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


def _valid_target(value: Any) -> bool:
    """Whether a saved target is a usable daily goal: a finite, positive number.

    Saved targets reach ``targets_to_goals`` straight from the client's
    ``POST /macros/save`` body — ``MacroSaveRequest.targets`` is an unconstrained
    ``dict[str, float]``, so pydantic admits ``NaN``/``Infinity`` and the
    ``GoalStore`` persists them verbatim (``json.dumps`` writes ``NaN``/``Infinity``)
    and reads them back as-is. A non-finite target poisons the ``/analysis``
    remaining-vs-target math and serializes as invalid JSON; a target ≤ 0 breaks
    the progress-bar ratio (``consumed / target``) — the same malformed-target
    class the env-override path guards in :func:`_target`. ``bool`` is excluded
    so a stray ``True`` isn't read as a 1-unit goal.
    """
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0.0
    )


def targets_to_goals(targets: dict[str, float]) -> list[dict[str, Any]]:
    """Convert a saved targets dict {USDA code: amount} to the goals list format.

    Preserves the canonical ordering from ``_GOAL_DEFS`` and carries over the
    name and unit for each code.  Codes not in ``_GOAL_DEFS`` are ignored so
    the output always matches what ``load_goals`` produces. A malformed saved
    target (non-finite or non-positive) degrades to that code's built-in default
    rather than shipping a value that poisons the ``/analysis`` math or
    serializes as invalid JSON (fail-soft, /§9 — mirrors :func:`_target`).
    """
    result = []
    for _, code, name, unit, default in _GOAL_DEFS:
        if code in targets:
            value = targets[code]
            target = value if _valid_target(value) else default
            result.append({"code": code, "name": name, "target": target, "unit": unit})
    return result
