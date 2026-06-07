"""Live experiment glue for the supervisor (untested — needs Phoenix + Vertex).

The *tested* retune orchestration (propose → gate → ship) lives in the
``/learning/retune`` handler; this module holds the live experiment runner the
``/experiments/run`` endpoint calls by default. There is no ``run-experiment`` MCP
tool, so we run the experiment here (via the Phoenix SDK) and read the results
back over MCP elsewhere. All live paths are fail-soft and excluded from coverage;
tests inject a fake runner.
"""

from __future__ import annotations

from typing import Any


def default_experiment_runner(spec: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover - live
    """Run an eval experiment for *spec* and return a summary dict.

    ``spec`` is ``{"dataset": <id|name>, "name": <experiment label>}``. Fail-soft:
    returns an ``unavailable`` summary when Phoenix/Vertex aren't configured so the
    endpoint degrades instead of raising.
    """
    from dietrace.agents.supervisor.phoenix_mcp import mcp_available

    if not mcp_available():
        return {"status": "unavailable", "reason": "Phoenix not configured"}

    try:
        import phoenix as px

        from dietrace.evals import runner as eval_runner
        from dietrace.nutrition.repository import FoodRepository
        from dietrace.web.memory import build_memory  # noqa: F401  (warms config)

        client = px.Client()
        dataset = client.get_dataset(name=spec["dataset"])
        repo = FoodRepository()

        def run_agent(text: str) -> dict:
            from dietrace.agents.nutrition.orchestrator import log_meal

            return log_meal(text, repo).model_dump()

        ran = eval_runner.run(
            client,
            dataset,
            run_agent,
            experiment_name=spec.get("name", "dietrace-supervisor"),
        )
        return {"status": "done", "experiment_id": getattr(ran, "id", None)}
    except Exception as exc:  # fail-soft: surface, don't crash the endpoint
        return {"status": "error", "reason": str(exc)}
