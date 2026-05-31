"""Run the supervisor against real Phoenix experiments via the Phoenix MCP server.

The self-supervision loop: the supervisor reads each experiment's
per-case results through the Phoenix MCP server, re-scores them with the numeric
evaluators, classifies each case's accuracy trend (improving / stable /
regressing), and for a regressing case proposes a prompt fix and — with
--open-pr — opens a GitHub PR for a human to review.

    set -a && . ./.env && set +a
    uv run python scripts/run_supervisor.py --experiments EXP_OLDEST ... EXP_NEWEST
"""

from __future__ import annotations

import argparse
import asyncio

from dietrace.agents.supervisor.classifier import classify_trends
from dietrace.agents.supervisor.phoenix_mcp import PhoenixMCPClient
from dietrace.agents.supervisor.pr import open_pr
from dietrace.agents.supervisor.proposer import propose_patch
from dietrace.agents.supervisor.reader import CaseResult, ExperimentSummary
from dietrace.evals.evaluators import macro_pct_error

_MAX_PRS = 1  # keep the demo to a single PR / proposer call


def _summary(mcp: PhoenixMCPClient, experiment_id: str) -> ExperimentSummary:
    """Read one experiment's results via MCP and re-score each case."""
    results = asyncio.run(mcp.get_experiment_results(experiment_id))
    cases: list[CaseResult] = []
    for r in results:
        output = r.get("output") or {}
        expected = r.get("reference_output") or {}
        label = "fail"
        score: float | None = None
        try:
            ev = macro_pct_error(output, expected)
            score, label = ev.score, ev.label
        except Exception:  # noqa: BLE001 — a malformed run scores as unknown, not a crash
            label = "error"
        cases.append(
            CaseResult(
                example_id=(r.get("input") or {}).get("text") or r.get("example_id", "?"),
                run_id=r.get("example_id", ""),
                output=output,
                score=score,
                label=label,
                passed=(score or 0.0) >= 0.5,
            )
        )
    return ExperimentSummary(
        experiment_id=experiment_id, experiment_name=experiment_id, case_results=cases
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the supervisor over experiments.")
    parser.add_argument(
        "--experiments", nargs="+", required=True, help="experiment ids, OLDEST first"
    )
    parser.add_argument("--open-pr", action="store_true", help="open a real PR (else dry-run)")
    args = parser.parse_args()

    mcp = PhoenixMCPClient()
    print(f"Reading {len(args.experiments)} experiments via Phoenix MCP...")
    summaries = [_summary(mcp, eid) for eid in args.experiments]  # oldest-first
    for summary in summaries:
        scores = [c.score for c in summary.case_results if c.score is not None]
        mean = sum(scores) / len(scores) if scores else 0.0
        print(f"  {summary.experiment_id}: mean macro accuracy {mean:.3f} ({len(scores)} scored)")

    # Stub the borderline LLM judge so classification stays offline + deterministic.
    trends = classify_trends(summaries, _llm_judge_fn=lambda example_id, scores: "stable")

    print("\nPer-case accuracy trend:")
    for t in sorted(trends, key=lambda t: t.trend):
        rounded = [round(x, 2) for x in t.scores]
        print(f"  [{t.trend:10s}] {t.example_id[:36]:36s} scores={rounded}")

    regressions = [t for t in trends if t.trend == "regressing"]
    print(f"\nRegressions detected: {len(regressions)}")

    for trend in regressions[:_MAX_PRS]:
        print(f"\nProposing a fix for regressing case {trend.example_id!r} (live Gemini)...")
        diff = propose_patch(
            example_id=trend.example_id,
            case_input=trend.example_id,
            case_expected="accurate macros within the ±15% tolerance band",
            agent_output=f"macro accuracy score trend {[round(x, 2) for x in trend.scores]}",
            trace_summary="macro accuracy regressed across consecutive experiments",
        )
        print(f"--- proposed instruction diff ---\n{diff[:700]}\n--- end diff ---")
        result = open_pr(
            case_id=trend.example_id,
            diff=diff,
            rationale=f"Macro accuracy regressed: scores {[round(x, 2) for x in trend.scores]}.",
            repo="colinh09/DietTrace",
            dry_run=not args.open_pr,
        )
        if result.pr_number:
            print(f"Opened PR #{result.pr_number}: {result.pr_url}")
        else:
            print(f"(dry-run) would open PR on branch {result.branch}")


if __name__ == "__main__":
    main()
