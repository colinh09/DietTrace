"""Compare a meal's totals to daily goals in a supportive voice.

``check_against_goals(totals, goals)`` is the closing step of the nutrition tool
pipeline: given the summed nutrient totals from ``log_entry`` and the
user's daily :class:`NutrientGoal` targets, it reports a per-nutrient status —
``over``, ``under``, or ``within`` — plus a short, encouraging message in the
non-preachy logging voice.

A nutrient counts as ``within`` when its total sits inside a tolerance band
around the goal (default ±10%, overridable per goal); beyond the band it is
``over`` or ``under`` by the rounded percentage. Goals drive the report: a goal
with no matching total reads as nothing-consumed (fully under), and a total with
no goal is simply not reported, keeping the step fail-soft.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from dietrace.nutrition.models import Nutrient

# Default fraction a total may deviate from its goal and still read as on track.
_DEFAULT_TOLERANCE = 0.10

GoalLabel = Literal["over", "under", "within"]


class NutrientGoal(BaseModel):
    """A daily target for one nutrient, identified by its USDA number code.

    ``tolerance`` is the fraction of ``target`` a total may sit above or below
    and still count as ``within``; it defaults to ±10% and can be tightened or
    loosened per goal.
    """

    code: str
    name: str
    target: float
    unit: str
    tolerance: float = _DEFAULT_TOLERANCE


class GoalStatus(BaseModel):
    """How one nutrient's total compares to its goal.

    ``pct_of_goal`` is ``consumed / target × 100``; ``status`` is ``within`` when
    that sits inside the goal's tolerance band, else ``over`` or ``under``.
    ``message`` carries the supportive, non-preachy phrasing.
    """

    code: str
    name: str
    status: GoalLabel
    consumed: float
    target: float
    unit: str
    pct_of_goal: float
    message: str


class GoalCheck(BaseModel):
    """The result of :func:`check_against_goals`: one status per goal."""

    statuses: list[GoalStatus] = []

    def status(self, code: str) -> GoalStatus | None:
        """Return the status for *code* (USDA number), or None if not checked."""
        for entry in self.statuses:
            if entry.code == code:
                return entry
        return None


def _amount(totals: dict[str, Nutrient], code: str) -> float:
    """The consumed amount for *code*, or 0.0 when the meal has no such total."""
    nutrient = totals.get(code)
    return nutrient.amount if nutrient is not None else 0.0


def _message(name: str, label: GoalLabel, pct_off: int, consumed: float, goal: NutrientGoal) -> str:
    """Supportive phrasing for *label* in the non-preachy logging voice."""
    figures = f"{consumed:g}{goal.unit} of {goal.target:g}{goal.unit}"
    if label == "within":
        return f"{name} is on track with your goal ({figures})."
    if label == "over":
        # A zero-limit goal (e.g. 0 added sugar) has no meaningful percent-over —
        # report it without a nonsensical figure rather than "-100% over".
        if goal.target == 0:
            return f"{name} is over your zero goal ({figures}) — easy to balance over the day."
        return f"{name} is {pct_off}% over your goal ({figures}) — easy to balance over the day."
    return f"{name} is {pct_off}% under your goal ({figures}) — still room to get there."


def check_against_goals(totals: list[Nutrient], goals: list[NutrientGoal]) -> GoalCheck:
    """Compare meal *totals* to daily *goals*, status per goal.

    Each goal is scored from its matching total (0 when absent): ``within`` if
    the total lies inside the goal's tolerance band, otherwise ``over`` or
    ``under`` by the rounded percentage. Totals without a goal are ignored, so
    the report mirrors the goals the user set.
    """
    by_code = {nutrient.code: nutrient for nutrient in totals}

    statuses: list[GoalStatus] = []
    for goal in goals:
        consumed = _amount(by_code, goal.code)
        pct_of_goal = (consumed / goal.target * 100.0) if goal.target else 0.0

        if abs(consumed - goal.target) <= goal.tolerance * goal.target:
            label: GoalLabel = "within"
            pct_off = 0
        elif consumed > goal.target:
            label = "over"
            pct_off = round(pct_of_goal - 100.0)
        else:
            label = "under"
            pct_off = round(100.0 - pct_of_goal)

        statuses.append(
            GoalStatus(
                code=goal.code,
                name=goal.name,
                status=label,
                consumed=consumed,
                target=goal.target,
                unit=goal.unit,
                pct_of_goal=pct_of_goal,
                message=_message(goal.name, label, pct_off, consumed, goal),
            )
        )

    return GoalCheck(statuses=statuses)
