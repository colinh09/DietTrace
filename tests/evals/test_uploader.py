"""The dataset uploader loads cases and pushes rows to Phoenix.

The Phoenix client is mocked; these assert that the seed dataset loads and that
``upload`` hands the client parallel input/expected/metadata rows. Offline.
"""

from unittest.mock import MagicMock

from dietrace.evals import uploader


def test_load_cases_reads_the_seed_dataset() -> None:
    cases = uploader.load_cases("evals/dataset/nutrition")
    assert len(cases) >= 8
    assert all(case.metadata.nutrient_tier in ("full", "label") for case in cases)


def test_upload_passes_rows_to_client() -> None:
    client = MagicMock()
    cases = uploader.load_cases("evals/dataset/nutrition")

    uploader.upload(client, cases, name="test-ds")

    client.datasets.create_dataset.assert_called_once()
    kwargs = client.datasets.create_dataset.call_args.kwargs
    assert kwargs["name"] == "test-ds"
    assert len(kwargs["inputs"]) == len(cases)
    assert len(kwargs["outputs"]) == len(cases)
    assert kwargs["inputs"][0] == cases[0].input.model_dump()
    assert kwargs["outputs"][0] == cases[0].expected.model_dump()
