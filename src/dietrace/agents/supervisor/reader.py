"""Eval result reader for the supervisor agent.

Normalizes raw Phoenix experiment payloads (as returned by the Phoenix MCP
server) into comparable per-case results across runs. Metric-agnostic: it reads
whatever numeric score and label each evaluator attached, so it works unchanged
for DietTrace's numeric macro-accuracy evals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CaseResult:
    """Normalized result for a single eval case across one experiment run."""

    example_id: str
    run_id: str
    output: Any
    score: float | None
    label: str
    passed: bool


@dataclass
class ExperimentSummary:
    """Normalized summary for one experiment run."""

    experiment_id: str
    experiment_name: str
    case_results: list[CaseResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        """Fraction of cases that passed (0.0 if no results)."""
        if not self.case_results:
            return 0.0
        return sum(1 for r in self.case_results if r.passed) / len(self.case_results)

    @property
    def mean_score(self) -> float | None:
        """Average numeric score across cases, or None if no scores present."""
        scores = [r.score for r in self.case_results if r.score is not None]
        if not scores:
            return None
        return sum(scores) / len(scores)


def _normalize_label(label: str | None) -> str:
    """Coerce various label strings to a canonical lower-case label."""
    if not label:
        return "unknown"
    return label.lower().strip()


def _is_passing(label: str, score: float | None) -> bool:
    """Determine pass/fail from label and optional score."""
    passing_labels = {"pass", "true", "correct", "yes", "1"}
    failing_labels = {"fail", "false", "incorrect", "no", "error", "0"}
    norm = _normalize_label(label)
    if norm in passing_labels:
        return True
    if norm in failing_labels:
        return False
    if score is not None:
        return score >= 0.5
    return False


def _extract_case_results(run: dict[str, Any]) -> list[CaseResult]:
    """Extract per-case results from a single experiment run dict."""
    run_id = run.get("id", "")
    example_id = run.get("datasetExampleId") or run.get("example_id", "")
    output = run.get("output")

    evaluations = run.get("annotations") or run.get("evaluations") or []

    if not evaluations:
        score_val = run.get("score")
        score = float(score_val) if score_val is not None else None
        label = _normalize_label(str(run.get("label", "")))
        return [
            CaseResult(
                example_id=example_id,
                run_id=run_id,
                output=output,
                score=score,
                label=label,
                passed=_is_passing(label, score),
            )
        ]

    results: list[CaseResult] = []
    for annotation in evaluations:
        score_val = annotation.get("score")
        score = float(score_val) if score_val is not None else None
        label = _normalize_label(str(annotation.get("label", "")))
        results.append(
            CaseResult(
                example_id=example_id,
                run_id=run_id,
                output=output,
                score=score,
                label=label,
                passed=_is_passing(label, score),
            )
        )
    return results


def normalize_experiments(experiments: list[dict[str, Any]]) -> list[ExperimentSummary]:
    """Normalize raw experiment dicts into ExperimentSummary objects, in input order.

    Each experiment dict is expected to have the shape returned by
    ``PhoenixMCPClient.get_recent_experiments()``: a dict with ``id``, ``name``,
    and a list of runs (keyed as ``runs`` or ``experimentRuns``).
    """
    summaries: list[ExperimentSummary] = []
    for exp in experiments:
        exp_id = exp.get("id", "")
        exp_name = exp.get("name") or exp.get("experimentName", "")
        runs: list[dict[str, Any]] = exp.get("runs") or exp.get("experimentRuns") or []

        case_results: list[CaseResult] = []
        for run in runs:
            case_results.extend(_extract_case_results(run))

        summaries.append(
            ExperimentSummary(
                experiment_id=exp_id,
                experiment_name=exp_name,
                case_results=case_results,
            )
        )
    return summaries


def read_recent(
    dataset_id: str,
    limit: int = 10,
    *,
    mcp_client: Any | None = None,
) -> list[ExperimentSummary]:
    """Pull and normalize the last N experiments for a dataset (most-recent first)."""
    import asyncio

    from dietrace.agents.supervisor.phoenix_mcp import PhoenixMCPClient

    client = mcp_client if mcp_client is not None else PhoenixMCPClient()
    raw_experiments = asyncio.run(client.get_recent_experiments(dataset_id, limit=limit))
    return normalize_experiments(raw_experiments)
