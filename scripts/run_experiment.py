"""Run a real Arize Phoenix experiment scoring the nutrition agent's accuracy.

Uploads (or reuses) the seed dataset, runs the deterministic /log pipeline (one
Gemini parse + the real food DB) over each case as the experiment task, scores
every run with the numeric evaluators, and prints Phoenix's summary plus the
experiment URL. This is the eval half of the self-supervision loop:
the supervisor reads these experiments to detect regressions.

    set -a && . ./.env && set +a
    uv run python scripts/run_experiment.py
"""

from __future__ import annotations

import os

from dietrace.agents.nutrition.orchestrator import log_meal
from dietrace.evals import runner, uploader
from dietrace.nutrition.repository import FoodRepository

EXPERIMENT_NAME = "dietrace-nutrition-accuracy"
DATASET_DIR = "evals/dataset/nutrition"


def _get_or_create_dataset(client, cases):
    """Reuse the dataset by name if it exists, else create it from *cases*."""
    try:
        return client.datasets.get_dataset(dataset=uploader.DATASET_NAME)
    except Exception:  # noqa: BLE001 — any miss (404/unknown) means create it fresh
        return uploader.upload(client, cases)


def main() -> None:
    from phoenix.client import Client

    client = Client(
        base_url=os.environ["PHOENIX_BASE_URL"],
        api_key=os.environ["PHOENIX_API_KEY"],
    )

    cases = uploader.load_cases(DATASET_DIR)
    print(f"Loaded {len(cases)} eval cases.")
    dataset = _get_or_create_dataset(client, cases)

    repository = FoodRepository(os.environ.get("DIETRACE_FOOD_DB", "data/food.sqlite"))

    def run_agent(text: str) -> dict:
        return log_meal(text, repository).model_dump()

    print("Running experiment (live Gemini parse per case)...")
    ran = runner.run(
        client, dataset, run_agent, experiment_name=EXPERIMENT_NAME
    )

    # Phoenix prints its own per-evaluator summary; surface the experiment URL too.
    for attr in ("url", "experiment_url"):
        url = getattr(ran, attr, None)
        if url:
            print(f"Experiment: {url}")
            break


if __name__ == "__main__":
    main()
