"""Macro planning value objects.

``MacroProfile`` captures the user inputs needed to derive personalised daily
targets. ``MacroPlan`` holds the resulting targets keyed by USDA nutrient number
(208 kcal / 203 protein / 204 fat / 205 carbohydrate — the same codes
``log_entry`` and ``check_against_goals`` use), plus the audit trail the guided
flow and observability layer read.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class MacroProfile(BaseModel):
    """User inputs for macro target derivation (transient — never persisted).

    Inputs are bounded to physically plausible ranges so a degenerate profile
    (negative age, zero height, negative weight) can never flow through
    ``compute_targets`` and yield negative or nonsensical targets. ``weight_kg``
    permits 0 only because the preset-evaluation path passes a sentinel profile
    with ``weight_kg=0`` to skip the protein g/kg axis; real submissions are
    always positive.
    """

    age: int = Field(gt=0, le=120)
    sex: Literal["male", "female"]
    height_cm: float = Field(gt=0, le=275)
    weight_kg: float = Field(ge=0, le=635)
    activity: Literal["sedentary", "light", "moderate", "active", "very_active"]
    goal: Literal["cut", "maintain", "bulk"]
    preference: str | None = None
    ai_help: bool = False


class MacroPlan(BaseModel):
    """Computed daily macro targets plus the reasoning trail.

    ``targets`` maps USDA nutrient codes to daily amounts (kcal or grams):
    - ``"208"`` → kcal (energy target)
    - ``"203"`` → protein grams
    - ``"205"`` → carbohydrate grams
    - ``"204"`` → fat grams

    ``steps`` is the ordered derivation trail: bmr → tdee → adjust → split,
    each a dict with a ``"step"`` key and the values used.

    ``clamped`` lists the axes where personalize_plan overrode the
    LLM suggestion to enforce physiological safety bounds.

    ``eval`` holds the result of ``evaluate_macro_plan`` once run;
    ``None`` until that layer runs.
    """

    targets: dict[str, float]
    rationale: str
    source: Literal["formula", "ai", "preset"]
    steps: list[dict[str, Any]]
    clamped: list[str]
    eval: dict[str, Any] | None = None
    # True when the split was biased toward the user's remembered preference
    # (the macro-learning closure) — surfaced so the UI/trace can show it learned.
    personalized: bool = False
    # The alignment of this plan to the user's saved split preference (Phase 2):
    # ``{score, protein_delta, fat_delta}``; None when there's no preference.
    adherence: dict[str, Any] | None = None
