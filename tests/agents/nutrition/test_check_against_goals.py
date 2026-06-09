"""Tests for check_against_goals — totals vs daily goals (3.4; ).

``check_against_goals(totals, goals)`` compares a meal's summed nutrient totals
(as produced by ``log_entry``) against the user's daily goals and returns a
supportive per-nutrient status — over / under / within — in the non-preachy
logging voice. The done criterion is the three messages, so the cases
below pin one nutrient comfortably over goal, one under, and one inside the
tolerance band, plus the supportive phrasing and fail-soft edges.
"""

import pytest

from dietrace.agents.nutrition.check_against_goals import (
    GoalCheck,
    NutrientGoal,
    check_against_goals,
)
from dietrace.nutrition.models import Nutrient

# USDA number codes: energy, protein, sodium.
_ENERGY, _PROTEIN, _SODIUM = "208", "203", "307"


def _totals() -> list[Nutrient]:
    """A meal's totals: sodium well over, protein well under, energy on goal."""
    return [
        Nutrient(code=_ENERGY, name="Energy", amount=2000.0, unit="kcal"),
        Nutrient(code=_PROTEIN, name="Protein", amount=70.0, unit="g"),
        Nutrient(code=_SODIUM, name="Sodium, Na", amount=3220.0, unit="mg"),
    ]


def _goals() -> list[NutrientGoal]:
    """Daily goals: energy met, protein short, sodium exceeded."""
    return [
        NutrientGoal(code=_ENERGY, name="Energy", target=2000.0, unit="kcal"),
        NutrientGoal(code=_PROTEIN, name="Protein", target=140.0, unit="g"),
        NutrientGoal(code=_SODIUM, name="Sodium, Na", target=2300.0, unit="mg"),
    ]


def _check() -> GoalCheck:
    return check_against_goals(_totals(), _goals())


def test_over_goal_status_and_message() -> None:
    """Sodium (3220 of 2300) is 40% over goal — flagged over, percent reported."""
    sodium = _check().status(_SODIUM)

    assert sodium.status == "over"
    assert sodium.pct_of_goal == pytest.approx(140.0)
    assert "40% over" in sodium.message
    assert "Sodium" in sodium.message


def test_under_goal_status_and_message() -> None:
    """Protein (70 of 140) is 50% under goal — flagged under, percent reported."""
    protein = _check().status(_PROTEIN)

    assert protein.status == "under"
    assert protein.pct_of_goal == pytest.approx(50.0)
    assert "50% under" in protein.message
    assert "Protein" in protein.message


def test_within_goal_status_and_message() -> None:
    """Energy (2000 of 2000) sits inside tolerance — flagged within, on track."""
    energy = _check().status(_ENERGY)

    assert energy.status == "within"
    assert energy.pct_of_goal == pytest.approx(100.0)
    assert "on track" in energy.message.lower()


def test_messages_are_supportive_not_preachy() -> None:
    """The voice stays encouraging — never scolding."""
    messages = [s.message.lower() for s in _check().statuses]

    assert messages  # one per goal
    forbidden = ("should not", "must not", "bad", "stop", "too much", "fail")
    assert not any(word in msg for msg in messages for word in forbidden)


def test_tolerance_band_counts_small_deviation_as_within() -> None:
    """A total a few percent off goal still reads as within the default band."""
    totals = [Nutrient(code=_ENERGY, name="Energy", amount=2080.0, unit="kcal")]
    goals = [NutrientGoal(code=_ENERGY, name="Energy", target=2000.0, unit="kcal")]

    assert check_against_goals(totals, goals).status(_ENERGY).status == "within"


def test_custom_tolerance_overrides_default() -> None:
    """A tighter per-goal tolerance flags a deviation the default would forgive."""
    totals = [Nutrient(code=_ENERGY, name="Energy", amount=2080.0, unit="kcal")]
    goals = [NutrientGoal(code=_ENERGY, name="Energy", target=2000.0, unit="kcal", tolerance=0.01)]

    assert check_against_goals(totals, goals).status(_ENERGY).status == "over"


def test_missing_total_counts_as_fully_under() -> None:
    """A goal with no matching total is treated as nothing consumed — under."""
    check = check_against_goals([], _goals())

    protein = check.status(_PROTEIN)
    assert protein.status == "under"
    assert protein.pct_of_goal == pytest.approx(0.0)


def test_totals_without_a_goal_are_ignored() -> None:
    """Only goals are reported; an extra total with no goal produces no status."""
    check = check_against_goals(_totals(), [_goals()[0]])

    assert [s.code for s in check.statuses] == [_ENERGY]
    assert check.status(_SODIUM) is None


# USDA code for added/total sugars (269) — a common zero-limit goal.
_SUGARS = "269"


def test_zero_target_goal_with_intake_reads_over_without_nonsense_percent() -> None:
    """A limit goal of 0 (e.g. added sugar) with any intake reads over, no negative %.

    Percent-of-goal is undefined against a zero target, so the supportive message
    must not surface a nonsensical figure like "-100% over".
    """
    totals = [Nutrient(code=_SUGARS, name="Added sugars", amount=12.0, unit="g")]
    goals = [NutrientGoal(code=_SUGARS, name="Added sugars", target=0.0, unit="g")]

    status = check_against_goals(totals, goals).status(_SUGARS)
    assert status.status == "over"
    assert "%" not in status.message  # no percent against a zero goal
    assert "-" not in status.message  # never "-100%"
    assert "12g" in status.message  # the consumed amount is still reported


