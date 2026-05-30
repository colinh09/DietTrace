"""Numeric, zero-LLM evaluators for the nutrition eval suite.

These hold the agent's macro/calorie accuracy to account against USDA ground
truth. Each returns an :class:`EvalResult` — the ``{score, label, explanation}``
shape ported from axon — extended with a ``metadata`` dict that carries the raw
error magnitudes so the supervisor reads true error while Phoenix charts the
normalized score (: "Normalize scores to [0,1] for Phoenix charts; carry
raw magnitudes in metadata").

``macro_pct_error`` is the first of these: it computes the
per-macro |%error| between the agent's logged totals and the case's expected
macros, normalizes the mean to a [0,1] accuracy score, and labels pass/fail
against the default ±15% band.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# USDA number codes for the scored macros; the agent's totals are
# keyed by code, never by name. Order is the per-macro report order.
_MACROS: tuple[tuple[str, str], ...] = (
    ("calories", "208"),
    ("protein_g", "203"),
    ("fat_g", "204"),
    ("carb_g", "205"),
)

# Default ±band a mean error may stay within and still label "pass".
_DEFAULT_TOLERANCE = 0.15


class EvalResult(BaseModel):
    """An evaluator's verdict, compatible with Phoenix experiment annotations.

    ``score`` is normalized to [0,1] (higher is better) for charting; ``label``
    is a categorical for grouping; ``explanation`` is one human-readable line;
    ``metadata`` carries the raw error magnitudes the supervisor reasons over.
    """

    score: float
    label: str
    explanation: str
    metadata: dict[str, Any] = {}

    def to_phoenix(self) -> dict[str, Any]:
        """Serialize to the dict shape Phoenix experiment annotations expect."""
        return {
            "score": self.score,
            "label": self.label,
            "explanation": self.explanation,
            "metadata": self.metadata,
        }


def _amount(item: Any, key: str) -> Any:
    """Read *key* from a dict-or-model item (agent output may be either)."""
    return item[key] if isinstance(item, dict) else getattr(item, key)


def _output_by_code(output: Any) -> dict[str, float]:
    """Map the agent output's totals to ``code -> amount`` (LoggedMeal shape)."""
    totals = _amount(output, "totals")
    return {str(_amount(n, "code")): float(_amount(n, "amount")) for n in totals}


def _expected_macros(expected: Any) -> dict[str, float]:
    """Coerce ``expected`` (ExpectedNutrition model or dict) to a macro mapping."""
    data = expected.model_dump() if hasattr(expected, "model_dump") else expected
    return {key: float(data[key]) for key, _code in _MACROS}


def _pct_error(actual: float, expected: float) -> float:
    """|%error| as a fraction; a zero ground truth is 0 if hit exactly, else 1."""
    if expected == 0.0:
        return 0.0 if actual == 0.0 else 1.0
    return abs(actual - expected) / abs(expected)


def macro_pct_error(
    output: Any,
    expected: Any,
    metadata: dict[str, Any] | None = None,  # accepted for a uniform evaluator API
) -> EvalResult:
    """Per-macro |%error| of the agent's totals vs. expected macros.

    Computes the absolute percent error for calories and protein/fat/carb,
    averages them, and returns the mean normalized to a [0,1] accuracy score
    (``1 - min(mean, 1)``). The per-macro and mean raw errors travel in
    ``metadata`` so the supervisor reads true magnitudes; the label passes when
    the mean stays within the default ±15% band.
    """
    by_code = _output_by_code(output)
    exp = _expected_macros(expected)

    per_macro = {
        key: _pct_error(by_code.get(code, 0.0), exp[key]) for key, code in _MACROS
    }
    mean_error = sum(per_macro.values()) / len(per_macro)
    score = 1.0 - min(mean_error, 1.0)
    label = "pass" if mean_error <= _DEFAULT_TOLERANCE else "fail"

    detail = ", ".join(f"{key} {err:.1%}" for key, err in per_macro.items())
    explanation = f"mean |%error| {mean_error:.1%} ({detail})"

    return EvalResult(
        score=score,
        label=label,
        explanation=explanation,
        metadata={"per_macro": per_macro, "mean_pct_error": mean_error},
    )
