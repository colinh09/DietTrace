"""The conservative per-meal decision picks exactly one of three ops."""

from __future__ import annotations

from dietrace.agents.supervisor.config import SupervisorConfig
from dietrace.agents.supervisor.decide import (
    OP_ADD_DATASET_POINT,
    OP_BANK_FEEDBACK,
    OP_RETUNE,
    DecisionSignals,
    decide,
    gather_signals,
)

# Thresholds: retune needs ≥2 new corrections AND ≥3 dataset points, under 5 runs/day.
_CFG = SupervisorConfig(
    min_new_feedback=2, min_new_dataset_points=3, max_runs_per_day=5
)


def test_corrected_meal_banks_feedback() -> None:
    sig = DecisionSignals(was_corrected=True, new_feedback=9, dataset_points=9)
    assert decide(sig, _CFG).op == OP_BANK_FEEDBACK


def test_clean_meal_below_threshold_adds_dataset_point() -> None:
    sig = DecisionSignals(new_feedback=1, dataset_points=1)  # not enough yet
    assert decide(sig, _CFG).op == OP_ADD_DATASET_POINT


def test_enough_signal_triggers_retune() -> None:
    sig = DecisionSignals(new_feedback=2, dataset_points=3, runs_today=0)
    assert decide(sig, _CFG).op == OP_RETUNE


def test_retune_blocked_below_either_threshold() -> None:
    # Enough feedback but too few dataset points → not yet.
    few_points = DecisionSignals(new_feedback=5, dataset_points=2)
    assert decide(few_points, _CFG).op == OP_ADD_DATASET_POINT
    # Enough dataset points but too little feedback → not yet.
    little_fb = DecisionSignals(new_feedback=1, dataset_points=9)
    assert decide(little_fb, _CFG).op == OP_ADD_DATASET_POINT


def test_daily_cap_blocks_retune() -> None:
    sig = DecisionSignals(new_feedback=9, dataset_points=9, runs_today=5)  # at cap
    assert decide(sig, _CFG).op == OP_ADD_DATASET_POINT


def test_correction_takes_precedence_over_retune() -> None:
    sig = DecisionSignals(was_corrected=True, new_feedback=9, dataset_points=9, runs_today=0)
    assert decide(sig, _CFG).op == OP_BANK_FEEDBACK


class _FakeFblog:
    def __init__(self, n: int) -> None:
        self._n = n

    def count_unprocessed(self, user: str) -> int:
        return self._n


class _FakeConfirms:
    def __init__(self, n: int) -> None:
        self._n = n

    def count(self, user: str) -> int:
        return self._n


def test_gather_signals_reads_store_counts() -> None:
    sig = gather_signals(
        _FakeFblog(4), _FakeConfirms(7), "alice", runs_today=2, meal_confidence=0.8
    )
    assert sig.new_feedback == 4
    assert sig.dataset_points == 7
    assert sig.runs_today == 2
    assert sig.meal_confidence == 0.8
    assert sig.was_corrected is False
