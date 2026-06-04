"""Attach eval verdicts to the active span — and, optionally, to Phoenix as a
first-class CODE annotation.

``annotate_log_eval`` / ``annotate_macro_eval`` take the result of ``evaluate_log``
/ ``evaluate_macro_plan`` and surface the verdict on the current trace two ways,
both fail-soft:

1. **Span attributes** — ``eval.<name>.{score,label,explanation}`` are set on the
   active recording span, so the verdict rides the live trace and is visible in
   the span's attribute panel in Phoenix. Always on when a span is recording.

2. **Phoenix span annotation** — a first-class ``add_span_annotation`` call
   (``annotator_kind="CODE"``) so the verdict can render as an eval/annotation on
   the trace. Best-effort and OFF by default (it talks to Phoenix): enabled by
   ``DIETRACE_PHOENIX_ANNOTATIONS=1``, or by injecting a client (tests). Any error
   — missing creds, span-export timing, network — is swallowed.

When no recording span is active (tracing disabled, or called outside a span),
both are silent no-ops. Only ``opentelemetry-api`` is needed at import time; the
Phoenix client is a lazy import behind the flag.
"""

from __future__ import annotations

import os
from typing import Any

from opentelemetry import trace

from dietrace.evals.online import REVIEW_THRESHOLD as _LOG_PASS_THRESHOLD


def _current_span() -> Any | None:
    """Return the active span if it is recording, else None."""
    span = trace.get_current_span()
    return span if span.is_recording() else None


def _explanation(reasons: list[str], flags: list[str]) -> str:
    """A short human verdict string: reasons, else flags, else 'ok'."""
    if reasons:
        return "; ".join(reasons)
    if flags:
        return "; ".join(flags)
    return "ok"


def annotate_log_eval(result: dict[str, Any], client: Any | None = None) -> None:
    """Surface an ``evaluate_log`` verdict on the current span as ``eval.meal_log.*``."""
    confidence: float = result.get("confidence", 0.0)
    label = "pass" if confidence >= _LOG_PASS_THRESHOLD else "fail"
    explanation = _explanation(result.get("reasons") or [], result.get("flags") or [])
    _annotate("meal_log", confidence, label, explanation, client)


def annotate_macro_eval(result: dict[str, Any], client: Any | None = None) -> None:
    """Surface an ``evaluate_macro_plan`` verdict on the current span as ``eval.macro_plan.*``."""
    score: float = result.get("score", 0.0)
    label = "pass" if result.get("pass", False) else "fail"
    explanation = _explanation(result.get("reasons") or [], result.get("flags") or [])
    _annotate("macro_plan", score, label, explanation, client)


def _annotate(
    name: str, score: float, label: str, explanation: str, client: Any | None
) -> None:
    span = _current_span()
    if span is None:
        return
    # 1) Always-on: the verdict rides the live span as attributes.
    span.set_attribute(f"eval.{name}.score", score)
    span.set_attribute(f"eval.{name}.label", label)
    span.set_attribute(f"eval.{name}.explanation", explanation)
    # 2) Best-effort: a first-class Phoenix CODE annotation.
    _phoenix_annotation(span, name, score, label, explanation, client)


def _phoenix_annotation(
    span: Any, name: str, score: float, label: str, explanation: str, client: Any | None
) -> None:
    """Best-effort first-class Phoenix annotation keyed by span id (fail-soft).

    Off unless a *client* is injected (tests) or ``DIETRACE_PHOENIX_ANNOTATIONS=1``
    — so production never adds a Phoenix round-trip per request unless asked. Any
    failure (no creds, span not yet exported, network) is swallowed.
    """
    try:
        if client is None:
            if os.environ.get("DIETRACE_PHOENIX_ANNOTATIONS") != "1":
                return
            client = _phoenix_client()
            if client is None:
                return
        span_id = format(span.get_span_context().span_id, "016x")
        client.spans.add_span_annotation(
            span_id=span_id,
            annotation_name=name,
            label=label,
            score=score,
            explanation=explanation,
            annotator_kind="CODE",
        )
    except Exception:
        return


def _phoenix_client() -> Any | None:
    """Lazily build a Phoenix client (reads creds from the env), or None on failure."""
    try:
        from phoenix.client import Client

        return Client()
    except Exception:
        return None
