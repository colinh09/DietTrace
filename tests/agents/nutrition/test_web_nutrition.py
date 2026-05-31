"""The grounded web fallback: a branded item → a synthetic per-100 g Food.

``web_nutrition(food, brand, client)`` asks a (mocked here) Google-Search-grounded
Gemini for one serving's published macros + that serving's grams, then normalizes
them to the per-100 g panel the rest of the pipeline reads. The client is always a
``Mock``; the no-network guard would block a real Vertex call. The cases pin the
conversion math and the fail-soft edges (no text, bad JSON, missing serving).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

from dietrace.agents.nutrition.web_nutrition import web_nutrition

# Five Guys' published little bacon cheeseburger, one sandwich ≈ 250 g.
_FIVE_GUYS = {
    "description": "Five Guys bacon cheeseburger",
    "serving_grams": 250,
    "calories": 780,
    "protein_g": 39,
    "fat_g": 50,
    "carb_g": 39,
    "fiber_g": 2,
    "sodium_mg": 1180,
    "sugar_g": 8,
}


def _client(text: str | None) -> Mock:
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(text=text)
    return client


def test_builds_per_100g_food_from_a_serving_sized_label() -> None:
    food = web_nutrition(
        "bacon cheeseburger", "Five Guys", client=_client(json.dumps(_FIVE_GUYS))
    )

    assert food is not None
    assert food.data_type == "web_grounded"
    assert food.description == "Five Guys bacon cheeseburger"
    # 780 kcal in a 250 g serving → 312 kcal per 100 g.
    energy = food.nutrient("208")
    assert energy is not None and round(energy.amount, 1) == 312.0
    # 39 g protein / 250 g × 100 = 15.6 g per 100 g.
    protein = food.nutrient("203")
    assert protein is not None and round(protein.amount, 1) == 15.6
    # The serving weight is preserved so estimate_portion logs ~one burger.
    assert food.serving_sizes[0].gram_weight == 250.0


def test_optional_micros_carry_through_with_correct_units() -> None:
    food = web_nutrition("bacon cheeseburger", "Five Guys", client=_client(json.dumps(_FIVE_GUYS)))

    assert food is not None
    sodium = food.nutrient("307")
    assert sodium is not None and sodium.unit == "mg"
    # 1180 mg / 250 g × 100 = 472 mg per 100 g.
    assert round(sodium.amount, 0) == 472.0


def test_missing_serving_weight_is_fail_soft_none() -> None:
    # Without a serving weight nothing downstream can scale — degrade to None.
    payload = json.dumps({"description": "", "serving_grams": None, "calories": None})
    assert web_nutrition("mystery dish", "Nowhere", client=_client(payload)) is None


def test_empty_and_garbled_responses_degrade_to_none() -> None:
    assert web_nutrition("x", "y", client=_client(None)) is None
    assert web_nutrition("x", "y", client=_client("not json at all")) is None
