"""Tests for parse_meal — free text → structured items (3.5; ).

``parse_meal(text, client)`` is the only inherently generative step of the
nutrition pipeline: it asks the (mocked here) Gemini client to turn
free text like "two eggs, half an avocado, slice of toast" into a list of
``{food, quantity, unit}`` items the deterministic tools can act on. The done
criterion is two-fold — items parse out of a mocked JSON response, and
malformed model output is handled fail-soft (no raise) — so the cases below
pin the happy path, the JSON shapes the model may emit, and the bad-output
edges.

The Gemini client is always a ``Mock`` here; the no-network guard in
``conftest.py`` would block a real Vertex call.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

from dietrace.agents.nutrition.parse_meal import MealParse, ParsedItem, parse_meal


def _client(text: str | None) -> Mock:
    """A Gemini client mock whose ``generate_content`` returns *text*."""
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(text=text)
    return client


def _items_json(items: list[dict]) -> str:
    return json.dumps({"items": items})


def test_parses_items_from_mocked_response() -> None:
    """The headline case: three foods parse out of a mocked JSON response."""
    client = _client(
        _items_json(
            [
                {"food": "egg", "quantity": 2, "unit": "each"},
                {"food": "avocado", "quantity": 0.5, "unit": "whole"},
                {"food": "toast", "quantity": 1, "unit": "slice"},
            ]
        )
    )

    result = parse_meal("two eggs, half an avocado, slice of toast", client=client)

    assert isinstance(result, MealParse)
    assert [i.food for i in result.items] == ["egg", "avocado", "toast"]
    assert result.items[0] == ParsedItem(food="egg", quantity=2.0, unit="each")
    assert result.items[1].quantity == 0.5


def test_parses_bare_json_array() -> None:
    """A bare top-level array (no ``items`` wrapper) is accepted too."""
    client = _client(json.dumps([{"food": "banana", "quantity": 1, "unit": "each"}]))

    result = parse_meal("a banana", client=client)

    assert [i.food for i in result.items] == ["banana"]


def test_strips_markdown_code_fences() -> None:
    """A fenced ```json block is unwrapped before parsing."""
    payload = _items_json([{"food": "apple", "quantity": 1, "unit": "each"}])
    client = _client(f"```json\n{payload}\n```")

    result = parse_meal("an apple", client=client)

    assert [i.food for i in result.items] == ["apple"]


def test_defaults_quantity_and_unit_when_omitted() -> None:
    """An item with only a food name defaults to quantity 1 and an empty unit."""
    client = _client(_items_json([{"food": "oatmeal"}]))

    item = parse_meal("oatmeal", client=client).items[0]

    assert item.food == "oatmeal"
    assert item.quantity == 1.0
    assert item.unit == ""
    assert item.brand == ""


def test_captures_a_named_brand_separately_from_the_food() -> None:
    """A restaurant/brand qualifier is kept in ``brand``, not folded into ``food``."""
    client = _client(
        _items_json(
            [{"food": "bacon cheeseburger", "quantity": 1, "unit": "", "brand": "Five Guys"}]
        )
    )

    item = parse_meal("a Five Guys bacon cheeseburger", client=client).items[0]

    assert item.food == "bacon cheeseburger"
    assert item.brand == "Five Guys"


def test_malformed_output_fails_soft() -> None:
    """Non-JSON model output yields an empty parse, never an exception."""
    result = parse_meal("???", client=_client("Sorry, I can't do that."))

    assert isinstance(result, MealParse)
    assert result.items == []


def test_missing_response_text_fails_soft() -> None:
    """A response with no text (None) is handled fail-soft."""
    assert parse_meal("anything", client=_client(None)).items == []


def test_skips_malformed_items_keeps_valid_ones() -> None:
    """A bad item (no food / non-numeric quantity) is dropped; valid ones stay."""
    client = _client(
        _items_json(
            [
                {"food": "rice", "quantity": 1, "unit": "cup"},
                {"quantity": 2, "unit": "each"},  # no food → skip
                {"food": "milk", "quantity": "lots", "unit": "cup"},  # bad qty → skip
                {"food": "egg", "quantity": 3, "unit": "each"},
            ]
        )
    )

    result = parse_meal("rice and an egg", client=client)

    assert [i.food for i in result.items] == ["rice", "egg"]


def test_drops_non_positive_and_non_finite_quantities() -> None:
    """A non-finite (NaN/inf) or non-positive quantity is dropped fail-soft.

    Pydantic coerces these to valid floats, so without an explicit guard they
    would slip past the "non-numeric quantity → skip" contract and poison the
    deterministic math downstream — a NaN quantity silently propagates NaN into
    the meal totals, a negative one *subtracts* grams. A real portion is a
    positive, finite quantity, so every other shape is dropped like any other
    malformed item; the valid item alongside them survives.
    """
    client = _client(
        _items_json(
            [
                {"food": "nan-food", "quantity": float("nan"), "unit": "g"},
                {"food": "inf-food", "quantity": float("inf"), "unit": "g"},
                {"food": "neg-food", "quantity": -2, "unit": "each"},
                {"food": "zero-food", "quantity": 0, "unit": "each"},
                {"food": "egg", "quantity": 2, "unit": "each"},
            ]
        )
    )

    result = parse_meal("a poisoned meal", client=client)

    assert [i.food for i in result.items] == ["egg"]


def test_calls_client_with_model_and_text() -> None:
    """The free text is sent to the model named by config."""
    from dietrace.llm.config import GEMINI_MODEL

    client = _client(_items_json([]))

    parse_meal("two eggs", client=client)

    client.models.generate_content.assert_called_once()
    kwargs = client.models.generate_content.call_args.kwargs
    assert kwargs["model"] == GEMINI_MODEL
    assert "two eggs" in kwargs["contents"]
