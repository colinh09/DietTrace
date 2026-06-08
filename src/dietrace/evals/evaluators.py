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

import functools
import math
from collections.abc import Callable
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
    """|%error| as a fraction; a zero ground truth is 0 if hit exactly, else 1.

    A non-finite operand (a NaN/inf amount reaching an evaluator from a replayed
    or MCP-written output) yields the worst error (1.0), not a non-finite value:
    every evaluator normalizes with ``1 - min(err, 1)`` and ``min(nan, 1.0)`` is
    ``nan``, so an unguarded non-finite error would poison the [0,1] score 
    requires for Phoenix charts and regression flagging. An unusable output is a
    full miss, not a silent ``nan``.
    """
    if expected == 0.0:
        return 0.0 if actual == 0.0 else 1.0
    err = abs(actual - expected) / abs(expected)
    return err if math.isfinite(err) else 1.0


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
    the mean stays within the case's ±band (default ±15%, overridable per case
    via ``metadata["tolerance"]`` like the other evaluators — ).
    """
    by_code = _output_by_code(output)
    exp = _expected_macros(expected)

    per_macro = {
        key: _pct_error(by_code.get(code, 0.0), exp[key]) for key, code in _MACROS
    }
    mean_error = sum(per_macro.values()) / len(per_macro)
    score = 1.0 - min(mean_error, 1.0)
    label = "pass" if mean_error <= _tolerance(metadata) else "fail"

    detail = ", ".join(f"{key} {err:.1%}" for key, err in per_macro.items())
    explanation = f"mean |%error| {mean_error:.1%} ({detail})"

    return EvalResult(
        score=score,
        label=label,
        explanation=explanation,
        metadata={"per_macro": per_macro, "mean_pct_error": mean_error},
    )


def _per_macro_abs_errors(output: Any, expected: Any) -> dict[str, float]:
    """The absolute error |actual - expected| of each scored macro, native units."""
    by_code = _output_by_code(output)
    exp = _expected_macros(expected)
    return {key: abs(by_code.get(code, 0.0) - exp[key]) for key, code in _MACROS}


def macro_mae(
    output: Any,
    expected: Any,
    metadata: dict[str, Any] | None = None,  # accepted for a uniform evaluator API
) -> EvalResult:
    """Mean absolute error of the agent's macros vs. expected.

    The companion to ``macro_pct_error``: same macros (calories, protein, fat,
    carb), but the raw magnitude carried for the supervisor is the absolute error
    in native units (kcal/g), not a percentage — "off by 12 g protein" reads
    differently from "off by 30%". The ``mae`` (mean absolute error) and per-macro
    absolute errors travel in ``metadata``; the [0,1] score normalizes against the
    expected total (NMAE = Σ|error| / Σ|expected|) so it weights by magnitude
    rather than equal-weighting percentages, and an all-zero ground truth scores
    perfect only on an exact zero. The label passes when the NMAE stays within the
    case's ±band (default ±15%, overridable per case — ).
    """
    per_macro_abs = _per_macro_abs_errors(output, expected)
    exp = _expected_macros(expected)

    mae = sum(per_macro_abs.values()) / len(per_macro_abs)
    total_expected = sum(abs(v) for v in exp.values())
    if total_expected == 0.0:
        nmae = 0.0 if sum(per_macro_abs.values()) == 0.0 else 1.0
    else:
        nmae = sum(per_macro_abs.values()) / total_expected

    score = 1.0 - min(nmae, 1.0)
    label = "pass" if nmae <= _tolerance(metadata) else "fail"

    detail = ", ".join(f"{key} {err:g}" for key, err in per_macro_abs.items())
    explanation = f"MAE {mae:g} (NMAE {nmae:.1%}; {detail})"

    return EvalResult(
        score=score,
        label=label,
        explanation=explanation,
        metadata={"per_macro_abs": per_macro_abs, "mae": mae, "nmae": nmae},
    )


def _expected_value(expected: Any, key: str) -> Any:
    """Read *key* from an ExpectedNutrition model or a plain dict."""
    data = expected.model_dump() if hasattr(expected, "model_dump") else expected
    return data.get(key)


def _per_macro_errors(output: Any, expected: Any) -> dict[str, float]:
    """The |%error| of each scored macro (calories/protein/fat/carb)."""
    by_code = _output_by_code(output)
    exp = _expected_macros(expected)
    return {key: _pct_error(by_code.get(code, 0.0), exp[key]) for key, code in _MACROS}


def _tolerance(metadata: dict[str, Any] | None) -> float:
    """The per-case ±band, defaulting to ±15%."""
    return float((metadata or {}).get("tolerance", _DEFAULT_TOLERANCE))


def _not_applicable(explanation: str) -> EvalResult:
    """An evaluator that does not apply to this case (e.g. micros on a label tier).

    Follows axon's convention: a non-penalizing ``n/a`` label kept out of the
    accuracy aggregation by filtering on label, not score.
    """
    return EvalResult(score=1.0, label="n/a", explanation=explanation)


def calorie_accuracy(
    output: Any,
    expected: Any,
    metadata: dict[str, Any] | None = None,
) -> EvalResult:
    """Calorie closeness as a normalized [0,1] score.

    Calories (USDA code 208) are the headline number, so they get a dedicated
    evaluator: ``1 - min(|%error|, 1)`` for the Phoenix chart, raw error in
    ``metadata``, and a pass/fail label against the case's ±band.
    """
    actual = _output_by_code(output).get("208", 0.0)
    target = float(_expected_value(expected, "calories"))
    err = _pct_error(actual, target)
    tol = _tolerance(metadata)
    return EvalResult(
        score=1.0 - min(err, 1.0),
        label="pass" if err <= tol else "fail",
        explanation=f"calorie |%error| {err:.1%} ({actual:.0f} vs {target:.0f} kcal)",
        metadata={"calorie_pct_error": err, "actual": actual, "expected": target},
    )


def within_tolerance(
    output: Any,
    expected: Any,
    metadata: dict[str, Any] | None = None,
) -> EvalResult:
    """Pass iff every scored macro is within the ±band.

    A strict gate over calories/protein/fat/carb: ``score`` is 1.0 when all are
    inside the tolerance (default ±15%, overridable per case) and 0.0 otherwise,
    with the offending macros named in ``metadata`` and the explanation.
    """
    tol = _tolerance(metadata)
    per_macro = _per_macro_errors(output, expected)
    failing = {key: err for key, err in per_macro.items() if err > tol}
    if failing:
        joined = ", ".join(f"{key} {err:.1%}" for key, err in failing.items())
        explanation = f"over ±{tol:.0%}: {joined}"
    else:
        explanation = f"all macros within ±{tol:.0%}"
    return EvalResult(
        score=0.0 if failing else 1.0,
        label="fail" if failing else "pass",
        explanation=explanation,
        metadata={"tolerance": tol, "per_macro": per_macro, "failing": failing},
    )


def portion_error(
    output: Any,
    expected: Any,
    metadata: dict[str, Any] | None = None,
) -> EvalResult:
    """Portion-weight closeness vs ground-truth grams.

    A surface distinct from lookup error: it scores the total grams the agent
    estimated against the case's ground-truth ``grams``. Returns ``n/a`` when the
    case carries no ground-truth weight.
    """
    target = _expected_value(expected, "grams")
    if target is None:
        return _not_applicable("no ground-truth grams for this case")
    actual = sum(float(_amount(item, "grams")) for item in _amount(output, "per_item"))
    err = _pct_error(actual, float(target))
    tol = _tolerance(metadata)
    return EvalResult(
        score=1.0 - min(err, 1.0),
        label="pass" if err <= tol else "fail",
        explanation=f"portion |%error| {err:.1%} ({actual:.0f} vs {float(target):.0f} g)",
        metadata={
            "portion_pct_error": err,
            "actual_grams": actual,
            "expected_grams": float(target),
        },
    )


def micro_panel_accuracy(
    output: Any,
    expected: Any,
    metadata: dict[str, Any] | None = None,
) -> EvalResult:
    """Micronutrient accuracy, scored only on the ``full`` tier.

    Implements the two-tier dispatch: branded ``label`` cases (or any
    case without an expected micro panel) return ``n/a``; ``full`` whole-food
    cases score the mean |%error| across the expected micro codes, normalized to
    [0,1] with the raw per-micro errors in ``metadata``.
    """
    meta = metadata or {}
    micros = _expected_value(expected, "micros") or {}
    if meta.get("nutrient_tier") == "label" or not micros:
        return _not_applicable("micros not scored for label tier")
    by_code = _output_by_code(output)
    per_micro = {
        code: _pct_error(by_code.get(code, 0.0), float(amount))
        for code, amount in micros.items()
    }
    mean_error = sum(per_micro.values()) / len(per_micro)
    tol = _tolerance(metadata)
    return EvalResult(
        score=1.0 - min(mean_error, 1.0),
        label="pass" if mean_error <= tol else "fail",
        explanation=f"micro mean |%error| {mean_error:.1%} over {len(per_micro)} nutrients",
        metadata={"per_micro": per_micro, "mean_pct_error": mean_error},
    )


def _micro_accuracy_evaluator(
    name: str, code: str, unit: str
) -> Callable[..., EvalResult]:
    """Build a single-nutrient evaluator scoring one micro code.

    Fiber (291), sodium (307), and total sugars (269) each appear on nutrition
    labels, so — unlike the full ``micro_panel_accuracy`` — they are scored on
    both tiers, gating only on whether the case carries ground truth for the
    nutrient (``expected.micros[code]``). Scoring mirrors ``calorie_accuracy``:
    ``1 - min(|%error|, 1)`` for the Phoenix chart, the raw error in
    ``metadata``, and a pass/fail label against the case's ±band; absence of
    ground truth returns a non-penalizing ``n/a``.
    """

    def evaluator(
        output: Any,
        expected: Any,
        metadata: dict[str, Any] | None = None,
    ) -> EvalResult:
        target = (_expected_value(expected, "micros") or {}).get(code)
        if target is None:
            return _not_applicable(f"no ground-truth {name} for this case")
        actual = _output_by_code(output).get(code, 0.0)
        target = float(target)
        err = _pct_error(actual, target)
        tol = _tolerance(metadata)
        return EvalResult(
            score=1.0 - min(err, 1.0),
            label="pass" if err <= tol else "fail",
            explanation=(
                f"{name} |%error| {err:.1%} ({actual:.0f} vs {target:.0f} {unit})"
            ),
            metadata={
                f"{name}_pct_error": err,
                "code": code,
                "actual": actual,
                "expected": target,
            },
        )

    evaluator.__name__ = f"{name}_accuracy"
    evaluator.__qualname__ = f"{name}_accuracy"
    evaluator.__doc__ = (
        f"{name.replace('_', ' ').title()} (USDA code {code}) closeness as a "
        f"normalized [0,1] score; n/a without ground truth."
    )
    return evaluator


# Label-friendly single-nutrient evaluators: fiber (291),
# sodium (307), and total sugars (269), each scored against its micro-panel code.
fiber_accuracy = _micro_accuracy_evaluator("fiber", "291", "g")
sodium_accuracy = _micro_accuracy_evaluator("sodium", "307", "mg")
total_sugars_accuracy = _micro_accuracy_evaluator("total_sugars", "269", "g")


# ---------------------------------------------------------------------------
# Phoenix experiment adapters
# ---------------------------------------------------------------------------

# The numeric evaluators in Phoenix-run order. Phoenix binds the (output,
# expected, metadata) params to the task output, the example's ground-truth
# output, and the example metadata respectively.
_NUMERIC_EVALUATORS: list[Callable[..., EvalResult]] = [
    macro_pct_error,
    macro_mae,
    calorie_accuracy,
    within_tolerance,
    portion_error,
    micro_panel_accuracy,
    fiber_accuracy,
    sodium_accuracy,
    total_sugars_accuracy,
]


def _as_phoenix_evaluator(fn: Callable[..., EvalResult]) -> Callable[..., tuple]:
    """Adapt an EvalResult evaluator to Phoenix's ``(score, label, explanation)``.

    Phoenix accepts a tuple return and uses the function's name as the eval name;
    ``functools.wraps`` preserves the original name and signature so the
    ``output``/``expected``/``metadata`` params still bind correctly.
    """

    @functools.wraps(fn)
    def evaluator(output: Any, expected: Any, metadata: dict[str, Any] | None = None) -> tuple:
        result = fn(output, expected, metadata)
        return result.score, result.label, result.explanation

    return evaluator


# Drop-in evaluator list for client.experiments.run_experiment(evaluators=...).
PHOENIX_EVALUATORS: list[Callable[..., tuple]] = [
    _as_phoenix_evaluator(fn) for fn in _NUMERIC_EVALUATORS
]


# ---------------------------------------------------------------------------
# Macro-plan offline evaluators
# ---------------------------------------------------------------------------

# USDA codes for the macro targets the plan carries.
_PLAN_ENERGY = "208"
_PLAN_PROTEIN = "203"
_PLAN_FAT = "204"
_PLAN_CARB = "205"

# Standard Atwater factors — replicated here to avoid circular imports with
# macros/eval.py (which imports from evals/span_eval.py).
_AW_P = 4.0
_AW_C = 4.0
_AW_F = 9.0

# Fraction of kcal by which the Atwater estimate may drift before the plan
# is considered internally inconsistent (mirrors macros/eval.py).
_MACRO_ATWATER_TOL = 0.05


def _plan_targets(output: Any) -> dict[str, float]:
    """Extract ``targets`` mapping from a MacroPlan dict-or-model."""
    targets = output["targets"] if isinstance(output, dict) else output.targets
    return {str(k): float(v) for k, v in targets.items()}


def macro_plan_within_range(
    output: Any,
    expected: Any,
    metadata: dict[str, Any] | None = None,  # accepted for uniform API
) -> EvalResult:
    """Check whether a plan's computed targets fall within expected ranges.

    Scores the fraction of the four macro targets (kcal/protein/fat/carb) that
    land within the inclusive [min, max] bands defined in *expected*
    (``MacroExpectedTargets`` shape). A fully in-range plan scores 1.0 and
    labels ``"pass"``; a partially or fully out-of-range plan scores the
    fraction of in-range targets and labels ``"fail"``. The failing targets are
    named in ``metadata`` for the supervisor.
    """
    targets = _plan_targets(output)
    exp = expected if isinstance(expected, dict) else expected.model_dump()

    checks: dict[str, tuple[float, float, float]] = {
        "kcal":      (targets.get(_PLAN_ENERGY, 0.0),  exp["kcal_min"],      exp["kcal_max"]),
        "protein_g": (targets.get(_PLAN_PROTEIN, 0.0), exp["protein_g_min"], exp["protein_g_max"]),
        "fat_g":     (targets.get(_PLAN_FAT, 0.0),     exp["fat_g_min"],     exp["fat_g_max"]),
        "carb_g":    (targets.get(_PLAN_CARB, 0.0),    exp["carb_g_min"],    exp["carb_g_max"]),
    }

    passing = [key for key, (val, lo, hi) in checks.items() if lo <= val <= hi]
    failing = [key for key, (val, lo, hi) in checks.items() if not (lo <= val <= hi)]

    score = len(passing) / len(checks)
    label = "pass" if not failing else "fail"

    detail = ", ".join(
        f"{key} {checks[key][0]:.1f} not in [{checks[key][1]:.1f}, {checks[key][2]:.1f}]"
        for key in failing
    )
    explanation = (
        "all macro targets within expected ranges" if not failing else f"out of range: {detail}"
    )

    return EvalResult(
        score=score,
        label=label,
        explanation=explanation,
        metadata={"passing": passing, "failing": failing},
    )


def macro_plan_consistency_eval(
    output: Any,
    expected: Any = None,  # unused — present for uniform (output, expected, metadata) API
    metadata: dict[str, Any] | None = None,
) -> EvalResult:
    """Atwater consistency check for a macro plan.

    The Atwater identity 4·P + 4·C + 9·F should match the plan's kcal target
    within ±5% (the same tolerance ``compute_targets`` and ``personalize_plan``
    enforce). Drift beyond that means the plan's internal numbers disagree.
    Score is 1.0 when consistent, degraded when inconsistent, 0.0 at extreme
    drift. A plan with all-zero targets passes (consistent degenerate case).
    """
    targets = _plan_targets(output)
    kcal = targets.get(_PLAN_ENERGY, 0.0)
    protein = targets.get(_PLAN_PROTEIN, 0.0)
    fat = targets.get(_PLAN_FAT, 0.0)
    carb = targets.get(_PLAN_CARB, 0.0)

    atwater = _AW_P * protein + _AW_C * carb + _AW_F * fat

    if kcal == 0.0 and atwater == 0.0:
        return EvalResult(
            score=1.0,
            label="pass",
            explanation="all-zero plan: Atwater consistent",
        )

    if kcal == 0.0:
        return EvalResult(
            score=0.0,
            label="fail",
            explanation=f"atwater estimate {atwater:.0f} kcal but plan kcal target is 0",
            metadata={"atwater": atwater, "kcal": kcal},
        )

    rel_err = abs(atwater - kcal) / kcal
    if rel_err <= _MACRO_ATWATER_TOL:
        return EvalResult(
            score=1.0,
            label="pass",
            explanation=(
                f"atwater {atwater:.0f} kcal vs {kcal:.0f} kcal "
                f"({rel_err:.1%} drift — consistent)"
            ),
        )

    score = max(0.0, 1.0 - rel_err)
    return EvalResult(
        score=score,
        label="fail",
        explanation=(
            f"atwater inconsistent: {atwater:.0f} kcal vs {kcal:.0f} kcal "
            f"({rel_err:.0%} drift — threshold {_MACRO_ATWATER_TOL:.0%})"
        ),
        metadata={"atwater": atwater, "kcal": kcal, "rel_err": rel_err},
    )


_MACRO_NUMERIC_EVALUATORS: list[Callable[..., EvalResult]] = [
    macro_plan_within_range,
    macro_plan_consistency_eval,
]

# Drop-in evaluator list for the macro-plan Phoenix experiment.
MACRO_PHOENIX_EVALUATORS: list[Callable[..., tuple]] = [
    _as_phoenix_evaluator(fn) for fn in _MACRO_NUMERIC_EVALUATORS
]
