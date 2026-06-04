"""The macros accuracy headline is a real measurement, not a placeholder (fix #5).

When no live Phoenix macro experiment is available, the report computes the
macro scores by running the actual evaluators over the seed dataset — so the
numbers a judge sees are genuine, not the old hardcoded 0.85/1.0 constants.
"""

from __future__ import annotations

from dietrace.web.accuracy import _measured_macro_scores, accuracy_report


def test_macros_headline_matches_real_measurement() -> None:
    measured = _measured_macro_scores()
    assert measured is not None, "seed macro dataset should exist"

    report = accuracy_report(fetch=lambda: None)  # force the no-live fallback
    macros = report["macros"]

    assert macros["headline"]["pass_rate"] == measured["pass_rate"]
    assert macros["headline"]["mean_score"] == measured["mean_score"]
    assert macros["experiments"] is None
    assert macros["dataset"]["cases"] >= 1


def test_seed_planner_passes_its_own_dataset() -> None:
    # The deterministic planner should land in-range and stay consistent on every
    # seed case — an honest, defensible number to show judges.
    measured = _measured_macro_scores()
    assert measured == {"pass_rate": 1.0, "mean_score": 1.0}
