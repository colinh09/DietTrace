"""normalize_experiments turns raw Phoenix payloads into comparable results (5.1)."""

from dietrace.agents.supervisor.reader import normalize_experiments


def test_normalize_extracts_per_annotation_case_results() -> None:
    raw = [
        {
            "id": "exp1",
            "name": "dietrace-nutrition-abc",
            "runs": [
                {
                    "id": "r1",
                    "datasetExampleId": "egg_large",
                    "output": {"totals": []},
                    "annotations": [
                        {"score": 0.9, "label": "pass"},
                        {"score": 0.2, "label": "fail"},
                    ],
                }
            ],
        }
    ]

    summaries = normalize_experiments(raw)

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.experiment_id == "exp1"
    assert summary.experiment_name == "dietrace-nutrition-abc"
    assert len(summary.case_results) == 2
    assert summary.case_results[0].example_id == "egg_large"
    assert summary.case_results[0].passed is True
    assert summary.case_results[1].passed is False


def test_summary_pass_rate_and_mean_score() -> None:
    raw = [
        {
            "id": "exp1",
            "name": "n",
            "runs": [
                {
                    "id": "r1",
                    "datasetExampleId": "a",
                    "annotations": [{"score": 1.0, "label": "pass"}],
                },
                {
                    "id": "r2",
                    "datasetExampleId": "b",
                    "annotations": [{"score": 0.0, "label": "fail"}],
                },
            ],
        }
    ]

    summary = normalize_experiments(raw)[0]

    assert summary.pass_rate == 0.5
    assert summary.mean_score == 0.5


def test_na_results_excluded_from_aggregation() -> None:
    """``n/a`` evaluators are filtered out of pass_rate/mean_score by label.

    The numeric evaluators emit a non-penalizing ``n/a`` (score 1.0) for a
    non-applicable case — micros on a label-tier food, portion with no
    ground-truth grams. Per axon's convention they are kept out of the
    accuracy aggregation by label, not score, so they neither inflate the pass
    rate nor skew the mean the supervisor reads.
    """
    raw = [
        {
            "id": "exp1",
            "name": "n",
            "runs": [
                {
                    "id": "r1",
                    "datasetExampleId": "a",
                    "annotations": [
                        {"score": 1.0, "label": "pass"},
                        {"score": 0.0, "label": "fail"},
                        {"score": 1.0, "label": "n/a"},
                    ],
                }
            ],
        }
    ]

    summary = normalize_experiments(raw)[0]

    # n/a is dropped: 1 pass of 2 scored cases, mean of 1.0 and 0.0 — not 2/3.
    assert summary.pass_rate == 0.5
    assert summary.mean_score == 0.5


def test_mean_score_none_when_all_na() -> None:
    """mean_score is None when every result carries label='n/a' (no applicable scores).

    The supervisor reads mean_score to decide if enough data exists; returning
    None (not a placeholder float) is the fail-soft signal that no real scores
    were collected in this experiment.
    """
    raw = [
        {
            "id": "e1",
            "name": "n",
            "runs": [
                {
                    "id": "r1",
                    "datasetExampleId": "a",
                    "annotations": [{"score": 1.0, "label": "n/a"}],
                }
            ],
        }
    ]
    summary = normalize_experiments(raw)[0]
    assert summary.mean_score is None


def test_pass_rate_zero_when_no_scored_cases() -> None:
    """pass_rate is 0.0 when every result has label='n/a' — no applicable cases."""
    raw = [
        {
            "id": "e1",
            "name": "n",
            "runs": [
                {
                    "id": "r1",
                    "datasetExampleId": "a",
                    "annotations": [{"score": 0.5, "label": "n/a"}],
                }
            ],
        }
    ]
    summary = normalize_experiments(raw)[0]
    assert summary.pass_rate == 0.0


def test_is_passing_score_fallback_true_for_unknown_label_at_or_above_half() -> None:
    """When the label is not in any canonical set and score >= 0.5 the case passes.

    Phoenix occasionally emits non-standard label strings; the score-based
    fallback in _is_passing ensures a >50%-accurate result is not silently
    counted as a failure by the supervisor, which would over-flag regressions.
    """
    raw = [
        {
            "id": "e1",
            "name": "n",
            "runs": [
                {
                    "id": "r1",
                    "datasetExampleId": "a",
                    "annotations": [{"score": 0.7, "label": "unexpected_label"}],
                }
            ],
        }
    ]
    result = normalize_experiments(raw)[0].case_results[0]
    assert result.passed is True


def test_is_passing_score_fallback_false_for_unknown_label_below_half() -> None:
    """When the label is unknown and score < 0.5 the case does not pass."""
    raw = [
        {
            "id": "e1",
            "name": "n",
            "runs": [
                {
                    "id": "r1",
                    "datasetExampleId": "a",
                    "annotations": [{"score": 0.3, "label": "borderline"}],
                }
            ],
        }
    ]
    result = normalize_experiments(raw)[0].case_results[0]
    assert result.passed is False


def test_is_passing_false_for_unknown_label_with_no_score() -> None:
    """When label is unknown and score is None the final-guard returns False.

    This is the last resort in _is_passing: an annotation with neither a
    canonical label nor a numeric score cannot be resolved — treating it as
    a non-pass is conservative and prevents silent regressions from slipping
    through as passes.
    """
    raw = [
        {
            "id": "e1",
            "name": "n",
            "runs": [
                {
                    "id": "r1",
                    "datasetExampleId": "a",
                    "annotations": [{"score": None, "label": "unknown_label"}],
                }
            ],
        }
    ]
    result = normalize_experiments(raw)[0].case_results[0]
    assert result.passed is False


def test_normalize_label_none_becomes_unknown() -> None:
    """A None label (from an incomplete Phoenix annotation) is coerced to 'unknown'.

    Phoenix may return null for a label field when an evaluator produces a score
    but no string label. _normalize_label must not raise on None — it returns the
    safe sentinel 'unknown' so downstream label comparisons work without guards.
    """
    raw = [
        {
            "id": "e1",
            "name": "n",
            "runs": [
                {
                    "id": "r1",
                    "datasetExampleId": "a",
                    "annotations": [{"score": 0.5, "label": None}],
                }
            ],
        }
    ]
    result = normalize_experiments(raw)[0].case_results[0]
    assert result.label == "unknown"
