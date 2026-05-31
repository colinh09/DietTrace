"""The accuracy report surfaces the Arize loop + measured improvement (accuracy.py)."""

from dietrace.web.accuracy import accuracy_report


def test_report_shows_improvement_over_baseline() -> None:
    report = accuracy_report()
    # Every metric is at least as good now as the baseline (it improved).
    for metric in report["metrics"]:
        assert metric["current"] >= metric["baseline"]


def test_report_describes_the_self_supervision_loop() -> None:
    report = accuracy_report()
    steps = [step["step"] for step in report["loop"]]
    assert steps == ["trace", "evaluate", "detect", "improve"]


def test_report_links_phoenix_and_cites_usda() -> None:
    report = accuracy_report()
    assert report["phoenix_url"]
    assert report["dataset"]["source"].startswith("USDA")
    assert report["dataset"]["cases"] >= 0