def test_zero_target_goal_met_reads_within() -> None:
    """A zero limit goal with nothing consumed sits on track, not over."""
    totals = [Nutrient(code=_SUGARS, name="Added sugars", amount=0.0, unit="g")]
    goals = [NutrientGoal(code=_SUGARS, name="Added sugars", target=0.0, unit="g")]

    assert check_against_goals(totals, goals).status(_SUGARS).status == "within"


# ``check_against_goals`` is exposed as an ADK FunctionTool (agent.py), so the
# model calls it directly with its own ``totals``/``goals`` dicts. ``json.loads``
# and pydantic both admit the literals ``NaN``/``Infinity``, so a garbled
# tool-call argument can carry a non-finite amount or target. The percent maths
# then reach ``round(nan)`` / ``round(inf)`` — a ValueError / OverflowError
# straight out of the tool — and an infinite target reads as a nonsense
# "X of inf" band. These pin the same non-finite fail-soft contract already held
# in parse_meal / web_nutrition / estimate_portion / interpret_feedback.


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_total_degrades_to_under_without_crashing(bad: float) -> None:
    """A non-finite consumed amount reads as nothing-consumed, never raises."""
    totals = [Nutrient(code=_SODIUM, name="Sodium, Na", amount=bad, unit="mg")]
    goals = [NutrientGoal(code=_SODIUM, name="Sodium, Na", target=2300.0, unit="mg")]

    status = check_against_goals(totals, goals).status(_SODIUM)
    assert status.status == "under"
    assert status.consumed == 0.0
    assert status.pct_of_goal == pytest.approx(0.0)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_goal_target_is_skipped(bad: float) -> None:
    """A goal with a non-finite target cannot be scored — it is left unreported.

    Other, well-formed goals are still scored, mirroring how a total with no goal
    is simply ignored rather than crashing the step.
    """
    totals = _totals()
    goals = [
        NutrientGoal(code=_SODIUM, name="Sodium, Na", target=bad, unit="mg"),
        NutrientGoal(code=_PROTEIN, name="Protein", target=140.0, unit="g"),
    ]

    check = check_against_goals(totals, goals)
    assert check.status(_SODIUM) is None
    assert check.status(_PROTEIN).status == "under"


@pytest.mark.parametrize("bad", [float("nan"), float("-inf"), -0.10])
def test_unusable_tolerance_falls_back_to_default_band(bad: float) -> None:
    """A non-finite or negative per-goal tolerance degrades to the ±10% default.

    ``tolerance`` is model-supplied on this ADK FunctionTool just like ``target``,
    so a garbled value can be ``NaN``/``-inf`` or negative. Used directly, such a
    band silently mislabels an on-track nutrient: ``goal.tolerance * goal.target``
    is then ``NaN``/negative, so ``abs(consumed - target) <= band`` is always
    False and a meal sitting exactly on goal reads as "under" rather than "within"
   . The unusable band must fall back to the default so the
    verdict stays correct.
    """
    totals = [Nutrient(code=_ENERGY, name="Energy", amount=2000.0, unit="kcal")]
    goals = [NutrientGoal(code=_ENERGY, name="Energy", target=2000.0, unit="kcal", tolerance=bad)]

    assert check_against_goals(totals, goals).status(_ENERGY).status == "within"


def test_infinite_tolerance_does_not_swallow_a_real_over() -> None:
    """A ``+inf`` tolerance must not turn a clear over-goal into a false "within".

    An infinite band would make ``abs(consumed - target) <= band`` always True,
    masking every genuine over/under as on-track — the opposite failure to the
    NaN/negative case but the same unusable-tolerance class. It degrades to the
    default ±10%, so a meal well over goal still reads as "over".
    """
    totals = [Nutrient(code=_ENERGY, name="Energy", amount=3000.0, unit="kcal")]
    goals = [
        NutrientGoal(
            code=_ENERGY, name="Energy", target=2000.0, unit="kcal", tolerance=float("inf")
        )
    ]

    assert check_against_goals(totals, goals).status(_ENERGY).status == "over"


def test_negative_goal_target_is_skipped() -> None:
    """A negative goal target defines no meaningful band — it is left unreported.

    You cannot aim for less than zero of a nutrient, so a finite-but-negative
    target (a garbled tool-call argument, since ``check_against_goals`` is an ADK
    FunctionTool) is meaningless: scored, it yields a negative tolerance band and
    a nonsensical "-3320% over ... of -100mg" message. It is skipped like a
    non-finite target, while other well-formed goals are still scored.
    """
    totals = _totals()
    goals = [
        NutrientGoal(code=_SODIUM, name="Sodium, Na", target=-100.0, unit="mg"),
        NutrientGoal(code=_PROTEIN, name="Protein", target=140.0, unit="g"),
    ]

    check = check_against_goals(totals, goals)
    assert check.status(_SODIUM) is None
    assert check.status(_PROTEIN).status == "under"
