"""Phoenix experiment runner for the nutrition eval suite.

``run()`` drives a Phoenix experiment: it pairs an uploaded ``Dataset`` with a
*task* (the agent logging each meal) and the numeric evaluators, and calls the
Phoenix client's ``experiments.run_experiment``. Phoenix binds the task's
``input`` param to each example's input and the evaluators' ``output``/
``expected``/``metadata`` params to the run output, ground truth, and case
metadata. The Phoenix client is injected so the wiring is testable offline.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dietrace.evals.evaluators import PHOENIX_EVALUATORS


def build_task(run_agent: Callable[[str], dict]) -> Callable[..., dict]:
    """Wrap a meal-logging callable as a Phoenix task over example inputs.

    *run_agent* takes the free-text meal and returns the agent's logged output
    (the ``LoggedMeal`` shape the evaluators read). Phoenix binds the returned
    task's ``input`` param to the example's input — a ``{"text": ...}`` dict.
    """

    def task(input: dict) -> dict:  # noqa: A002 — Phoenix binds this to the example input
        text = input["text"] if isinstance(input, dict) else input
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
    Returns the Phoenix ``RanExperiment``.
    """
    return client.experiments.run_experiment(
        dataset=dataset,
        task=build_task(run_agent),
        evaluators=list(evaluators) if evaluators is not None else list(PHOENIX_EVALUATORS),
        experiment_name=experiment_name,
    )
