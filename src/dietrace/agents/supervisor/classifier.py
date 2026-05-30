"""Regression classifier for the supervisor agent.

Given recent experiments (oldest-first), classifies each eval case's accuracy
trend as improving / stable / regressing. A score delta drives a heuristic for
clear-cut cases; an LLM-as-judge resolves borderline ones. Scores are the
normalized [0,1] accuracy from the numeric evaluators, so a falling score is a
regression.
"""

from __future__ import annotations

import textwrap
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from dietrace.agents.supervisor.reader import ExperimentSummary

Trend = Literal["improving", "stable", "regressing"]
LLMJudge = Callable[[str, list[float]], Trend]


@dataclass
class CaseTrend:
    """Classification result for a single eval case across runs."""

    example_id: str
    trend: Trend
    score_delta: float | None
    runs_analyzed: int
    scores: list[float]


def _heuristic_trend(scores: list[float], threshold: float) -> Trend | None:
    """Classify from a score sequence (oldest-first); None when borderline."""
    if len(scores) < 2:
        return "stable"
    delta = scores[-1] - scores[0]
    if delta > threshold:
        return "improving"
    if delta < -threshold:
        return "regressing"
    return None


def _llm_judge(example_id: str, scores: list[float]) -> Trend:  # pragma: no cover
    """Use Gemini to classify a borderline trend (lazy import; live call)."""
    from google import genai

    from dietrace.llm.config import GEMINI_LOCATION, GEMINI_MODEL, GEMINI_PROJECT

    prompt = textwrap.dedent(f"""
        You are an eval trend classifier. A nutrition-accuracy test case ran across
        {len(scores)} experiment runs and produced the following scores
        (oldest → newest), where higher is more accurate:

        {scores}

        Eval case ID: {example_id}

        Classify the trend as one of: improving, stable, regressing.

        Rules:
        - "improving": scores are generally increasing over time
        - "regressing": scores are generally decreasing over time
        - "stable": scores fluctuate without a clear directional trend

        Respond with ONLY one of the three words: improving, stable, or regressing.
    """).strip()

    client = genai.Client(vertexai=True, project=GEMINI_PROJECT, location=GEMINI_LOCATION)
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    raw = response.text.strip().lower()
    if "improving" in raw:
        return "improving"
    if "regressing" in raw:
        return "regressing"
    return "stable"


def _collect_scores_by_case(
    summaries: list[ExperimentSummary],
) -> dict[str, list[float]]:
    """Build a map of example_id -> [scores oldest-first], skipping unscored runs."""
    scores_by_case: dict[str, list[float]] = defaultdict(list)
    seen_per_experiment: dict[int, set[str]] = defaultdict(set)

    for exp_idx, summary in enumerate(summaries):
        for result in summary.case_results:
            if result.score is None:
                continue
            if result.example_id in seen_per_experiment[exp_idx]:
                continue
            seen_per_experiment[exp_idx].add(result.example_id)
            scores_by_case[result.example_id].append(result.score)

    return dict(scores_by_case)


def classify_trends(
    summaries: list[ExperimentSummary],
    *,
    borderline_threshold: float = 0.1,
    min_runs: int = 2,
    _llm_judge_fn: LLMJudge | None = None,
) -> list[CaseTrend]:
    """Classify score trends across experiments for each eval case.

    *summaries* must be ordered oldest-first. Cases with fewer than *min_runs*
    scored runs are "stable" (insufficient data). When the delta
    (last - first) is within *borderline_threshold*, the LLM judge decides.
    Returns one CaseTrend per example_id, sorted by example_id.
    """
    judge = _llm_judge_fn if _llm_judge_fn is not None else _llm_judge

    scores_by_case = _collect_scores_by_case(summaries)

    results: list[CaseTrend] = []
    for example_id, scores in sorted(scores_by_case.items()):
        if len(scores) < min_runs:
            results.append(
                CaseTrend(
                    example_id=example_id,
                    trend="stable",
                    score_delta=None,
                    runs_analyzed=len(scores),
                    scores=scores,
                )
            )
            continue

        delta = scores[-1] - scores[0]
        heuristic = _heuristic_trend(scores, borderline_threshold)
        trend: Trend = heuristic if heuristic is not None else judge(example_id, scores)

        results.append(
            CaseTrend(
                example_id=example_id,
                trend=trend,
                score_delta=delta,
                runs_analyzed=len(scores),
                scores=scores,
            )
        )

    return results
