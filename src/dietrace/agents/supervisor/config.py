"""Supervisor configuration: decision mode + retune thresholds.

``DIETRACE_SUPERVISOR_MODE`` toggles how the per-meal decision is made and how
eagerly retunes run (design §4):
- ``conservative`` (default): deterministic, LLM-free decision; runs gated tightly.
- ``powerful``: LLM-reasoned decision; runs more eagerly.

Thresholds gate when there's *enough new signal* to retune meaningfully. All are
env-overridable; unparseable values fall back to the default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

CONSERVATIVE = "conservative"
POWERFUL = "powerful"
_MODES = (CONSERVATIVE, POWERFUL)

# New corrections are the PRIMARY trigger (feedback is the signal a retune acts on);
# the held-out floor is a precondition so a retune can be validated, not a co-trigger.
DEFAULT_MIN_NEW_FEEDBACK = 3
DEFAULT_MIN_NEW_DATASET_POINTS = 3
DEFAULT_MAX_RUNS_PER_DAY = 10


@dataclass(frozen=True)
class SupervisorConfig:
    """Resolved supervisor settings (see module docstring)."""

    mode: str = CONSERVATIVE
    min_new_feedback: int = DEFAULT_MIN_NEW_FEEDBACK
    min_new_dataset_points: int = DEFAULT_MIN_NEW_DATASET_POINTS
    max_runs_per_day: int = DEFAULT_MAX_RUNS_PER_DAY

    @property
    def is_powerful(self) -> bool:
        return self.mode == POWERFUL


def _int_env(name: str, default: int) -> int:
    """Parse an int from the environment, falling back to *default* on absence/error."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def load_supervisor_config() -> SupervisorConfig:
    """Build a :class:`SupervisorConfig` from the environment (fail-soft defaults)."""
    mode = os.environ.get("DIETRACE_SUPERVISOR_MODE", CONSERVATIVE).strip().lower()
    if mode not in _MODES:
        mode = CONSERVATIVE
    return SupervisorConfig(
        mode=mode,
        min_new_feedback=_int_env("DIETRACE_MIN_NEW_FEEDBACK", DEFAULT_MIN_NEW_FEEDBACK),
        min_new_dataset_points=_int_env(
            "DIETRACE_MIN_NEW_DATASET_POINTS", DEFAULT_MIN_NEW_DATASET_POINTS
        ),
        max_runs_per_day=_int_env("DIETRACE_MAX_RUNS_PER_DAY", DEFAULT_MAX_RUNS_PER_DAY),
    )
