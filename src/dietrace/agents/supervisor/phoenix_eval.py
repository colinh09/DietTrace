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


def row_data(results: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Map each example's meal text → ``{acc, expected, est}`` (accuracy, the truth
    kcal, and this run's estimate kcal) for the per-meal table the rail shows. Skips
    rows missing an estimate or a truth."""
    out: dict[str, dict[str, float]] = {}
    for r in results or []:
        text = (r.get("input") or {}).get("text", "")
        est = (r.get("output") or {}).get("calories")
        ref = (r.get("reference_output") or {}).get("calories")
        if text and est is not None and ref is not None:
            out[text] = {
                "acc": accuracy(float(est), float(ref)),
                "expected": float(ref),
                "est": float(est),
            }
    return out


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
    """Run one experiment (agent+block over *dataset*) → its experiment id, taken
    straight off the RanExperiment return (so base/tuned can run in parallel without
    racing on a 'most recent experiment' lookup)."""
    from dietrace.web.memory import calories_of

    ex_block = [{"preference_block": block}] if block else []

    def task(example: Any) -> dict[str, Any]:
        totals = logger_fn(_example_text(example), examples=ex_block).get("totals", [])
        return {"calories": calories_of(totals)}

    def calorie_accuracy(output: Any, expected: Any) -> float:
        return accuracy(
            (output or {}).get("calories", 0.0), (expected or {}).get("calories", 0.0)
        )

    ran = client.experiments.run_experiment(
        dataset=dataset,
        task=task,
        evaluators=[calorie_accuracy],
        experiment_name=name,
        print_summary=False,
        timeout=180,
    )
    return (
        ran.get("experiment_id")
        if isinstance(ran, dict)
        else getattr(ran, "experiment_id", None)
    )


def _results_via_mcp(experiment_id: str) -> list[dict[str, Any]]:  # pragma: no cover
    """Per-example results for an experiment, read back over MCP (the load-bearing read)."""
    from dietrace.agents.supervisor.phoenix_mcp import PhoenixMCPClient

    async def _pull() -> list[dict[str, Any]]:
        return await PhoenixMCPClient().get_experiment_results(experiment_id)

    return asyncio.run(_pull()) or []


def _score_set_via_phoenix(
    user: str,
    set_name: str,
    dataset_name: str,
    dataset_desc: str,
    cases: list[dict[str, Any]] | None,
    current_block: str,
    proposed_block: str,
    logger_fn: Callable[..., dict],
) -> dict[str, Any] | None:  # pragma: no cover - live
    """Score one case set as base/tuned Phoenix experiments, read back over MCP.

    REBUILDS *dataset_name* to exactly mirror *cases* (``create_dataset`` on an
    existing name replaces its examples with a fresh version, so a meal can never end
    up scored against the wrong truth), runs the current vs proposed block over it as
    two parallel experiments, and returns ``{"current", "proposed", "experiment_url",
    "rows"}`` — mean accuracies (base/tuned) plus per-meal rows ``{text, expected,
    before, after, base_kcal, tuned_kcal}`` for the rail — or ``None`` on any failure
    so the caller falls back to local scoring.
    """
    try:
        from dietrace.agents.supervisor.phoenix_mcp import mcp_available

        if not mcp_available():
            return None
        client = _phoenix_client()
        if client is None:
            return None
        by_text = {c["text"]: c for c in (cases or []) if c.get("text")}
        if not by_text:
            return None
        set_cases = list(by_text.values())
        dataset = client.datasets.create_dataset(
            name=dataset_name,
            inputs=[{"text": c["text"]} for c in set_cases],
            outputs=[{"calories": c["calories"]} for c in set_cases],
            dataset_description=dataset_desc,
        )
        if not getattr(dataset, "example_count", 0):
            return None

        # Run base + tuned experiments IN PARALLEL — independent (same dataset, two
        # prompts), and the food repo opens a SQLite connection per query so the agent
        # is thread-safe. Halves the wall-clock vs running them back-to-back.
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as pool:
            base_fut = pool.submit(
                _run_experiment, client, dataset, current_block, logger_fn,
                f"dietrace-{user}-{set_name}-base",
            )
            tuned_fut = pool.submit(
                _run_experiment, client, dataset, proposed_block, logger_fn,
                f"dietrace-{user}-{set_name}-tuned",
            )
            base_id, tuned_id = base_fut.result(), tuned_fut.result()

        base = row_data(_results_via_mcp(base_id)) if base_id else {}
        tuned = row_data(_results_via_mcp(tuned_id)) if tuned_id else {}
        if not base or not tuned:
            return None
        current_acc = round(sum(d["acc"] for d in base.values()) / len(base), 3)
        proposed_acc = round(sum(d["acc"] for d in tuned.values()) / len(tuned), 3)
        rows = [
            {
                "text": text,
                "expected": round(d["expected"]),
                "before": d["acc"],
                "after": (tuned.get(text) or {}).get("acc"),
                "base_kcal": round(d["est"]),
                "tuned_kcal": round((tuned.get(text) or {}).get("est", 0)),
            }
            for text, d in base.items()
        ]

        url = ""
        try:
            url = client.experiments.get_dataset_experiments_url(dataset_id=dataset.id)
        except Exception:
            url = ""
        return {
            "current": current_acc,
            "proposed": proposed_acc,
            "experiment_url": url,
            "rows": rows,
        }
    except Exception:
        return None


def score_fit_via_phoenix(
    user: str,
    current_block: str,
    proposed_block: str,
    logger_fn: Callable[..., dict],
    fit_cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:  # pragma: no cover - live
    """Score the user's confirmed-meal (fit) set in Arize — each retune rebuilds the
    user's Phoenix dataset to exactly mirror the current confirmations."""
    from dietrace.agents.supervisor.phoenix_mcp import user_dataset_name

    return _score_set_via_phoenix(
        user, "fit", user_dataset_name(user),
        "DietTrace user confirmed meals — the gate's fit set",
        fit_cases, current_block, proposed_block, logger_fn,
    )


def score_usda_via_phoenix(
    user: str,
    current_block: str,
    proposed_block: str,
    logger_fn: Callable[..., dict],
    usda_cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:  # pragma: no cover - live
    """Score the USDA reference (floor) set in Arize too, so the everyday-foods
    check is a Phoenix experiment like the fit set — not just a local re-score."""
    return _score_set_via_phoenix(
        user, "usda", f"dietrace-usda-{user}",
        "DietTrace USDA reference foods — the gate's everyday-accuracy floor",
        usda_cases, current_block, proposed_block, logger_fn,
    )
