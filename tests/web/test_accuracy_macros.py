"""Tests for the macros section of accuracy_report()."""

import pytest

from dietrace.web.accuracy import accuracy_report


def _no_live():
    return None


def test_accuracy_report_includes_macros_key() -> None:
    report = accuracy_report(fetch=_no_live)
    assert "macros" in report


def test_macros_section_has_required_keys() -> None:
    report = accuracy_report(fetch=_no_live)
    macros = report["macros"]
    assert "headline" in macros
    assert "experiments" in macros
    assert "trend" in macros
    assert "dataset" in macros


def test_macros_headline_has_pass_rate_and_mean_score() -> None:
    report = accuracy_report(fetch=_no_live)
    headline = report["macros"]["headline"]
    assert "pass_rate" in headline
    assert "mean_score" in headline
    assert 0.0 <= headline["pass_rate"] <= 1.0
    assert 0.0 <= headline["mean_score"] <= 1.0


def test_macros_experiments_is_null_on_fallback() -> None:
    report = accuracy_report(fetch=_no_live)
    assert report["macros"]["experiments"] is None


def test_macros_trend_is_a_list() -> None:
    report = accuracy_report(fetch=_no_live)
    assert isinstance(report["macros"]["trend"], list)


def test_macros_trend_has_at_least_two_points_on_fallback() -> None:
    """Fallback trend should have baseline + current (≥2 points) for the chart."""
    report = accuracy_report(fetch=_no_live)
    assert len(report["macros"]["trend"]) >= 2


def test_macros_trend_points_have_expected_shape() -> None:
    report = accuracy_report(fetch=_no_live)
    for point in report["macros"]["trend"]:
        assert "pass_rate" in point
        assert "mean_score" in point


def test_macros_dataset_has_cases_count() -> None:
    report = accuracy_report(fetch=_no_live)
    cases = report["macros"]["dataset"]["cases"]
    assert isinstance(cases, int)
    assert cases >= 0


def test_macros_section_with_live_macro_scores() -> None:
    """When the live fetch returns macros experiment data, report maps it."""
    live = {
        "baseline": {"macro_pct_error": 0.05, "calorie_accuracy": 0.02,
                     "within_tolerance": 0.0, "portion_error": 0.1},
        "current": {"macro_pct_error": 0.58, "calorie_accuracy": 0.60,
                    "within_tolerance": 0.38, "portion_error": 0.58},
        "experiments": 2,
        "series": [
            {"macro_pct_error": 0.05, "calorie_accuracy": 0.02,
             "within_tolerance": 0.0, "portion_error": 0.1},
            {"macro_pct_error": 0.58, "calorie_accuracy": 0.60,
             "within_tolerance": 0.38, "portion_error": 0.58},
        ],
        "macros": {
            "baseline": {"macro_plan_within_range": 0.6, "macro_plan_consistency_eval": 0.9},
            "current": {"macro_plan_within_range": 0.85, "macro_plan_consistency_eval": 1.0},
            "experiments": 2,
            "series": [
                {"macro_plan_within_range": 0.6, "macro_plan_consistency_eval": 0.9},
                {"macro_plan_within_range": 0.85, "macro_plan_consistency_eval": 1.0},
            ],
        },
    }

    report = accuracy_report(fetch=lambda: live)

    macros = report["macros"]
    assert macros["experiments"] == 2
    assert len(macros["trend"]) == 2
    assert macros["headline"]["pass_rate"] == pytest.approx(0.85, rel=0.01)


def test_macros_series_shape_with_live_data() -> None:
    """Live macro series includes pass_rate and mean_score per experiment."""
    live = {
        "baseline": {"macro_pct_error": 0.05, "calorie_accuracy": 0.02,
                     "within_tolerance": 0.0, "portion_error": 0.1},
        "current": {"macro_pct_error": 0.58, "calorie_accuracy": 0.60,
                    "within_tolerance": 0.38, "portion_error": 0.58},
        "experiments": 3,
        "series": [],
        "macros": {
            "baseline": {"macro_plan_within_range": 0.5, "macro_plan_consistency_eval": 0.8},
            "current": {"macro_plan_within_range": 0.9, "macro_plan_consistency_eval": 1.0},
            "experiments": 3,
            "series": [
                {"macro_plan_within_range": 0.5, "macro_plan_consistency_eval": 0.8},
                {"macro_plan_within_range": 0.7, "macro_plan_consistency_eval": 0.9},
                {"macro_plan_within_range": 0.9, "macro_plan_consistency_eval": 1.0},
            ],
        },
    }

    report = accuracy_report(fetch=lambda: live)

    macros = report["macros"]
    assert macros["experiments"] == 3
    assert len(macros["trend"]) == 3
    for point in macros["trend"]:
        assert "pass_rate" in point
        assert "mean_score" in point
