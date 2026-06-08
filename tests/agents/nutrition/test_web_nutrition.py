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
from unittest.mock import Mock, patch

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


def test_retry_succeeds_on_second_attempt() -> None:
    """When the first lookup returns no text, the second attempt is used."""
    client = Mock()
    client.models.generate_content.side_effect = [
        SimpleNamespace(text=None),
        SimpleNamespace(text=json.dumps(_FIVE_GUYS)),
    ]
    food = web_nutrition("bacon cheeseburger", "Five Guys", client=client, attempts=2)

    assert food is not None
    assert client.models.generate_content.call_count == 2


def test_credential_failure_is_fail_soft_none() -> None:
    """A credentials exception during client init degrades to None."""
    with patch(
        "dietrace.agents.nutrition.web_nutrition._default_client",
        side_effect=RuntimeError("no credentials"),
    ):
        result = web_nutrition("burger", "McD")

    assert result is None


def test_negative_nutrient_value_is_dropped() -> None:
    """A negative nutrient from corrupted LLM output is skipped; core nutrients survive."""
    payload = dict(_FIVE_GUYS)
    payload["fiber_g"] = -3
    food = web_nutrition("bacon cheeseburger", "Five Guys", client=_client(json.dumps(payload)))

    assert food is not None
    assert food.nutrient("291") is None  # fiber dropped
    assert food.nutrient("208") is not None  # energy intact


def test_nan_nutrient_value_is_dropped() -> None:
    """A NaN nutrient (json.loads accepts the ``NaN`` literal) is skipped — energy survives.

    ``nan < 0`` is False, so the negative-value guard never catches it; only the
    ``math.isfinite`` check drops it before a NaN amount reaches the per-100 g panel
    and poisons every downstream macro total.
    """
    payload = dict(_FIVE_GUYS)
    payload["protein_g"] = float("nan")
    food = web_nutrition("bacon cheeseburger", "Five Guys", client=_client(json.dumps(payload)))

    assert food is not None
    assert food.nutrient("203") is None  # NaN protein dropped, not propagated
    assert food.nutrient("208") is not None  # energy intact


def test_non_finite_serving_grams_is_fail_soft_none() -> None:
    """An infinite serving weight degrades to None — the ``isfinite`` guard, not ``> 0``.

    ``inf > 0`` is True, so an infinite ``serving_grams`` would pass the positivity
    check and make every per-100 g amount divide to 0; only ``math.isfinite`` rejects
    it.
    """
    payload = dict(_FIVE_GUYS)
    payload["serving_grams"] = float("inf")
    assert web_nutrition("burger", "Five Guys", client=_client(json.dumps(payload))) is None


def test_missing_description_falls_back_to_brand_food_label() -> None:
    """When the LLM omits the description field, the label is built from brand + food."""
    payload = {k: v for k, v in _FIVE_GUYS.items() if k != "description"}
    food = web_nutrition("bacon cheeseburger", "Five Guys", client=_client(json.dumps(payload)))

    assert food is not None
    assert "Five Guys" in food.description or "bacon cheeseburger" in food.description
