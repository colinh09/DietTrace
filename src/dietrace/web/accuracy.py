"""The accuracy / Arize-observability report surfaced in the web app.

DietTrace's accuracy is held to account by Arize Phoenix: every logged meal is
traced, an eval suite scores estimates against USDA ground truth as Phoenix
experiments, and a supervisor agent reads those experiments back over the
Phoenix MCP server to open prompt-fix PRs when accuracy regresses. This surfaces
that loop — and the measured before/after numbers — at ``GET /accuracy`` so the
Arize integration is visible in the product, not just the repo.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Mean evaluator scores (0–1, higher is better) measured on the Phoenix eval
# dataset, baseline vs after the food-resolution fixes — see
# scripts/run_experiment.py and the two compared experiments.
_BASELINE = {"macro": 0.047, "calorie": 0.016, "within_tolerance": 0.0, "portion": 0.128}
_CURRENT = {"macro": 0.577, "calorie": 0.601, "within_tolerance": 0.375, "portion": 0.583}

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
    if directory.exists():
        return len(list(directory.glob("*.json")))
    return 0


def accuracy_report() -> dict[str, Any]:
    """The Arize accuracy story + measured numbers for the web ``/accuracy`` page."""
    return {
        "headline": {
            "calorie_accuracy": _CURRENT["calorie"],
            "macro_accuracy": _CURRENT["macro"],
            "within_tolerance": _CURRENT["within_tolerance"],
        },
        "metrics": [
            {**m, "baseline": _BASELINE[m["key"]], "current": _CURRENT[m["key"]]}
            for m in _METRICS
        ],
        "loop": _LOOP,
        "dataset": {"cases": _case_count(), "source": "USDA FoodData Central (CC0)"},
        "phoenix_url": phoenix_dashboard_url(),
    }
