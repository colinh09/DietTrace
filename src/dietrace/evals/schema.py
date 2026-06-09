"""The EvalCase JSON contract for the nutrition eval suite.

Every dataset case under ``evals/dataset/nutrition/`` is an
``{input, expected, metadata}`` object, the shape ported from axon. ``input`` is
the free-text meal the agent logs; ``expected`` carries the USDA-grounded
ground-truth macros (and, for whole foods, the micro panel) the numeric
evaluators score against; ``metadata`` selects the **two-tier scoring** path via
``nutrient_tier`` — ``"full"`` (whole foods scored on the full micro panel) or
``"label"`` (branded foods scored on the label subset, micros ``n/a``).

This module is just the validated schema plus a file loader; the evaluators
 and the dataset loader/uploader (4.7/4.9) build on it.
Models are ``extra="forbid"`` so a mistyped field in a hand-authored case fails
loudly instead of being silently ignored.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# The two scoring tiers; micro evaluators return n/a for "label".
NutrientTier = Literal["full", "label"]

# Default fraction a result may deviate and still pass within_tolerance.
_DEFAULT_TOLERANCE = 0.15


class EvalInput(BaseModel):
    """What the agent is asked to log: a free-text meal description."""

    model_config = ConfigDict(extra="forbid")

    text: str


class ExpectedNutrition(BaseModel):
    """Ground-truth nutrition the numeric evaluators score against.

    The scored macros — ``calories`` (USDA code 208) and ``protein_g``/``fat_g``/
    ``carb_g`` (203/204/205) — are required. ``grams`` is the ground-truth
    portion weight for ``portion_error`` (a separate surface from lookup), and
    ``micros`` is the per-code panel scored only on the ``full`` tier; both are
    optional so branded label cases can omit them.

    Every value is finite: a NaN/inf ground truth is meaningless and silently
    distorts scoring (the evaluators treat non-finite error as a full miss, so a
    corrupt case scores every output maximally wrong without failing to load), so
    the schema rejects it loudly — the same guard ``CaseMetadata.tolerance`` uses
    below, in keeping with this module's ``extra="forbid"`` fail-loud contract.
    """

    model_config = ConfigDict(extra="forbid")

    calories: float = Field(allow_inf_nan=False)
    protein_g: float = Field(allow_inf_nan=False)
    fat_g: float = Field(allow_inf_nan=False)
    carb_g: float = Field(allow_inf_nan=False)
    grams: float | None = Field(default=None, allow_inf_nan=False)
    micros: dict[str, Annotated[float, Field(allow_inf_nan=False)]] = {}


class CaseMetadata(BaseModel):
    """Scoring metadata for a case.

    ``nutrient_tier`` is mandatory: it dispatches the two-tier scoring. ``fdc_id``
    pins the case to its USDA food so expected values are reproducible (and the
    supervisor can trace them); ``tolerance`` is the per-case ±band for
    ``within_tolerance`` (default ±15%); ``source`` and ``notes`` document where
    the ground truth came from.
    """

    model_config = ConfigDict(extra="forbid")

    nutrient_tier: NutrientTier
    fdc_id: int | None = None
    tolerance: float = Field(default=_DEFAULT_TOLERANCE, ge=0.0, allow_inf_nan=False)
    source: str | None = None
    notes: str | None = None


class EvalCase(BaseModel):
    """One nutrition eval case: ``{input, expected, metadata}``."""

    model_config = ConfigDict(extra="forbid")

    input: EvalInput
    expected: ExpectedNutrition
    metadata: CaseMetadata


def load_case(path: str | Path) -> EvalCase:
    """Read and validate a single eval case from a JSON file.

    Raises ``pydantic.ValidationError`` if the file does not match the schema, so
    a malformed hand-authored case fails the suite rather than scoring wrong.
    """
    text = Path(path).read_text()
    return EvalCase.model_validate(json.loads(text))
