"""The accuracy report: live Phoenix scores when available, measured fallback (accuracy.py)."""

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
