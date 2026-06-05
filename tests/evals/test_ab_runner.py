"""Tests for the parse-prompt A/B runner.

run_ab() scores two parse-prompt variants on an eval dataset using an
injected task_factory + evaluator.  All externals are mocked — no Gemini,
no Phoenix, no network.  The done criterion: an offline (mocked) run reports
both prompts' scores with a delta, the live parse_prompt.md is unchanged,
and parse_prompt.hardened.md is saved alongside it.
"""

from __future__ import annotations

from typing import Any

import pytest

from dietrace.evals.ab_runner import (
    HARDENED_PROMPT_PATH,
    SOFT_PROMPT_PATH,
    ABResult,
    PromptScore,
    run_ab,
    run_offline_demo,
)
from dietrace.evals.evaluators import EvalResult

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_MACROS: list[tuple[str, str]] = [
    ("calories", "208"),
    ("protein_g", "203"),
    ("fat_g", "204"),
    ("carb_g", "205"),
]

_EXPECTED: dict[str, float] = {
    "calories": 100.0,
    "protein_g": 10.0,
    "fat_g": 5.0,
    "carb_g": 8.0,
}


def _make_output(values: dict[str, float]) -> dict[str, Any]:
    return {
        "totals": [{"code": code, "amount": values.get(key, 0.0)} for key, code in _MACROS]
    }


_PERFECT_OUTPUT = _make_output(_EXPECTED)
_WORSE_OUTPUT = _make_output({k: v * 1.20 for k, v in _EXPECTED.items()})

_CASE: dict[str, Any] = {
    "input": {"text": "test meal"},
    "expected": _EXPECTED,
    "metadata": {"nutrient_tier": "full"},
}


