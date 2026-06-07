"""Per-meal supervisor decision: pick exactly one of three ops (design §1).

Conservative mode is a deterministic policy (here); powerful mode layers an
LLM-reasoned variant on top (phase 6). The op is *what to do*; the deterministic
gate still decides whether a retune actually ships.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dietrace.agents.supervisor.config import SupervisorConfig

OP_BANK_FEEDBACK = "bank_feedback"
OP_ADD_DATASET_POINT = "add_dataset_point"
OP_RETUNE = "retune"


@dataclass(frozen=True)
class DecisionSignals:
    """Inputs to the per-meal decision, gathered from the user's stores."""

    was_corrected: bool = False
    new_feedback: int = 0  # unprocessed corrections since the last retune
    dataset_points: int = 0  # held-out fit-set size
    runs_today: int = 0
    meal_confidence: float = 1.0


@dataclass(frozen=True)
class Decision:
    op: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {"op": self.op, "reason": self.reason}


def decide(signals: DecisionSignals, config: SupervisorConfig) -> Decision:
    """Deterministic conservative policy → exactly one op.

    Precedence: a correction on this meal is captured first (it's tied to this
    meal); else retune when there's enough *new* signal and we're under the daily
    cap; else the clean meal becomes a held-out dataset point.
    """
    if signals.was_corrected:
        return Decision(OP_BANK_FEEDBACK, "meal was corrected — banking the feedback")

    retune_ready = (
        signals.new_feedback >= config.min_new_feedback
        and signals.dataset_points >= config.min_new_dataset_points
        and signals.runs_today < config.max_runs_per_day
    )
    if retune_ready:
        return Decision(
            OP_RETUNE,
            f"enough new signal ({signals.new_feedback} corrections, "
            f"{signals.dataset_points} dataset points) — retuning",
        )

    return Decision(
        OP_ADD_DATASET_POINT,
        "clean meal accepted as-is — adding to the held-out dataset",
    )


def gather_signals(
    fblog: Any,
    confirms: Any,
    user: str,
    *,
    was_corrected: bool = False,
    runs_today: int = 0,
    meal_confidence: float = 1.0,
) -> DecisionSignals:
    """Build :class:`DecisionSignals` from the user's feedback + confirmation stores."""
    return DecisionSignals(
        was_corrected=was_corrected,
        new_feedback=fblog.count_unprocessed(user),
        dataset_points=confirms.count(user),
        runs_today=runs_today,
        meal_confidence=meal_confidence,
    )
