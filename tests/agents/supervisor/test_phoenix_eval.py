"""Unit tests for the pure helpers in phoenix_eval (the live experiment plumbing
needs Phoenix and is excluded from coverage)."""

from __future__ import annotations

from dietrace.agents.supervisor.phoenix_eval import accuracy, mean_accuracy


def test_accuracy_exact_off_and_capped() -> None:
    assert accuracy(100, 100) == 1.0  # exact
    assert accuracy(150, 100) == 0.5  # 50% over
    assert accuracy(0, 0) == 1.0  # both zero
    assert accuracy(50, 0) == 0.0  # expected nothing, estimated something
    assert accuracy(300, 100) == 0.0  # way off → floored at 0, not negative


def test_mean_accuracy_skips_unscorable_rows() -> None:
    results = [
        {"output": {"calories": 100}, "reference_output": {"calories": 100}},  # 1.0
        {"output": {"calories": 150}, "reference_output": {"calories": 100}},  # 0.5
        {"output": {"calories": 90}, "reference_output": {}},  # no truth → skipped
    ]
    assert mean_accuracy(results) == 0.75  # mean of the two scorable rows
    assert mean_accuracy([]) is None
    assert mean_accuracy([{"output": {}, "reference_output": {}}]) is None
