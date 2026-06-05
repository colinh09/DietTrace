"""Tests for interpret_feedback — free-form feedback → StructuredFeedback (14.11).

``interpret_feedback(meal_context, feedback_text, client)`` mirrors parse_meal: it
asks the (mocked here) Gemini client to convert a user's free-form comment about
a meal into a structured action. ``apply_feedback(meal_items, feedback)`` then
applies that action deterministically to the list of meal items.

The Gemini client is always a ``Mock`` here; the no-network guard in
``conftest.py`` would block a real Vertex call.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dietrace.agents.nutrition.interpret_feedback import (
    StructuredFeedback,
    apply_feedback,
    interpret_feedback,
)


def _client(text: str | None) -> Mock:
    """A Gemini client mock whose ``generate_content`` returns *text*."""
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(text=text)
    return client


def _fb_json(**kwargs) -> str:
    """Render a StructuredFeedback dict as JSON text."""
    return json.dumps(kwargs)


_MEAL = {
    "items": [
        {"food": "fries", "grams": 300.0},
        {"food": "burger", "grams": 200.0},
    ],
    "meal_type": "lunch",
}


# ---------------------------------------------------------------------------
# interpret_feedback — each kind
# ---------------------------------------------------------------------------


def test_portion_adjust_fries() -> None:
    """'the fries are double what I'd eat' → portion_adjust fries ×0.5."""
    payload = _fb_json(
        kind="portion_adjust",
        target_food="fries",
        adjustment=0.5,
        scope="this_food",
        rationale="User eats half the fries they were served.",
    )
    result = interpret_feedback(_MEAL, "the fries are double what I'd eat", client=_client(payload))

    assert isinstance(result, StructuredFeedback)
    assert result.kind == "portion_adjust"
    assert result.target_food == "fries"
    assert result.adjustment == pytest.approx(0.5)
    assert result.scope == "this_food"


def test_standing_rule_meal_type() -> None:
    """'from now on this is my preworkout, aim for 80g carbs' → standing_rule meal_type."""
    payload = _fb_json(
        kind="standing_rule",
        target_food="",
        adjustment=80.0,
        scope="meal_type",
        rationale="User wants 80g carbs for preworkout meals.",
    )
    result = interpret_feedback(
        _MEAL,
        "from now on this is my preworkout, aim for 80g carbs",
        client=_client(payload),
    )

    assert isinstance(result, StructuredFeedback)
    assert result.kind == "standing_rule"
    assert result.scope == "meal_type"
    assert result.adjustment == pytest.approx(80.0)


def test_remove_item() -> None:
    """'I actually didn't eat the salad' → remove_item salad."""
    payload = _fb_json(
        kind="remove_item",
        target_food="salad",
        adjustment=None,
        scope="this_meal",
        rationale="User did not eat the salad.",
    )
    result = interpret_feedback(_MEAL, "I actually didn't eat the salad", client=_client(payload))

    assert isinstance(result, StructuredFeedback)
    assert result.kind == "remove_item"
    assert result.target_food == "salad"
    assert result.adjustment is None


def test_add_item() -> None:
    """'I also had a protein bar, about 50g' → add_item protein_bar 50g."""
    payload = _fb_json(
        kind="add_item",
        target_food="protein bar",
        adjustment=50.0,
        scope="this_meal",
        rationale="User ate an additional protein bar.",
    )
    result = interpret_feedback(
        _MEAL, "I also had a protein bar, about 50g", client=_client(payload)
    )

    assert isinstance(result, StructuredFeedback)
    assert result.kind == "add_item"
    assert result.target_food == "protein bar"
    assert result.adjustment == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# interpret_feedback — fail-soft
# ---------------------------------------------------------------------------


def test_none_text_fails_soft() -> None:
    """A response with no text (None) returns None, never raises."""
    result = interpret_feedback(_MEAL, "anything", client=_client(None))
    assert result is None


def test_malformed_json_fails_soft() -> None:
    """Non-JSON model output returns None, never raises."""
    result = interpret_feedback(_MEAL, "anything", client=_client("Sorry, can't do that."))
    assert result is None


def test_model_exception_fails_soft() -> None:
    """An exception from the model call returns None, never raises."""
    client = Mock()
    client.models.generate_content.side_effect = RuntimeError("network error")
    result = interpret_feedback(_MEAL, "anything", client=client)
    assert result is None


def test_invalid_schema_fails_soft() -> None:
    """Valid JSON but wrong shape returns None fail-soft."""
    result = interpret_feedback(
        _MEAL, "anything", client=_client(json.dumps({"wrong": "shape"}))
    )
    assert result is None


