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
