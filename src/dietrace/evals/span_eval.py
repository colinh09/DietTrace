"""Attach eval verdicts to the active OpenTelemetry span.

annotate_log_eval and annotate_macro_eval write the results from
``evaluate_log`` / ``evaluate_macro_plan`` to the current active span as
OpenInference eval annotation attributes (``eval.<name>.score``,
``eval.<name>.label``, ``eval.<name>.explanation``), so every food log and
macro plan carries its verdict next to its span in Phoenix.

Fail-soft: when no recording span is active (tracing disabled or called
outside a span context), both functions are silent no-ops. Only the standard
``opentelemetry-api`` is required at call time — no Phoenix or OpenInference
imports.
"""

from __future__ import annotations

from typing import Any

from opentelemetry import trace

from dietrace.evals.online import REVIEW_THRESHOLD as _LOG_PASS_THRESHOLD


def _current_span():
    """Return the active span if it is recording, else None."""
    span = trace.get_current_span()
    return span if span.is_recording() else None


def annotate_log_eval(result: dict[str, Any]) -> None:
    """Write ``evaluate_log`` verdict attributes onto the current active span.

    Sets ``eval.meal_log.{score,label,explanation}`` so the verdict appears
    as an eval annotation alongside the meal-logging span in Phoenix. No-op
    when no recording span is active.
    """
    span = _current_span()
    if span is None:
        return

    confidence: float = result.get("confidence", 0.0)
    reasons: list[str] = result.get("reasons") or []
    flags: list[str] = result.get("flags") or []

    label = "pass" if confidence >= _LOG_PASS_THRESHOLD else "fail"
    explanation = "; ".join(reasons) if reasons else ("; ".join(flags) if flags else "ok")

    span.set_attribute("eval.meal_log.score", confidence)
    span.set_attribute("eval.meal_log.label", label)
    span.set_attribute("eval.meal_log.explanation", explanation)


def annotate_macro_eval(result: dict[str, Any]) -> None:
    """Write ``evaluate_macro_plan`` verdict attributes onto the current active span.

    Sets ``eval.macro_plan.{score,label,explanation}`` so the verdict appears
    as an eval annotation alongside the macro-planning span in Phoenix. No-op
    when no recording span is active.
    """
    span = _current_span()
    if span is None:
        return

    score: float = result.get("score", 0.0)
    passed: bool = result.get("pass", False)
    reasons: list[str] = result.get("reasons") or []
    flags: list[str] = result.get("flags") or []

    label = "pass" if passed else "fail"
    explanation = "; ".join(reasons) if reasons else ("; ".join(flags) if flags else "ok")

    span.set_attribute("eval.macro_plan.score", score)
    span.set_attribute("eval.macro_plan.label", label)
    span.set_attribute("eval.macro_plan.explanation", explanation)
