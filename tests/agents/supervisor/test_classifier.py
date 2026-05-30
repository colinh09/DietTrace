"""classify_trends labels improving / stable / regressing accuracy trends (5.2)."""

from dietrace.agents.supervisor.classifier import classify_trends
from dietrace.agents.supervisor.reader import CaseResult, ExperimentSummary


def _exp(score: float, example_id: str = "egg_large") -> ExperimentSummary:
    """One experiment whose single case scored *score*."""
    passed = score >= 0.5
    return ExperimentSummary(
        experiment_id="e",
        experiment_name="n",
        case_results=[
            CaseResult(
                example_id=example_id,
                run_id="r",
                output=None,
                score=score,
                label="pass" if passed else "fail",
                passed=passed,
            )
        ],
    )


def test_rising_scores_are_improving() -> None:
    trends = classify_trends([_exp(0.5), _exp(0.9)])
    assert trends[0].trend == "improving"
    assert trends[0].score_delta == 0.4


def test_falling_scores_are_regressing() -> None:
    trends = classify_trends([_exp(0.9), _exp(0.4)])
    assert trends[0].trend == "regressing"


def test_single_run_is_stable() -> None:
    trends = classify_trends([_exp(0.9)])
    assert trends[0].trend == "stable"  # below min_runs


def test_borderline_delta_defers_to_llm_judge() -> None:
    # delta 0.05 < 0.1 threshold → the (injected) judge decides.
    trends = classify_trends(
        [_exp(0.50), _exp(0.55)],
        _llm_judge_fn=lambda example_id, scores: "stable",
    )
    assert trends[0].trend == "stable"
