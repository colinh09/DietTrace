"""Offline A/B runner for comparing two parse-prompt variants.

The hardened prompt (``parse_prompt.hardened.md``) is the current live prompt
saved for reference.  The soft variant (``parse_prompt.soft.md``) is a less
rule-heavy alternative — decent but more adaptable to informal user input.

``run_ab()`` scores both prompts on an eval dataset using an injected
``task_factory`` and evaluator so the runner is fully offline-testable.  The
``run_offline_demo()`` convenience function wires pre-baked mock outputs (no
Gemini call) to illustrate the scoring shape of a live run.

The LIVE prompt (``parse_prompt.md``) is unchanged; Colin decides which variant
to promote after reviewing the scores.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Canonical paths
# ---------------------------------------------------------------------------

_AGENTS_DIR = Path(__file__).parent.parent / "agents" / "nutrition"

HARDENED_PROMPT_PATH: Path = _AGENTS_DIR / "parse_prompt.hardened.md"
SOFT_PROMPT_PATH: Path = _AGENTS_DIR / "parse_prompt.soft.md"

_DATASET_DIR: Path = (
    Path(__file__).parent.parent.parent.parent / "evals" / "dataset" / "nutrition"
)

# Macro key → USDA nutrient code (matches evaluators._MACROS order).
_MACRO_CODES: list[tuple[str, str]] = [
    ("calories", "208"),
    ("protein_g", "203"),
    ("fat_g", "204"),
    ("carb_g", "205"),
]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class PromptScore:
    """Aggregate score for one prompt variant across all eval cases."""

    label: str
    mean_score: float
    scores: list[float] = field(default_factory=list)


@dataclass
class ABResult:
    """Scores for both prompt variants and their delta."""

    a: PromptScore
    b: PromptScore

    @property
    def delta(self) -> float:
        """B mean score minus A mean score (positive → B is better)."""
        return self.b.mean_score - self.a.mean_score

    def report(self) -> str:
        """Human-readable summary of both scores and the delta."""
        lines = [
            "Parse Prompt A/B Results",
            f"  {self.a.label}: {self.a.mean_score:.4f}",
            f"  {self.b.label}: {self.b.mean_score:.4f}",
            f"  delta ({self.b.label} - {self.a.label}): {self.delta:+.4f}",
        ]
        if self.delta > 0:
            lines.append(f"  winner: {self.b.label}")
        elif self.delta < 0:
            lines.append(f"  winner: {self.a.label}")
        else:
            lines.append("  winner: tie")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dataset loader
# ---------------------------------------------------------------------------


def load_eval_cases(dataset_dir: Path | None = None) -> list[dict[str, Any]]:
    """Load all nutrition eval cases from JSON files in *dataset_dir*."""
    d = dataset_dir or _DATASET_DIR
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))]


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------


def _score_prompt(
    prompt: str,
    label: str,
    cases: list[dict[str, Any]],
    task_factory: Callable[[str], Callable[[dict[str, Any]], dict[str, Any]]],
    evaluator: Callable[..., Any],
) -> PromptScore:
    task = task_factory(prompt)
    scores: list[float] = []
    for case in cases:
        output = task(case["input"])
        result = evaluator(output, case["expected"], case.get("metadata"))
        scores.append(float(result.score))
    mean = sum(scores) / len(scores) if scores else 0.0
    return PromptScore(label=label, mean_score=mean, scores=scores)


def run_ab(
    *,
    prompt_a: str,
    prompt_b: str,
    cases: list[dict[str, Any]],
    task_factory: Callable[[str], Callable[[dict[str, Any]], dict[str, Any]]],
    evaluator: Callable[..., Any] | None = None,
    label_a: str = "hardened",
    label_b: str = "soft",
) -> ABResult:
    """Score two parse-prompt variants on *cases* and return an :class:`ABResult`.

    *task_factory(prompt)* returns a callable that maps an input dict
    (e.g. ``{"text": "one large egg"}``) to a LoggedMeal-shaped output dict.
    In offline tests the factory returns a canned output; for a live run it
    wires the real agent with the supplied prompt text.

    *evaluator* defaults to :func:`~dietrace.evals.evaluators.macro_pct_error`.
    """
    from dietrace.evals.evaluators import macro_pct_error

    ev = evaluator if evaluator is not None else macro_pct_error
    score_a = _score_prompt(prompt_a, label_a, cases, task_factory, ev)
    score_b = _score_prompt(prompt_b, label_b, cases, task_factory, ev)
    return ABResult(a=score_a, b=score_b)


# ---------------------------------------------------------------------------
# Offline demo (pre-baked mock outputs — no Gemini call)
# ---------------------------------------------------------------------------


def _make_perfect_output(expected: dict[str, Any]) -> dict[str, Any]:
    """LoggedMeal output that exactly matches the 4 macro values in *expected*."""
    return {
        "totals": [
            {"code": code, "amount": float(expected.get(key, 0.0))}
            for key, code in _MACRO_CODES
        ]
    }


def _make_offset_output(expected: dict[str, Any], offset: float) -> dict[str, Any]:
    """LoggedMeal output with *offset* fractional error on each macro."""
    return {
        "totals": [
            {"code": code, "amount": float(expected.get(key, 0.0)) * (1.0 + offset)}
            for key, code in _MACRO_CODES
        ]
    }


def run_offline_demo(dataset_dir: Path | None = None) -> ABResult:
    """Offline (mocked) A/B: hardened → exact match outputs, soft → +10% offset.

    No Gemini call is made.  The hardened prompt is assigned outputs that exactly
    match ground truth (score ≈ 1.0); the soft prompt is assigned outputs with a
    +10% systematic error on every macro (score ≈ 0.90).  This illustrates the
    delta shape a live run would produce — the actual difference depends on how
    each prompt guides the model's parsing.
    """
    cases = load_eval_cases(dataset_dir)
    hardened_text = HARDENED_PROMPT_PATH.read_text(encoding="utf-8")
    soft_text = SOFT_PROMPT_PATH.read_text(encoding="utf-8")

    def task_factory(
        prompt: str,
    ) -> Callable[[dict[str, Any]], dict[str, Any]]:
        is_hardened = prompt == hardened_text

        def task(input_dict: dict[str, Any]) -> dict[str, Any]:
            text = (
                input_dict.get("text", "")
                if isinstance(input_dict, dict)
                else str(input_dict)
            )
            matching = next(
                (c for c in cases if c.get("input", {}).get("text") == text), None
            )
            expected = matching["expected"] if matching else {}
            if is_hardened:
                return _make_perfect_output(expected)
            return _make_offset_output(expected, offset=0.10)

        return task

    return run_ab(
        prompt_a=hardened_text,
        prompt_b=soft_text,
        cases=cases,
        task_factory=task_factory,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the offline demo and print the A/B report."""
    print("=== ILLUSTRATIVE MOCK — no Gemini call; not a measured eval ===")
    print("(The outputs are pre-baked to show the delta shape. Run a live A/B to")
    print(" compare the hardened vs soft prompt for real.)\n")
    result = run_offline_demo()
    print(result.report())


if __name__ == "__main__":
    main()
