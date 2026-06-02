"""The accuracy / Arize-observability report surfaced in the web app.

DietTrace's accuracy is held to account by Arize Phoenix: every logged meal is
traced, an eval suite scores estimates against USDA ground truth as Phoenix
experiments, and a supervisor agent reads those experiments back over the
Phoenix MCP server to open prompt-fix PRs when accuracy regresses. ``GET
/accuracy`` surfaces that loop — and the measured before/after numbers.

The numbers are read **live** from the Phoenix experiments (cached briefly) and
fall back to the last measured values when Phoenix is unreachable.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dietrace.evals.uploader import DATASET_NAME

# Last measured mean evaluator scores (0–1) — the fallback when Phoenix is
# unreachable (and what the live read maps onto).
_BASELINE = {"macro": 0.047, "calorie": 0.016, "within_tolerance": 0.0, "portion": 0.128}
_CURRENT = {"macro": 0.577, "calorie": 0.601, "within_tolerance": 0.375, "portion": 0.583}

# UI metric key -> the Phoenix evaluator name it reads from.
_EVALUATOR_OF = {
    "calorie": "calorie_accuracy",
    "macro": "macro_pct_error",
    "within_tolerance": "within_tolerance",
    "portion": "portion_error",
}

_METRICS = [
    {"key": "calorie", "label": "Calorie accuracy"},
    {"key": "macro", "label": "Macro accuracy"},
    {"key": "within_tolerance", "label": "Within ±15%"},
    {"key": "portion", "label": "Portion accuracy"},
]

_LOOP = [
    {
        "step": "trace",
        "label": "Every logged meal is traced to Arize Phoenix (OpenInference spans).",
    },
    {
        "step": "evaluate",
        "label": "An eval suite scores each estimate against USDA ground truth "
        "as a Phoenix experiment.",
    },
    {
        "step": "detect",
        "label": "A supervisor agent reads the experiments back over the Phoenix "
        "MCP server and classifies each case improving / stable / regressing.",
    },
    {
        "step": "improve",
        "label": "On a regression it proposes a prompt fix and opens a GitHub PR "
        "— human-in-the-loop.",
    },
]


def phoenix_dashboard_url() -> str:
    """The Arize Phoenix workspace URL (from ``PHOENIX_BASE_URL``)."""
    return os.environ.get("PHOENIX_BASE_URL", "https://app.phoenix.arize.com")


def _case_count() -> int:
    """The number of eval cases in the USDA-grounded dataset."""
    directory = Path("evals/dataset/nutrition")
    return len(list(directory.glob("*.json"))) if directory.exists() else 0


def _experiment_means(client: Any, experiment_id: str) -> dict[str, float]:
    """Mean score per evaluator for one Phoenix experiment."""
    ran = client.experiments.get_experiment(experiment_id=experiment_id)
    by_name: dict[str, list[float]] = defaultdict(list)
    for run in ran["evaluation_runs"]:
        result = run.result if isinstance(run.result, dict) else {}
        score = result.get("score")
        if score is not None:
            by_name[run.name].append(score)
    return {name: sum(scores) / len(scores) for name, scores in by_name.items()}


def _fetch_live_scores() -> dict[str, Any] | None:
    """Read the eval experiments from Phoenix; baseline = oldest run, current =
    latest run.

    Returns ``{baseline, current, experiments}`` keyed by evaluator name, or None
    when Phoenix is unreachable / unconfigured (caller falls back to measured).
    """
    api_key = os.environ.get("PHOENIX_API_KEY")
    base_url = os.environ.get("PHOENIX_BASE_URL")
    if not api_key or not base_url:
        return None
    try:
        from phoenix.client import Client

        client = Client(base_url=base_url, api_key=api_key)
        dataset = client.datasets.get_dataset(dataset=DATASET_NAME)
        experiments = client.experiments.list(dataset_id=dataset.id)

        runs: list[dict[str, Any]] = []
        for exp in experiments:
            exp_id = exp["id"] if isinstance(exp, dict) else exp.id
            created = (exp.get("created_at") if isinstance(exp, dict) else "") or ""
            scores = _experiment_means(client, exp_id)
            if scores:
                runs.append({"created": created, "scores": scores})
        if not runs:
            return None

        runs.sort(key=lambda r: r["created"])
        return {
            "baseline": runs[0]["scores"],
            "current": runs[-1]["scores"],
            "experiments": len(runs),
            "series": [r["scores"] for r in runs],  # oldest → newest, for the trend
        }
    except Exception:
        return None


_cache: tuple[float, dict[str, Any] | None] | None = None
_CACHE_TTL = 60.0


def _cached_live_fetch() -> dict[str, Any] | None:
    """``_fetch_live_scores`` with a short TTL so the page never hammers Phoenix."""
    global _cache
    now = time.time()
    if _cache is not None and now - _cache[0] < _CACHE_TTL:
        return _cache[1]
    scores = _fetch_live_scores()
    _cache = (now, scores)
    return scores


def accuracy_report(
    fetch: Callable[[], dict[str, Any] | None] = _cached_live_fetch,
) -> dict[str, Any]:
    """The Arize accuracy story + numbers for the web ``/accuracy`` page.

    Reads live Phoenix scores via *fetch* (injectable for tests); falls back to the
    last measured values when Phoenix is unavailable.
    """
    live = fetch()
    if live:
        baseline = {k: live["baseline"].get(_EVALUATOR_OF[k], 0.0) for k in _EVALUATOR_OF}
        current = {k: live["current"].get(_EVALUATOR_OF[k], 0.0) for k in _EVALUATOR_OF}
        source = "live"
        experiments = live["experiments"]
        series = live.get("series", [live["baseline"], live["current"]])
        # Each experiment's scores mapped to the metric keys → a trend the page plots.
        trend = [{k: s.get(_EVALUATOR_OF[k], 0.0) for k in _EVALUATOR_OF} for s in series]
    else:
        baseline, current = _BASELINE, _CURRENT
        source = "measured"
        experiments = None
        trend = [dict(_BASELINE), dict(_CURRENT)]  # baseline → current, two points

    return {
        "headline": {
            "calorie_accuracy": current["calorie"],
            "macro_accuracy": current["macro"],
            "within_tolerance": current["within_tolerance"],
        },
        "metrics": [
            {**m, "baseline": baseline[m["key"]], "current": current[m["key"]]}
            for m in _METRICS
        ],
        "loop": _LOOP,
        "dataset": {"cases": _case_count(), "source": "USDA FoodData Central (CC0)"},
        "phoenix_url": phoenix_dashboard_url(),
        "source": source,
        "experiments": experiments,
        "trend": trend,
    }
