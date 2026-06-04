"""The accuracy report: live Phoenix scores when available, measured fallback (accuracy.py)."""

import pytest

from dietrace.web.accuracy import accuracy_report


def _no_live():
    return None


def test_static_fallback_shows_improvement_over_baseline() -> None:
    report = accuracy_report(fetch=_no_live)
    assert report["source"] == "measured"
    for metric in report["metrics"]:
        assert metric["current"] >= metric["baseline"]


def test_report_describes_the_self_supervision_loop() -> None:
    report = accuracy_report(fetch=_no_live)
    assert [step["step"] for step in report["loop"]] == [
        "trace",
        "evaluate",
        "detect",
        "improve",
    ]


def test_report_links_phoenix_and_cites_usda() -> None:
    report = accuracy_report(fetch=_no_live)
    assert report["phoenix_url"]
    assert report["dataset"]["source"].startswith("USDA")


# ---------------------------------------------------------------------------
# trend — the chart series the frontend plots on /accuracy
# ---------------------------------------------------------------------------


def test_trend_is_a_list_on_fallback() -> None:
    report = accuracy_report(fetch=_no_live)
    assert isinstance(report["trend"], list)


def test_trend_has_at_least_two_points_on_fallback() -> None:
    """Fallback trend must have baseline + current — ≥2 points for the chart."""
    report = accuracy_report(fetch=_no_live)
    assert len(report["trend"]) >= 2


def test_trend_points_have_metric_key_shape_on_fallback() -> None:
    """Fallback trend points expose the frontend metric keys, not Phoenix evaluator names."""
    report = accuracy_report(fetch=_no_live)
    for point in report["trend"]:
        for key in ("calorie", "macro", "within_tolerance", "portion"):
            assert key in point, f"metric key {key!r} missing from trend point"
        assert 0.0 <= point["calorie"] <= 1.0
        assert 0.0 <= point["macro"] <= 1.0


def test_trend_maps_phoenix_evaluator_names_to_metric_keys() -> None:
    """Live trend remaps Phoenix evaluator names to the metric keys the frontend uses.

    Phoenix stores scores under names like ``macro_pct_error``, ``calorie_accuracy``,
    ``within_tolerance``, and ``portion_error``.  ``accuracy_report`` remaps these to
    ``macro``, ``calorie``, ``within_tolerance``, and ``portion`` in the trend list so
    the frontend never needs to know the Phoenix evaluator names.
    """
    live = {
        "baseline": {
            "macro_pct_error": 0.05, "calorie_accuracy": 0.02,
            "within_tolerance": 0.0, "portion_error": 0.1,
        },
        "current": {
            "macro_pct_error": 0.58, "calorie_accuracy": 0.60,
            "within_tolerance": 0.38, "portion_error": 0.58,
        },
        "experiments": 2,
        "series": [
            {"macro_pct_error": 0.05, "calorie_accuracy": 0.02,
             "within_tolerance": 0.0, "portion_error": 0.1},
            {"macro_pct_error": 0.58, "calorie_accuracy": 0.60,
             "within_tolerance": 0.38, "portion_error": 0.58},
        ],
    }
    report = accuracy_report(fetch=lambda: live)

    trend = report["trend"]
    assert len(trend) == 2
    assert trend[0]["macro"] == pytest.approx(0.05)
    assert trend[1]["macro"] == pytest.approx(0.58)
    assert trend[0]["calorie"] == pytest.approx(0.02)
    assert trend[1]["calorie"] == pytest.approx(0.60)
    assert trend[0]["within_tolerance"] == pytest.approx(0.0)
    assert trend[1]["portion"] == pytest.approx(0.58)


def test_trend_uses_baseline_plus_current_when_series_absent() -> None:
    """When the live fetch has no 'series' key the trend falls back to [baseline, current]."""
    live = {
        "baseline": {
            "macro_pct_error": 0.05, "calorie_accuracy": 0.02,
            "within_tolerance": 0.0, "portion_error": 0.1,
        },
        "current": {
            "macro_pct_error": 0.58, "calorie_accuracy": 0.60,
            "within_tolerance": 0.38, "portion_error": 0.58,
        },
        "experiments": 5,
        # no "series" key → fallback path: series = [baseline, current]
    }
    report = accuracy_report(fetch=lambda: live)

    assert len(report["trend"]) == 2
    assert report["trend"][0]["macro"] == pytest.approx(0.05)
    assert report["trend"][1]["macro"] == pytest.approx(0.58)


def test_live_scores_map_from_phoenix_evaluator_names() -> None:
    live = {
        "baseline": {
            "macro_pct_error": 0.05,
            "calorie_accuracy": 0.02,
            "within_tolerance": 0.0,
            "portion_error": 0.1,
        },
        "current": {
            "macro_pct_error": 0.58,
            "calorie_accuracy": 0.60,
            "within_tolerance": 0.38,
            "portion_error": 0.58,
        },
        "experiments": 3,
    }

    report = accuracy_report(fetch=lambda: live)

    assert report["source"] == "live"
    assert report["experiments"] == 3
    assert report["headline"]["macro_accuracy"] == 0.58
    macro = next(m for m in report["metrics"] if m["key"] == "macro")
    assert macro["baseline"] == 0.05
    assert macro["current"] == 0.58
