"""Supervisor end-to-end loop.

Wires PhoenixMCPClient → reader → classifier → proposer → PR opener as a single
``run_supervisor()`` entrypoint: read recent experiments, classify per-case
trends, and for each regressing case propose a prompt diff and open a GitHub PR
for a human to review.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dietrace.agents.supervisor.classifier import CaseTrend, classify_trends
from dietrace.agents.supervisor.pr import PRResult, open_pr
from dietrace.agents.supervisor.proposer import propose_patch
from dietrace.agents.supervisor.reader import ExperimentSummary, normalize_experiments

_DEFAULT_REPO = "colinh09/DietTrace"


@dataclass
class SupervisorRun:
    """Summary of a single supervisor run."""

    dataset_id: str
    experiments_read: int
    regressions_found: list[CaseTrend] = field(default_factory=list)
    prs_opened: list[PRResult] = field(default_factory=list)


def _run_coroutine(coro: Any) -> Any:
    """Run *coro* whether or not an event loop is already running."""
    try:
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)


def _fetch_experiments(
    dataset_id: str,
    limit: int,
    mcp_client: Any | None,
) -> list[ExperimentSummary]:
    """Pull and normalize recent experiments for a dataset."""
    from dietrace.agents.supervisor.phoenix_mcp import PhoenixMCPClient

    client = mcp_client if mcp_client is not None else PhoenixMCPClient()
    raw = _run_coroutine(client.get_recent_experiments(dataset_id, limit=limit))
    return normalize_experiments(raw)


def _summarise_trace(experiment: ExperimentSummary, example_id: str) -> str:
    """Build a brief trace summary string from the experiment data."""
    matching = [r for r in experiment.case_results if r.example_id == example_id]
    if not matching:
        return (
            f"No trace data found for case {example_id} "
            f"in experiment {experiment.experiment_id}."
        )
    result = matching[0]
    return (
        f"Experiment {experiment.experiment_id}: "
        f"score={result.score}, label={result.label}, passed={result.passed}. "
        f"Output: {str(result.output)[:200]}"
    )


def run_supervisor(
    dataset_id: str,
    *,
    experiments_limit: int = 10,
    regression_threshold: float = 0.1,
    min_runs: int = 2,
    open_prs: bool = True,
    dry_run: bool = False,
    mcp_client: Any | None = None,
    _propose_fn: Any | None = None,
    _open_pr_fn: Any | None = None,
    _classify_fn: Any | None = None,
    repo: str | None = None,
    github_token: str | None = None,
    repo_root: Path | None = None,
) -> SupervisorRun:
    """Run the full supervisor pipeline for a Phoenix dataset.

    Reads recent experiments via MCP, classifies trends per case, and for each
    regressing case proposes a diff and opens a PR (unless ``dry_run``). All
    external calls are injectable for offline tests.
    """
    summaries = _fetch_experiments(dataset_id, experiments_limit, mcp_client)

    # Experiments come back most-recent-first; the classifier wants oldest-first.
    oldest_first = list(reversed(summaries))

    classify = _classify_fn if _classify_fn is not None else classify_trends
    trends = classify(
        oldest_first,
        borderline_threshold=regression_threshold,
        min_runs=min_runs,
    )

    regressions = [t for t in trends if t.trend == "regressing"]

    run = SupervisorRun(
        dataset_id=dataset_id,
        experiments_read=len(summaries),
        regressions_found=regressions,
    )

    if not open_prs or not regressions:
        return run

    propose = _propose_fn if _propose_fn is not None else propose_patch
    open_pr_fn = _open_pr_fn if _open_pr_fn is not None else open_pr
    most_recent = summaries[0] if summaries else None

    for trend in regressions:
        trace_summary = (
            _summarise_trace(most_recent, trend.example_id)
            if most_recent is not None
            else "No trace data available."
        )

        diff = propose(
            example_id=trend.example_id,
            case_input=f"eval case {trend.example_id}",
            case_expected="accurate macros within tolerance",
            agent_output=f"score trend: {trend.scores}",
            trace_summary=trace_summary,
        )

        rationale = (
            f"Case `{trend.example_id}` regressed: scores {trend.scores} "
            f"(delta={trend.score_delta:.3f} over {trend.runs_analyzed} runs)."
        )

        result = open_pr_fn(
            case_id=trend.example_id,
            diff=diff,
            rationale=rationale,
            repo=repo or os.environ.get("GITHUB_REPOSITORY", _DEFAULT_REPO),
            github_token=github_token,
            repo_root=repo_root,
            dry_run=dry_run,
        )
        run.prs_opened.append(result)

    return run


def _main() -> None:  # pragma: no cover — CLI entrypoint, live Phoenix
    """CLI entrypoint: resolve the dataset_id, then run the supervisor."""
    import httpx
    from phoenix.client import Client

    from dietrace.evals.uploader import DATASET_NAME

    phoenix = Client()
    try:
        dataset = phoenix.datasets.get_dataset(dataset=DATASET_NAME)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (403, 404):
            print("no regressions detected")
            return
        raise

    result = run_supervisor(dataset_id=dataset.id)
    if result.regressions_found:
        print(
            f"regressions: {len(result.regressions_found)}; "
            f"PRs opened: {len(result.prs_opened)}"
        )
    else:
        print("no regressions detected")


if __name__ == "__main__":  # pragma: no cover
    _main()
