"""Phoenix experiment runner for the nutrition eval suite.

``run()`` drives a Phoenix experiment: it pairs the dataset with a *task* (the
agent logging each meal) and the numeric evaluators, and calls the Phoenix
client's ``experiments.run_experiment``. The Phoenix client is injected so the
wiring is testable offline — nothing here touches the network or Vertex.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dietrace.evals.evaluators import (
    calorie_accuracy,
    macro_pct_error,
    micro_panel_accuracy,
    portion_error,
    within_tolerance,
)

# The full numeric evaluator panel attached to every experiment run.
EVALUATORS = [
    macro_pct_error,
    calorie_accuracy,
    within_tolerance,
    portion_error,
    micro_panel_accuracy,
]


def build_task(run_agent: Callable[[str], dict]) -> Callable[[Any], dict]:
    """Wrap a meal-logging callable as a Phoenix task over example inputs.

    *run_agent* takes the free-text meal and returns the agent's logged output
    (the ``LoggedMeal`` shape the evaluators read). The returned task accepts the
    example's ``input`` — a ``{"text": ...}`` dict or a bare string.
    """

    def task(example_input: Any) -> dict:
        text = example_input["text"] if isinstance(example_input, dict) else example_input
        return run_agent(text)

    return task


def run(
    client: Any,
    dataset: Any,
    run_agent: Callable[[str], dict],
    *,
    experiment_name: str,
    evaluators: list[Callable] | None = None,
) -> Any:
    """Run a Phoenix experiment for *dataset* using *run_agent* as the task.

    Attaches the full numeric evaluator panel unless *evaluators* overrides it.
    Returns whatever the Phoenix client returns for the run.
    """
    return client.experiments.run_experiment(
        dataset=dataset,
        task=build_task(run_agent),
        evaluators=list(evaluators) if evaluators is not None else list(EVALUATORS),
        experiment_name=experiment_name,
    )
