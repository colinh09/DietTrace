"""Unit tests for the pure helpers in phoenix_eval (the live experiment plumbing
needs Phoenix and is excluded from coverage)."""

from __future__ import annotations

from unittest.mock import MagicMock

import dietrace.agents.supervisor.phoenix_eval as pe
from dietrace.agents.supervisor.phoenix_eval import accuracy, mean_accuracy, row_data


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


def test_row_data_maps_meal_text_to_acc_expected_est() -> None:
    results = [
        {
            "input": {"text": "salmon"},
            "output": {"calories": 280},
            "reference_output": {"calories": 301},
        },
        {  # no estimate → skipped
            "input": {"text": "pasta"},
            "output": {},
            "reference_output": {"calories": 250},
        },
    ]
    rows = row_data(results)
    assert set(rows) == {"salmon"}
    assert rows["salmon"]["expected"] == 301.0
    assert rows["salmon"]["est"] == 280.0
    assert rows["salmon"]["acc"] == accuracy(280, 301)


def _patch_live_externals(monkeypatch, client):
    """Stub out MCP availability, the REST client, and the experiment plumbing so
    score_fit_via_phoenix exercises only the dataset-sync logic offline."""
    monkeypatch.setattr(
        "dietrace.agents.supervisor.phoenix_mcp.mcp_available", lambda: True
    )
    monkeypatch.setattr(
        "dietrace.agents.supervisor.phoenix_mcp.user_dataset_name",
        lambda u: f"dietrace-user-{u}",
    )
    monkeypatch.setattr(pe, "_phoenix_client", lambda: client)
    monkeypatch.setattr(pe, "_run_experiment", lambda *a, **k: a[4])  # name → id

    def fake_results(exp_id):
        cal = 300 if "base" in exp_id else 280
        return [
            {
                "input": {"text": "salmon"},
                "output": {"calories": cal},
                "reference_output": {"calories": 301},
            }
        ]

    monkeypatch.setattr(pe, "_results_via_mcp", fake_results)


def test_score_fit_rebuilds_dataset_from_current_confirmations(monkeypatch) -> None:
    """Each retune REBUILDS the user's Phoenix dataset to exactly mirror the current
    local confirmations via create_dataset — it must NOT get-or-create + add-missing,
    the stale path that shuffled a meal onto the wrong truth (the live bug)."""
    client = MagicMock()
    ds = MagicMock()
    ds.example_count = 2
    ds.id = "ds1"
    client.datasets.create_dataset.return_value = ds
    _patch_live_externals(monkeypatch, client)

    fit = [{"text": "salmon", "calories": 301}, {"text": "pasta", "calories": 250}]
    out = pe.score_fit_via_phoenix("u1", "base", "tuned", lambda *a, **k: {}, fit_cases=fit)

    assert out is not None
    client.datasets.create_dataset.assert_called_once()
    kwargs = client.datasets.create_dataset.call_args.kwargs
    assert kwargs["name"] == "dietrace-user-u1"
    assert kwargs["inputs"] == [{"text": "salmon"}, {"text": "pasta"}]
    assert kwargs["outputs"] == [{"calories": 301}, {"calories": 250}]
    # The stale accumulate-by-text path is gone.
    client.datasets.get_dataset.assert_not_called()
    client.datasets.add_examples_to_dataset.assert_not_called()


def test_score_fit_returns_none_without_fit_cases(monkeypatch) -> None:
    client = MagicMock()
    _patch_live_externals(monkeypatch, client)

    out = pe.score_fit_via_phoenix("u1", "base", "tuned", lambda *a, **k: {}, fit_cases=[])

    assert out is None
    client.datasets.create_dataset.assert_not_called()
