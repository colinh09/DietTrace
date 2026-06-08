"""Tests for the corrector agent.

Mocked Gemini — no live calls. Covers parsing, fail-soft on every axis, the
token cap, and that emphasis/feedback reach the prompt.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

from dietrace.agents.nutrition.corrector import (
    ProposedBlock,
    propose_preference_block,
)


def _client(text: str) -> Mock:
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(text=text)
    return client


def _ok_json(block: str = "Preworkout meals: carbs run high; scale up.") -> str:
    return json.dumps(
        {
            "block_text": block,
            "rules": [
                {
                    "rule": "Preworkout carbs run high",
                    "rationale": "user corrected carbs up twice",
                    "from_feedback": [1, 2],
                }
            ],
        }
    )


_FEEDBACK = [
    {"id": 2, "feedback_text": "more carbs before workouts", "weight": 2.0,
     "meal_text": "preworkout oats"},
    {"id": 1, "feedback_text": "I run higher carbs preworkout", "weight": 1.0,
     "meal_text": None},
]


def test_parses_a_valid_proposal() -> None:
    result = propose_preference_block(_FEEDBACK, "", client=_client(_ok_json()))
    assert isinstance(result, ProposedBlock)
    assert "carbs run high" in result.block_text
    assert result.rules[0].from_feedback == [1, 2]
    assert result.rules[0].rationale


def test_empty_corrections_returns_none_without_calling() -> None:
    client = _client(_ok_json())
    assert propose_preference_block([], "", client=client) is None
    client.models.generate_content.assert_not_called()


def test_model_exception_is_fail_soft() -> None:
    client = Mock()
    client.models.generate_content.side_effect = RuntimeError("vertex down")
    assert propose_preference_block(_FEEDBACK, "", client=client) is None


def test_non_json_returns_none() -> None:
    assert propose_preference_block(_FEEDBACK, "", client=_client("not json")) is None


def test_wrong_shape_returns_none() -> None:
    bad = json.dumps({"rules": []})  # no block_text
    assert propose_preference_block(_FEEDBACK, "", client=_client(bad)) is None


def test_token_cap_truncates_an_overlong_block() -> None:
    long_block = " ".join(["word"] * 500)
    result = propose_preference_block(
        _FEEDBACK, "", token_cap=50, client=_client(_ok_json(long_block))
    )
    assert result is not None
    assert len(result.block_text.split()) <= 51  # 50 words + the "…" marker


def test_feedback_text_reaches_the_prompt() -> None:
    client = _client(_ok_json())
    propose_preference_block(_FEEDBACK, "current profile", client=client)
    contents = client.models.generate_content.call_args.kwargs["contents"]
    assert "more carbs before workouts" in contents
    # Emphasis was removed — all corrections are weighted equally now.
    assert "emphasis" not in contents.lower()
    assert "current profile" in contents


def test_parses_a_json_fenced_proposal() -> None:
    # Gemini commonly wraps structured JSON in a ```json … ``` code block; the
    # fence-stripper must peel it before json.loads or every such response is lost.
    fenced = "```json\n" + _ok_json() + "\n```"
    result = propose_preference_block(_FEEDBACK, "", client=_client(fenced))
    assert isinstance(result, ProposedBlock)
    assert "carbs run high" in result.block_text


def test_parses_a_plain_fenced_proposal() -> None:
    # A bare ``` … ``` fence (no language tag) must strip the same way.
    fenced = "```\n" + _ok_json() + "\n```"
    result = propose_preference_block(_FEEDBACK, "", client=_client(fenced))
    assert isinstance(result, ProposedBlock)
    assert "carbs run high" in result.block_text


def test_parses_a_leading_fence_without_a_trailing_fence() -> None:
    # A truncated response with an opening fence but no closing one must still
    # parse — exercises the "no trailing ```" arm of the stripper.
    fenced = "```json\n" + _ok_json()
    result = propose_preference_block(_FEEDBACK, "", client=_client(fenced))
    assert isinstance(result, ProposedBlock)
    assert "carbs run high" in result.block_text
