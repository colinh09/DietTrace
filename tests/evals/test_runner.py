"""The experiment runner wires task + evaluators into Phoenix.

The Phoenix client is mocked, so these assert the wiring — that the meal-logging
callable is wrapped as a task and the numeric evaluator panel is attached —
without any network or Vertex call.
"""

from unittest.mock import MagicMock

from dietrace.evals import runner


def test_run_wires_task_and_default_evaluators() -> None:
    client = MagicMock()
    sentinel = object()
    client.experiments.run_experiment.return_value = sentinel

    def run_agent(text: str) -> dict:
        return {"totals": [], "echo": text}

    result = runner.run(
        client, dataset="ds", run_agent=run_agent, experiment_name="exp-1"
    )

    assert result is sentinel
    client.experiments.run_experiment.assert_called_once()
    kwargs = client.experiments.run_experiment.call_args.kwargs
    assert kwargs["dataset"] == "ds"
    assert kwargs["experiment_name"] == "exp-1"
    assert kwargs["evaluators"] == runner.PHOENIX_EVALUATORS
    # The wrapped task binds the example input and calls the agent.
    assert kwargs["task"]({"text": "2 eggs"}) == {"totals": [], "echo": "2 eggs"}


def test_run_accepts_custom_evaluators() -> None:
    client = MagicMock()
    runner.run(
        client,
        dataset="ds",
        run_agent=lambda t: {},
        experiment_name="exp-2",
        evaluators=[len],
    )
    kwargs = client.experiments.run_experiment.call_args.kwargs
    assert kwargs["evaluators"] == [len]


def test_build_task_accepts_bare_string_input() -> None:
    task = runner.build_task(lambda text: {"logged": text})
    assert task("1 banana") == {"logged": "1 banana"}
