"""Phoenix first-class CODE annotation path in span_eval (review fix #1).

The verdict is set as span attributes (covered in test_span_eval) AND, best-effort,
logged as a Phoenix span annotation via the client API. This pins the annotation
call shape, the env/inject gating, and fail-soft behaviour.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from dietrace.evals import span_eval
from dietrace.evals.span_eval import annotate_macro_eval


def _tracer():
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(InMemorySpanExporter()))
    return provider.get_tracer("test")


def _macro_result(passed: bool = True) -> dict:
    return {"score": 1.0 if passed else 0.5, "pass": passed, "flags": [], "reasons": []}


def test_injected_client_gets_code_annotation() -> None:
    client = MagicMock()
    with _tracer().start_as_current_span("macro_plan"):
        annotate_macro_eval(_macro_result(), client=client)
    client.spans.add_span_annotation.assert_called_once()
    kwargs = client.spans.add_span_annotation.call_args.kwargs
    assert kwargs["annotator_kind"] == "CODE"
    assert kwargs["annotation_name"] == "macro_plan"
    assert kwargs["label"] == "pass"
    assert kwargs["score"] == 1.0
    assert kwargs["span_id"]  # a non-empty hex span id


def test_annotation_is_fail_soft_when_client_raises() -> None:
    client = MagicMock()
    client.spans.add_span_annotation.side_effect = RuntimeError("phoenix down")
    with _tracer().start_as_current_span("macro_plan"):
        annotate_macro_eval(_macro_result(), client=client)  # must not raise


def test_annotation_off_by_default(monkeypatch) -> None:
    built = MagicMock()
    monkeypatch.setattr(span_eval, "_phoenix_client", lambda: built)
    monkeypatch.delenv("DIETRACE_PHOENIX_ANNOTATIONS", raising=False)
    with _tracer().start_as_current_span("macro_plan"):
        annotate_macro_eval(_macro_result())  # client=None, flag unset
    built.spans.add_span_annotation.assert_not_called()


def test_annotation_enabled_by_env_flag(monkeypatch) -> None:
    built = MagicMock()
    monkeypatch.setattr(span_eval, "_phoenix_client", lambda: built)
    monkeypatch.setenv("DIETRACE_PHOENIX_ANNOTATIONS", "1")
    with _tracer().start_as_current_span("macro_plan"):
        annotate_macro_eval(_macro_result())
    built.spans.add_span_annotation.assert_called_once()


def test_no_op_without_recording_span(monkeypatch) -> None:
    client = MagicMock()
    monkeypatch.setenv("DIETRACE_PHOENIX_ANNOTATIONS", "1")
    assert not trace.get_current_span().is_recording()
    annotate_macro_eval(_macro_result(), client=client)  # no span → no call, no raise
    client.spans.add_span_annotation.assert_not_called()
