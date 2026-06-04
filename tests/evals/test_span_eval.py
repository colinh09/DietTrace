"""Tests for eval-to-span annotation helpers and their integration.

Verifies that annotate_log_eval and annotate_macro_eval attach eval verdicts
to the active OTEL span using OpenInference eval attribute keys, and that both
are safe no-ops when no span is active (tracing disabled).

Also verifies the integration: evaluate_log and evaluate_macro_plan annotate
the current span automatically when one is active.
"""

from __future__ import annotations

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from dietrace.evals.online import evaluate_log
from dietrace.evals.span_eval import annotate_log_eval, annotate_macro_eval
from dietrace.macros.eval import evaluate_macro_plan
from dietrace.macros.models import MacroPlan, MacroProfile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tracer() -> tuple:
    """Return (tracer, exporter) using an in-process InMemorySpanExporter."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


def _log_result(confidence: float = 0.85, flags=None, reasons=None) -> dict:
    return {
        "confidence": confidence,
        "flags": flags or [],
        "reasons": reasons or [],
    }


def _macro_result(score: float = 1.0, passed: bool = True, flags=None, reasons=None) -> dict:
    return {
        "score": score,
        "pass": passed,
        "flags": flags or [],
        "reasons": reasons or [],
        "consistency": {"score": 1.0},
        "safety": {"score": 1.0},
    }


def _profile() -> MacroProfile:
    return MacroProfile(
        age=30, sex="male", height_cm=175.0, weight_kg=80.0,
        activity="moderate", goal="maintain",
    )


def _plan(kcal: float = 2000.0, protein: float = 150.0,
          carb: float = 200.8, fat: float = 66.7) -> MacroPlan:
    return MacroPlan(
        targets={"208": kcal, "203": protein, "205": carb, "204": fat},
        rationale="test",
        source="formula",
        steps=[],
        clamped=[],
    )


# ---------------------------------------------------------------------------
# annotate_log_eval — standalone helper
# ---------------------------------------------------------------------------


def test_annotate_log_eval_sets_score() -> None:
    tracer, exporter = _make_tracer()
    with tracer.start_as_current_span("meal-log"):
        annotate_log_eval(_log_result(confidence=0.85))
    attrs = dict(exporter.get_finished_spans()[0].attributes)
    assert "eval.meal_log.score" in attrs
    assert attrs["eval.meal_log.score"] == pytest.approx(0.85)


def test_annotate_log_eval_sets_label_pass() -> None:
    """Confidence >= 0.6 gets the 'pass' label."""
    tracer, exporter = _make_tracer()
    with tracer.start_as_current_span("meal-log"):
        annotate_log_eval(_log_result(confidence=0.75))
    attrs = dict(exporter.get_finished_spans()[0].attributes)
    assert "eval.meal_log.label" in attrs
    assert attrs["eval.meal_log.label"] == "pass"


def test_annotate_log_eval_sets_label_fail() -> None:
    """Confidence < 0.6 gets the 'fail' label."""
    tracer, exporter = _make_tracer()
    with tracer.start_as_current_span("meal-log"):
        annotate_log_eval(_log_result(confidence=0.4))
    attrs = dict(exporter.get_finished_spans()[0].attributes)
    assert attrs["eval.meal_log.label"] == "fail"


def test_annotate_log_eval_sets_explanation_with_reasons() -> None:
    tracer, exporter = _make_tracer()
    with tracer.start_as_current_span("meal-log"):
        annotate_log_eval(_log_result(
            confidence=0.4,
            flags=["dropped_items"],
            reasons=["1 of 2 foods dropped"],
        ))
    attrs = dict(exporter.get_finished_spans()[0].attributes)
    assert "eval.meal_log.explanation" in attrs
    assert "dropped" in attrs["eval.meal_log.explanation"].lower()


def test_annotate_log_eval_sets_explanation_when_no_reasons() -> None:
    """No reasons and no flags → explanation is the 'ok' sentinel."""
    tracer, exporter = _make_tracer()
    with tracer.start_as_current_span("meal-log"):
        annotate_log_eval(_log_result(confidence=0.85, flags=[], reasons=[]))
    attrs = dict(exporter.get_finished_spans()[0].attributes)
    assert "eval.meal_log.explanation" in attrs
    assert attrs["eval.meal_log.explanation"] == "ok"


def test_annotate_log_eval_explanation_uses_flags_when_reasons_empty() -> None:
    """No reasons but non-empty flags → explanation is built from the flags list."""
    tracer, exporter = _make_tracer()
    with tracer.start_as_current_span("meal-log"):
        annotate_log_eval(_log_result(confidence=0.4, flags=["dropped_items"], reasons=[]))
    attrs = dict(exporter.get_finished_spans()[0].attributes)
    assert attrs["eval.meal_log.explanation"] == "dropped_items"


def test_annotate_log_eval_no_op_when_no_active_span() -> None:
    """Safe no-op — must not raise when called outside any span context."""
    # Confirm we have no active recording span first.
    assert not trace.get_current_span().is_recording()
    annotate_log_eval(_log_result())  # must not raise


# ---------------------------------------------------------------------------
# annotate_macro_eval — standalone helper
# ---------------------------------------------------------------------------


def test_annotate_macro_eval_sets_score() -> None:
    tracer, exporter = _make_tracer()
    with tracer.start_as_current_span("macro-plan"):
        annotate_macro_eval(_macro_result(score=1.0, passed=True))
    attrs = dict(exporter.get_finished_spans()[0].attributes)
    assert "eval.macro_plan.score" in attrs
    assert attrs["eval.macro_plan.score"] == pytest.approx(1.0)


def test_annotate_macro_eval_sets_label_pass() -> None:
    tracer, exporter = _make_tracer()
    with tracer.start_as_current_span("macro-plan"):
        annotate_macro_eval(_macro_result(score=1.0, passed=True))
    attrs = dict(exporter.get_finished_spans()[0].attributes)
    assert attrs["eval.macro_plan.label"] == "pass"


def test_annotate_macro_eval_sets_label_fail() -> None:
    tracer, exporter = _make_tracer()
    with tracer.start_as_current_span("macro-plan"):
        annotate_macro_eval(_macro_result(score=0.5, passed=False, flags=["atwater_inconsistent"]))
    attrs = dict(exporter.get_finished_spans()[0].attributes)
    assert attrs["eval.macro_plan.label"] == "fail"


def test_annotate_macro_eval_sets_explanation_with_reasons() -> None:
    tracer, exporter = _make_tracer()
    with tracer.start_as_current_span("macro-plan"):
        annotate_macro_eval(_macro_result(
            score=0.5,
            passed=False,
            flags=["atwater_inconsistent"],
            reasons=["Atwater 2200 kcal vs target 2000 kcal"],
        ))
    attrs = dict(exporter.get_finished_spans()[0].attributes)
    assert "eval.macro_plan.explanation" in attrs
    assert "atwater" in attrs["eval.macro_plan.explanation"].lower() or \
           "2200" in attrs["eval.macro_plan.explanation"]


def test_annotate_macro_eval_explanation_uses_flags_when_reasons_empty() -> None:
    """No reasons but non-empty flags → explanation is built from the flags list."""
    tracer, exporter = _make_tracer()
    with tracer.start_as_current_span("macro-plan"):
        annotate_macro_eval(_macro_result(
            score=0.5,
            passed=False,
            flags=["atwater_inconsistent"],
            reasons=[],
        ))
    attrs = dict(exporter.get_finished_spans()[0].attributes)
    assert attrs["eval.macro_plan.explanation"] == "atwater_inconsistent"


def test_annotate_macro_eval_no_op_when_no_active_span() -> None:
    """Safe no-op — must not raise when called outside any span context."""
    assert not trace.get_current_span().is_recording()
    annotate_macro_eval(_macro_result())  # must not raise


# ---------------------------------------------------------------------------
# Integration — evaluate_log annotates the active span
# ---------------------------------------------------------------------------


def test_evaluate_log_annotates_span_when_active() -> None:
    """evaluate_log sets eval.meal_log.* on the current span when one is active."""
    tracer, exporter = _make_tracer()
    per_item = [{"fdc_id": 1, "description": "apple", "grams": 150, "nutrients": []}]
    totals = [
        {"code": "208", "name": "Energy", "amount": 88, "unit": "kcal"},
        {"code": "203", "name": "Protein", "amount": 0.4, "unit": "g"},
        {"code": "204", "name": "Total lipid", "amount": 0.2, "unit": "g"},
        {"code": "205", "name": "Carbohydrate", "amount": 21, "unit": "g"},
    ]
    with tracer.start_as_current_span("meal-log"):
        result = evaluate_log("an apple", per_item, totals)
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    attrs = dict(spans[0].attributes)
    assert "eval.meal_log.score" in attrs
    assert attrs["eval.meal_log.score"] == pytest.approx(result["confidence"])
    assert "eval.meal_log.label" in attrs
    assert "eval.meal_log.explanation" in attrs


def test_evaluate_log_no_op_without_active_span() -> None:
    """evaluate_log is safe when called outside any span context."""
    per_item = [{"fdc_id": 1, "description": "apple", "grams": 150, "nutrients": []}]
    totals = [{"code": "208", "amount": 88}]
    # Must not raise — just returns the result dict normally.
    result = evaluate_log("an apple", per_item, totals)
    assert "confidence" in result


# ---------------------------------------------------------------------------
# Integration — evaluate_macro_plan annotates the active span
# ---------------------------------------------------------------------------


def test_evaluate_macro_plan_annotates_span_when_active() -> None:
    """evaluate_macro_plan sets eval.macro_plan.* on the current span."""
    tracer, exporter = _make_tracer()
    profile = _profile()
    # Atwater-consistent plan inside physiological bounds.
    protein, fat = 150.0, 66.7
    carb = round((2000.0 - protein * 4.0 - fat * 9.0) / 4.0, 1)
    plan = _plan(kcal=2000.0, protein=protein, carb=carb, fat=fat)

    with tracer.start_as_current_span("macro-plan"):
        result = evaluate_macro_plan(profile, plan)

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    attrs = dict(spans[0].attributes)
    assert "eval.macro_plan.score" in attrs
    assert attrs["eval.macro_plan.score"] == pytest.approx(result["score"])
    assert "eval.macro_plan.label" in attrs
    assert attrs["eval.macro_plan.label"] == "pass"
    assert "eval.macro_plan.explanation" in attrs


def test_evaluate_macro_plan_no_op_without_active_span() -> None:
    """evaluate_macro_plan is safe when called outside any span context."""
    profile = _profile()
    protein, fat = 150.0, 66.7
    carb = round((2000.0 - protein * 4.0 - fat * 9.0) / 4.0, 1)
    plan = _plan(kcal=2000.0, protein=protein, carb=carb, fat=fat)
    result = evaluate_macro_plan(profile, plan)
    assert "score" in result
