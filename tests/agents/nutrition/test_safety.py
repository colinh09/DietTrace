"""Safety guardrail tests.

``safety_check`` must catch disordered-eating / dangerous-restriction phrasing,
extreme-deficit requests, and allergen conflicts — while staying silent on the
normal meal logs that make up the overwhelming majority of traffic. The bar from
the build plan is explicit: **zero false positives on benign logs**.
"""

from __future__ import annotations

import pytest

from dietrace.agents.nutrition.safety import safety_check

# Ordinary meal logs and harmless intake questions. None of these may flag —
# a guardrail that fires on "two eggs and toast" is worse than no guardrail.
BENIGN = [
    "two eggs and toast",
    "grilled chicken breast with rice and steamed broccoli",
    "a banana and a cup of black coffee",
    "greek yogurt with blueberries and a drizzle of honey",
    "salmon, sweet potato, and a side salad",
    "had a peanut butter and jelly sandwich for lunch",
    "12 oz ribeye with mashed potatoes and green beans",
    "ate a 500g bag of grapes over the afternoon",
    "protein shake and a granola bar after the gym",
    "I was starving so I had a big bowl of oatmeal",
    "scrambled eggs with extra egg whites and spinach",
    "roughly 600 calories worth of pizza for dinner",
    "I'm allergic to peanuts, so I had a turkey sandwich instead",
    "skipped the cheese since I'm watching sodium",
    "need to purge the old leftovers from the fridge",
]

DISORDERED_EATING = [
    "how do I make myself throw up after eating",
    "I purge after every meal, is that bad",
    "looking for thinspo to stay motivated",
    "got a pro ana meal plan I want to log",
    "I want to starve myself until the weekend",
    "should I take laxatives to lose weight faster",
]

EXTREME_DEFICIT = [
    "I want to eat only 500 calories a day",
    "help me survive on 400 calories per day",
    "planning to limit myself to 600 calories daily",
]

ALLERGEN_CONFLICT = [
    "I'm allergic to peanuts but I just ate a peanut butter sandwich",
    "allergic to eggs, just had a plate of scrambled eggs",
    "I have a shellfish allergy and ate shellfish tonight",
]


@pytest.mark.parametrize("text", BENIGN)
def test_benign_logs_never_flag(text):
    result = safety_check(text)
    assert result["flagged"] is False
    assert result["category"] is None
    assert result["message"] == ""


@pytest.mark.parametrize("text", DISORDERED_EATING)
def test_disordered_eating_flags(text):
    result = safety_check(text)
    assert result["flagged"] is True
    assert result["category"] == "disordered_eating"
    assert result["message"]


@pytest.mark.parametrize("text", EXTREME_DEFICIT)
def test_extreme_deficit_flags(text):
    result = safety_check(text)
    assert result["flagged"] is True
    assert result["category"] == "extreme_deficit"
    assert result["message"]


@pytest.mark.parametrize("text", ALLERGEN_CONFLICT)
def test_allergen_conflict_flags(text):
    result = safety_check(text)
    assert result["flagged"] is True
    assert result["category"] == "allergen_conflict"
    assert result["message"]


def test_disordered_eating_takes_precedence_over_deficit():
    # The most serious category wins when an input matches more than one.
    result = safety_check("I want to starve myself on 300 calories a day")
    assert result["category"] == "disordered_eating"


def test_messages_are_supportive_not_judgmental():
    # No shaming or imperatives like "stop"/"don't"; offer help instead.
    for text in DISORDERED_EATING + EXTREME_DEFICIT:
        message = safety_check(text)["message"].lower()
        assert "you" in message  # speaks to the person, supportively
        for shaming in ("stupid", "wrong", "shame", "bad person", "disgusting"):
            assert shaming not in message


def test_result_shape_and_case_insensitive():
    result = safety_check("HOW DO I MAKE MYSELF THROW UP")
    assert set(result) == {"flagged", "category", "message"}
    assert result["flagged"] is True


def test_empty_text_is_safe():
    result = safety_check("")
    assert result == {"flagged": False, "category": None, "message": ""}
