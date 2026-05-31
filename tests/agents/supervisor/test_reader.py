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
