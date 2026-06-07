"""Phoenix-experiment gate scoring for the user's confirmed-meal set (live path).

The gate's *fit* score (how well the agent does on the user's own confirmed meals)
is computed by running the agent over the user's Phoenix dataset as real
experiments — base block vs proposed block — and reading the per-example results
back over MCP (``get-experiment-by-id``). This is what makes MCP load-bearing for
the gate, not just the dataset writes: the agent reads its own eval.

Only the FIT set runs through Phoenix (it is small — the user's confirmed meals);
the USDA floor stays local for speed (it is a "can't regress" guardrail, not the
learning signal). Everything here is fail-soft: any missing dataset / Phoenix / MCP
error returns ``None`` so the caller falls back to local scoring and the demo never
hangs. The live experiment plumbing is excluded from coverage; the pure helpers
(:func:`accuracy`, :func:`mean_accuracy`) are unit-tested.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import Any


def accuracy(estimate: float, expected: float) -> float:
    """Calorie accuracy in [0, 1] (1.0 exact), matching the local evaluator."""
    if expected <= 0:
        return 1.0 if estimate == 0 else 0.0
    return round(max(0.0, 1.0 - abs(estimate - expected) / expected), 3)


def mean_accuracy(results: list[dict[str, Any]]) -> float | None:
    """Mean calorie accuracy over MCP experiment results (output vs reference_output).

    Each result is one example: ``{"output": {"calories": ...}, "reference_output":
    {"calories": ...}, ...}``. Returns ``None`` when no scorable rows are present.
    """
    accs: list[float] = []
    for r in results or []:
        out = (r.get("output") or {}).get("calories")
        ref = (r.get("reference_output") or {}).get("calories")
        if out is not None and ref is not None:
            accs.append(accuracy(float(out), float(ref)))
    return round(sum(accs) / len(accs), 3) if accs else None


def _phoenix_client() -> Any | None:  # pragma: no cover - live
    """A REST Phoenix client (the one whose auth actually works), or None."""
    base = os.environ.get("PHOENIX_BASE_URL", "")
    key = os.environ.get("PHOENIX_API_KEY", "")
    if not base or not key:
        return None
    if not base.startswith("http"):
        base = "https://" + base
    from phoenix.client import Client

    return Client(base_url=base, api_key=key)


def _example_text(example: Any) -> str:  # pragma: no cover - live
    inp = example["input"] if isinstance(example, dict) else getattr(example, "input", {})
    return (inp or {}).get("text", "")


def _run_experiment(
    client: Any, dataset: Any, block: str, logger_fn: Callable[..., dict], name: str
) -> str | None:  # pragma: no cover - live
    """Run one experiment (agent+block over *dataset*) → its experiment id via MCP."""
    from dietrace.web.memory import calories_of

    ex_block = [{"preference_block": block}] if block else []

    def task(example: Any) -> dict[str, Any]:
        totals = logger_fn(_example_text(example), examples=ex_block).get("totals", [])
        return {"calories": calories_of(totals)}

    def calorie_accuracy(output: Any, expected: Any) -> float:
        return accuracy(
            (output or {}).get("calories", 0.0), (expected or {}).get("calories", 0.0)
        )

    client.experiments.run_experiment(
        dataset=dataset,
        task=task,
        evaluators=[calorie_accuracy],
        experiment_name=name,
        print_summary=False,
        timeout=180,
    )
    # The just-created experiment is the most recent for this dataset.
    from dietrace.agents.supervisor.phoenix_mcp import PhoenixMCPClient

    async def _latest() -> str | None:
        exps = await PhoenixMCPClient().get_recent_experiments(dataset.id, limit=1)
        return exps[0].get("id") if exps else None

    return asyncio.run(_latest())


def _score_via_mcp(experiment_id: str) -> float | None:  # pragma: no cover - live
    """Mean accuracy for an experiment, read back over MCP (the load-bearing read)."""
    from dietrace.agents.supervisor.phoenix_mcp import PhoenixMCPClient

    async def _pull() -> list[dict[str, Any]]:
        return await PhoenixMCPClient().get_experiment_results(experiment_id)

    return mean_accuracy(asyncio.run(_pull()))


def score_fit_via_phoenix(
    user: str, current_block: str, proposed_block: str, logger_fn: Callable[..., dict]
) -> dict[str, Any] | None:  # pragma: no cover - live
    """Score the user's confirmed-meal set as base/tuned Phoenix experiments.

    Returns ``{"current": <fit>, "proposed": <fit>, "experiment_url": <str>}`` (fit
    accuracies pulled over MCP), or ``None`` on any failure so the caller falls back
    to local scoring.
    """
    try:
        from dietrace.agents.supervisor.phoenix_mcp import (
            mcp_available,
            user_dataset_name,
        )

        if not mcp_available():
            return None
        client = _phoenix_client()
        if client is None:
            return None
        dataset = client.datasets.get_dataset(dataset=user_dataset_name(user))
        if not getattr(dataset, "example_count", 0):
            return None

        base_id = _run_experiment(
            client, dataset, current_block, logger_fn, f"dietrace-{user}-fit-base"
        )
        tuned_id = _run_experiment(
            client, dataset, proposed_block, logger_fn, f"dietrace-{user}-fit-tuned"
        )
        current_fit = _score_via_mcp(base_id) if base_id else None
        proposed_fit = _score_via_mcp(tuned_id) if tuned_id else None
        if current_fit is None or proposed_fit is None:
            return None

        url = ""
        try:
            url = client.experiments.get_dataset_experiments_url(dataset_id=dataset.id)
        except Exception:
            url = ""
        return {
            "current": current_fit,
            "proposed": proposed_fit,
            "experiment_url": url,
        }
    except Exception:
        return None