def test_calls_model_with_feedback_text_and_meal() -> None:
    """The feedback text and meal context are sent to the model."""
    payload = _fb_json(
        kind="portion_adjust",
        target_food="fries",
        adjustment=0.5,
        scope="this_food",
        rationale="half portion",
    )
    client = _client(payload)

    interpret_feedback(_MEAL, "the fries are too much", client=client)

    client.models.generate_content.assert_called_once()
    contents = client.models.generate_content.call_args.kwargs["contents"]
    assert "fries" in contents
    assert "the fries are too much" in contents


# ---------------------------------------------------------------------------
# apply_feedback — deterministic application
# ---------------------------------------------------------------------------

_ITEMS = [
    {"food": "fries", "grams": 300.0},
    {"food": "burger", "grams": 200.0},
]


def test_apply_portion_adjust_scales_grams() -> None:
    """portion_adjust multiplies the matched food's grams by adjustment."""
    fb = StructuredFeedback(
        kind="portion_adjust",
        target_food="fries",
        adjustment=0.5,
        scope="this_food",
        rationale="half portion",
    )
    result = apply_feedback(_ITEMS, fb)

    assert result[0]["food"] == "fries"
    assert result[0]["grams"] == pytest.approx(150.0)
    assert result[1]["grams"] == pytest.approx(200.0)  # burger unchanged


def test_apply_portion_adjust_case_insensitive() -> None:
    """Food matching for portion_adjust is case-insensitive."""
    fb = StructuredFeedback(
        kind="portion_adjust",
        target_food="Fries",
        adjustment=0.5,
        scope="this_food",
        rationale="",
    )
    result = apply_feedback(_ITEMS, fb)
    assert result[0]["grams"] == pytest.approx(150.0)


def test_apply_portion_adjust_no_match_unchanged() -> None:
    """A portion_adjust with no matching food returns items unchanged (fail-soft)."""
    fb = StructuredFeedback(
        kind="portion_adjust",
        target_food="salad",
        adjustment=0.5,
        scope="this_food",
        rationale="",
    )
    result = apply_feedback(_ITEMS, fb)
    assert result[0]["grams"] == pytest.approx(300.0)
    assert result[1]["grams"] == pytest.approx(200.0)


def test_apply_remove_item() -> None:
    """remove_item drops the matched food from the list."""
    fb = StructuredFeedback(
        kind="remove_item",
        target_food="fries",
        adjustment=None,
        scope="this_meal",
        rationale="didn't eat them",
    )
    result = apply_feedback(_ITEMS, fb)

    assert len(result) == 1
    assert result[0]["food"] == "burger"


def test_apply_remove_item_no_match_unchanged() -> None:
    """remove_item with no matching food returns items unchanged."""
    fb = StructuredFeedback(
        kind="remove_item",
        target_food="salad",
        adjustment=None,
        scope="this_meal",
        rationale="",
    )
    result = apply_feedback(_ITEMS, fb)
    assert len(result) == 2


def test_apply_add_item() -> None:
    """add_item appends a new food with the given grams."""
    fb = StructuredFeedback(
        kind="add_item",
        target_food="protein bar",
        adjustment=50.0,
        scope="this_meal",
        rationale="ate it after",
    )
    result = apply_feedback(_ITEMS, fb)

    assert len(result) == 3
    added = result[-1]
    assert added["food"] == "protein bar"
    assert added["grams"] == pytest.approx(50.0)


def test_apply_add_item_no_adjustment_uses_zero() -> None:
    """add_item with None adjustment adds a food with 0 grams (fail-soft)."""
    fb = StructuredFeedback(
        kind="add_item",
        target_food="mystery food",
        adjustment=None,
        scope="this_meal",
        rationale="",
    )
    result = apply_feedback(_ITEMS, fb)
    assert len(result) == 3
    assert result[-1]["grams"] == pytest.approx(0.0)


def test_apply_standing_rule_no_meal_change() -> None:
    """standing_rule does not modify meal items (rule is for future meals)."""
    fb = StructuredFeedback(
        kind="standing_rule",
        target_food="",
        adjustment=80.0,
        scope="meal_type",
        rationale="preworkout target",
    )
    result = apply_feedback(_ITEMS, fb)

    assert len(result) == 2
    assert result[0]["grams"] == pytest.approx(300.0)


def test_apply_none_feedback_no_change() -> None:
    """None feedback (failed interpretation) returns items unchanged."""
    result = apply_feedback(_ITEMS, None)
    assert result == _ITEMS


def test_apply_unknown_kind_no_change() -> None:
    """An unrecognised kind returns items unchanged (fail-soft)."""
    fb = StructuredFeedback(
        kind="unknown_kind",
        target_food="",
        adjustment=None,
        scope="this_meal",
        rationale="",
    )
    result = apply_feedback(_ITEMS, fb)
    assert result == _ITEMS
