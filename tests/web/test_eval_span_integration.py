"""The live request path opens a recording span carrying the eval verdict (fix #1).

This is the regression test for the original blocker: /log and /macros/plan ran
their evaluators with no active span, so the verdict never reached a trace. Now
each handler wraps its work in a span, and the eval verdict rides it as
``eval.<name>.*`` attributes — what a judge sees in Phoenix.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import dietrace.web.app as appmod
from dietrace.web.app import create_app
from dietrace.web.feedback import FeedbackStore
from dietrace.web.goal_store import GoalStore
from dietrace.web.memory import SqliteMemory
from dietrace.web.store import MealLogStore
from dietrace.web.trust import TrustStore


def _app(tmp_path):
    return create_app(
        meal_logger=lambda text, examples=None: {"totals": [], "per_item": []},
        store=MealLogStore(tmp_path / "log.sqlite"),
        feedback_store=FeedbackStore(tmp_path / "feedback.sqlite"),
        trust_store=TrustStore(tmp_path / "trust.sqlite"),
        goal_store=GoalStore(tmp_path / "goals.sqlite"),
        memory=SqliteMemory(tmp_path / "memory.sqlite"),
        feedback_pusher=lambda *a: False,
        tracer_init=lambda name: None,
    )


def _install_recording_tracer(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(appmod, "_TRACER", provider.get_tracer("test"))
    return exporter


def test_macros_plan_opens_recording_span_with_eval(tmp_path, monkeypatch) -> None:
    exporter = _install_recording_tracer(monkeypatch)
    client = TestClient(_app(tmp_path))

    resp = client.post("/macros/plan", json={"preset": "maintain"})
    assert resp.status_code == 200

    spans = [s for s in exporter.get_finished_spans() if s.name == "macro_plan"]
    assert len(spans) == 1, "the /macros/plan handler must open a 'macro_plan' span"
    attrs = dict(spans[0].attributes)
    assert attrs.get("eval.macro_plan.label") in {"pass", "fail"}
    assert "eval.macro_plan.score" in attrs
    assert "eval.macro_plan.explanation" in attrs


def test_log_opens_recording_span_with_eval(tmp_path, monkeypatch) -> None:
    exporter = _install_recording_tracer(monkeypatch)
    client = TestClient(_app(tmp_path))

    resp = client.post("/log", json={"text": "two eggs and toast"})
    assert resp.status_code == 200

    spans = [s for s in exporter.get_finished_spans() if s.name == "meal_log"]
    assert len(spans) == 1, "the /log handler must open a 'meal_log' span"
    attrs = dict(spans[0].attributes)
    assert attrs.get("eval.meal_log.label") in {"pass", "fail"}
    assert "eval.meal_log.score" in attrs
