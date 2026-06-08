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
    # Past-tense "threw up" does not match the present-tense `throw\s+up\s+after`
    # pattern — illness-related vomiting after the fact is not a guardrail trigger.
    "I threw up after the stomach flu, just logging what I managed to eat today",
    # allergen-free compound words (hyphenated and space-separated) must not
    # trigger a conflict — the allergen appears in a "X-free" product name,
    # not as an eaten ingredient.
    "I'm allergic to eggs and had egg-free pasta for dinner",
    "I have a gluten allergy so I always choose gluten-free bread",
    "I'm allergic to dairy and I have dairy-free milk in my coffee",
    "allergic to peanuts, bought some peanut-free candy at the store",
    "I'm allergic to eggs and had egg free pasta for dinner",
]

DISORDERED_EATING = [
    "how do I make myself throw up after eating",
    # Pins the `throw\s+up\s+after` pattern independently — the case above also
    # matches the earlier `make\s+myself` branch, so removing `throw\s+up\s+after`
    # from the pattern list would not break it. This case has no "make myself".
    "I throw up after every dinner to feel better",
    "I purge after every meal, is that bad",
    "looking for thinspo to stay motivated",
    "got a pro ana meal plan I want to log",
    "I want to starve myself until the weekend",
    "should I take laxatives to lose weight faster",
    # Pins patterns not exercised by the cases above (each one tests a distinct branch):
    "how do I force myself to vomit",            # force\s+myself\s+to\s+(throw\s+up|vomit)
    "vomiting after every meal to stay thin",    # vomit(ing)?\s+after
    "binge and purge routine for weight control", # binge\s+and\s+purge
    "pro-mia tips for beginners",                # pro[\s-]?mia\b
    "how to make myself sick after eating too much", # make\s+myself\s+sick (the "sick" branch)
    "I force myself to be sick after big meals", # force\s+myself\s+to\s+(be\s+sick)
]

BENIGN_FORCE_SICK = [
    # "be sick" without "force myself" is ordinary illness language — must not flag.
    "I feel sick when I overeat",
    "eating too much makes me feel sick",
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

# Allergy declared and the allergen named twice, but NOT eaten — no eating verb.
# An allergen conflict requires the person to actually log eating the allergen, so
# the eating-verb gate must keep these clear.
ALLERGEN_DECLARED_NOT_EATEN = [
    "I'm allergic to walnuts, and the walnuts from the backyard tree go to the squirrels.",
    "I'm allergic to shellfish, but the shellfish tank at the aquarium is my favorite exhibit.",
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


def test_high_calorie_per_day_does_not_flag():
    # Pattern matches ("1200 calories a day") but 1200 > ceiling (800) → no flag.
    # Exercises the int(match.group(1)) > _DEFICIT_CALORIE_CEILING fall-through branch.
    result = safety_check("I'm aiming for 1200 calories a day to lose weight gradually")
    assert result["flagged"] is False
    assert result["category"] is None


def test_exact_ceiling_calorie_per_day_flags():
    # 800 kcal/day is at the inclusive ceiling (≤ not <) and must flag.
    result = safety_check("I want to limit myself to 800 calories a day")
    assert result["flagged"] is True
    assert result["category"] == "extreme_deficit"


def test_one_above_ceiling_does_not_flag():
    # 801 kcal/day is just above the ceiling; the pattern matches but must not flag.
    result = safety_check("eating 801 calories per day")
    assert result["flagged"] is False


def test_safe_result_is_fresh_copy():
    # Mutating one safe result must not corrupt subsequent calls (dict(_SAFE) guard).
    r1 = safety_check("chicken and rice")
    r2 = safety_check("oatmeal with berries")
    r1["flagged"] = True  # deliberately corrupt the first result
    assert r2["flagged"] is False


@pytest.mark.parametrize("text", BENIGN_FORCE_SICK)
def test_be_sick_without_force_myself_does_not_flag(text):
    result = safety_check(text)
    assert result["flagged"] is False


@pytest.mark.parametrize("text", ALLERGEN_DECLARED_NOT_EATEN)
def test_allergen_named_but_not_eaten_does_not_flag(text):
    # Declaring an allergy and mentioning the allergen twice is not a conflict
    # unless the person logs eating it — the eating-verb gate must hold. Removing
    # `not _EATING_VERB.search(text)` from `_has_allergen_conflict` flags these.
    result = safety_check(text)
    assert result["flagged"] is False
    assert result["category"] is None
    assert result["message"] == ""
