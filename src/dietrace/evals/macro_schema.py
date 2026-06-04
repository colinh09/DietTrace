"""Schema for macro-plan eval cases.

Every file under ``evals/dataset/macros/`` is a ``{input, expected, metadata}``
object whose ``input`` is a ``MacroProfile``-shaped dict, ``expected`` is a set
of acceptable target ranges per USDA code (the plan is scored against these
ranges by ``macro_plan_within_range``), and ``metadata`` documents the case.

Models are ``extra="forbid"`` so a mistyped field in a hand-authored case fails
loudly instead of being silently ignored.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict


class MacroEvalInput(BaseModel):
    """Profile fields that drive macro target computation (transient — never persisted)."""

    model_config = ConfigDict(extra="forbid")

    age: int
    sex: Literal["male", "female"]
    height_cm: float
    weight_kg: float
    activity: Literal["sedentary", "light", "moderate", "active", "very_active"]
    goal: Literal["cut", "maintain", "bulk"]
    preference: str | None = None
    ai_help: bool = False


class MacroExpectedTargets(BaseModel):
    """Acceptable target ranges for a macro plan computed from this profile.

    The ranges are inclusive: a plan passes ``macro_plan_within_range`` when
    every computed target falls within [min, max] for each macro.
    """

    model_config = ConfigDict(extra="forbid")

    kcal_min: float
    kcal_max: float
    protein_g_min: float
    protein_g_max: float
    fat_g_min: float
    fat_g_max: float
    carb_g_min: float
    carb_g_max: float


class MacroCaseMetadata(BaseModel):
    """Scoring metadata for a macro eval case."""

    model_config = ConfigDict(extra="forbid")

    source: str | None = None
    notes: str | None = None


class MacroEvalCase(BaseModel):
    """One macro eval case: ``{input, expected, metadata}``."""

    model_config = ConfigDict(extra="forbid")

    input: MacroEvalInput
    expected: MacroExpectedTargets
    metadata: MacroCaseMetadata


def load_macro_case(path: str | Path) -> MacroEvalCase:
    """Read and validate a single macro eval case from a JSON file.

    Raises ``pydantic.ValidationError`` if the file does not match the schema.
    """
    text = Path(path).read_text()
    return MacroEvalCase.model_validate(json.loads(text))