def _fixed_factory(output: dict[str, Any]):
    """task_factory that always returns *output* regardless of prompt."""

    def factory(prompt: str):  # noqa: ARG001
        def task(input_dict: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
            return output

        return task

    return factory


def _varying_factory(output_a: dict[str, Any], output_b: dict[str, Any], prompt_a: str):
    """task_factory that returns output_a when called with prompt_a, else output_b."""

    def factory(prompt: str):
        chosen = output_a if prompt == prompt_a else output_b

        def task(input_dict: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
            return chosen

        return task

    return factory


# ---------------------------------------------------------------------------
# Core run_ab behaviour
# ---------------------------------------------------------------------------


def test_run_ab_returns_ab_result() -> None:
    """run_ab returns an ABResult containing PromptScores for both variants."""
    result = run_ab(
        prompt_a="A",
        prompt_b="B",
        cases=[_CASE],
        task_factory=_fixed_factory(_PERFECT_OUTPUT),
    )
    assert isinstance(result, ABResult)
    assert isinstance(result.a, PromptScore)
    assert isinstance(result.b, PromptScore)


def test_ab_delta_is_b_minus_a() -> None:
    """delta equals b.mean_score − a.mean_score."""
    factory = _varying_factory(_PERFECT_OUTPUT, _WORSE_OUTPUT, "PROMPT-A")
    result = run_ab(
        prompt_a="PROMPT-A",
        prompt_b="PROMPT-B",
        cases=[_CASE],
        task_factory=factory,
    )
    assert abs(result.delta - (result.b.mean_score - result.a.mean_score)) < 1e-9


def test_ab_labels_propagate() -> None:
    """label_a and label_b appear in the returned PromptScores."""
    result = run_ab(
        prompt_a="A",
        prompt_b="B",
        cases=[_CASE],
        task_factory=_fixed_factory(_PERFECT_OUTPUT),
        label_a="hardened",
        label_b="soft",
    )
    assert result.a.label == "hardened"
    assert result.b.label == "soft"


def test_ab_scores_per_case_list_length() -> None:
    """scores list has one entry per case."""
    case2 = {
        "input": {"text": "another meal"},
        "expected": {"calories": 200.0, "protein_g": 20.0, "fat_g": 10.0, "carb_g": 16.0},
        "metadata": {"nutrient_tier": "full"},
    }

    def always_half(output: Any, expected: Any, metadata: Any = None) -> EvalResult:
        return EvalResult(score=0.5, label="pass", explanation="fixed")

    result = run_ab(
        prompt_a="A",
        prompt_b="B",
        cases=[_CASE, case2],
        task_factory=_fixed_factory(_PERFECT_OUTPUT),
        evaluator=always_half,
    )
    assert len(result.a.scores) == 2
    assert len(result.b.scores) == 2
    assert result.a.mean_score == pytest.approx(0.5)


def test_task_factory_receives_prompt_string() -> None:
    """task_factory is called with the exact prompt strings passed to run_ab."""
    received: list[str] = []

    def recording_factory(prompt: str):
        received.append(prompt)

        def task(input_dict: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
            return _PERFECT_OUTPUT

        return task

    run_ab(
        prompt_a="PROMPT-A",
        prompt_b="PROMPT-B",
        cases=[_CASE],
        task_factory=recording_factory,
    )
    assert "PROMPT-A" in received
    assert "PROMPT-B" in received


# ---------------------------------------------------------------------------
# report()
# ---------------------------------------------------------------------------


def test_report_mentions_both_labels_and_delta() -> None:
    """ABResult.report() contains both labels and the word 'delta'."""
    result = run_ab(
        prompt_a="A",
        prompt_b="B",
        cases=[_CASE],
        task_factory=_fixed_factory(_PERFECT_OUTPUT),
        label_a="hardened",
        label_b="soft",
    )
    report = result.report()
    assert "hardened" in report
    assert "soft" in report
    assert "delta" in report.lower()


def test_report_names_winner_correctly() -> None:
    """report() names A as winner when A scores higher."""
    factory = _varying_factory(_PERFECT_OUTPUT, _WORSE_OUTPUT, "PROMPT-A")
    result = run_ab(
        prompt_a="PROMPT-A",
        prompt_b="PROMPT-B",
        cases=[_CASE],
        task_factory=factory,
        label_a="hardened",
        label_b="soft",
    )
    # A is perfect (1.0), B is worse — hardened should win
    assert result.a.mean_score > result.b.mean_score
    report = result.report()
    assert "hardened" in report


# ---------------------------------------------------------------------------
# Saved prompt files
# ---------------------------------------------------------------------------


def test_hardened_prompt_file_exists() -> None:
    """parse_prompt.hardened.md is saved alongside parse_prompt.md."""
    assert HARDENED_PROMPT_PATH.exists(), (
        f"Hardened prompt not found at {HARDENED_PROMPT_PATH}"
    )


def test_soft_prompt_file_exists() -> None:
    """parse_prompt.soft.md exists as the experimental soft variant."""
    assert SOFT_PROMPT_PATH.exists(), f"Soft prompt not found at {SOFT_PROMPT_PATH}"


def test_live_prompt_matches_hardened() -> None:
    """parse_prompt.md (the live prompt) matches parse_prompt.hardened.md exactly."""
    live_path = HARDENED_PROMPT_PATH.parent / "parse_prompt.md"
    live = live_path.read_text(encoding="utf-8")
    hardened = HARDENED_PROMPT_PATH.read_text(encoding="utf-8")
    assert live == hardened, (
        "parse_prompt.md differs from parse_prompt.hardened.md — "
        "the live prompt must not be swapped until Colin approves."
    )


def test_soft_prompt_differs_from_hardened() -> None:
    """The soft variant is a distinct prompt, not a copy of the hardened one."""
    hardened = HARDENED_PROMPT_PATH.read_text(encoding="utf-8")
    soft = SOFT_PROMPT_PATH.read_text(encoding="utf-8")
    assert hardened != soft, "Soft prompt must differ from the hardened prompt"


# ---------------------------------------------------------------------------
# Offline demo (integration-level, still no network)
# ---------------------------------------------------------------------------


def test_run_offline_demo_returns_ab_result() -> None:
    """run_offline_demo() returns an ABResult with non-zero scores for both variants."""
    result = run_offline_demo()
    assert isinstance(result, ABResult)
    assert 0.0 < result.a.mean_score <= 1.0
    assert 0.0 < result.b.mean_score <= 1.0


def test_run_offline_demo_hardened_scores_higher() -> None:
    """In the offline demo the hardened prompt scores strictly above the soft prompt."""
    result = run_offline_demo()
    assert result.a.mean_score > result.b.mean_score
