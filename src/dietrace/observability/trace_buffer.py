"""In-process buffer of finished OTel spans, queryable by trace_id.

Powers the web "reasoning" panel — it renders the most recent agent
runs without a Phoenix round-trip. Spans are still exported to Phoenix when
configured; this buffer is a parallel, in-memory observer with a hard cap so a
long-running process can never grow unbounded. Least-recently-touched traces are
evicted once the cap is reached (LRU via OrderedDict).
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor

_MAX_TRACES = 100
_ATTR_VALUE_TRUNCATE = 500


class BufferingSpanProcessor(SpanProcessor):
    """SpanProcessor that retains finished spans in memory, keyed by trace_id."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._traces: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()

    def on_start(self, span: Any, parent_context: Any | None = None) -> None:
        return

    def on_end(self, span: ReadableSpan) -> None:
        trace_id = f"{span.get_span_context().trace_id:032x}"
        record = _span_to_dict(span)
        with self._lock:
            self._traces.setdefault(trace_id, []).append(record)
            self._traces.move_to_end(trace_id)
            while len(self._traces) > _MAX_TRACES:
                self._traces.popitem(last=False)

    def shutdown(self) -> None:
        return

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

    def get_trace(self, trace_id: str) -> list[dict[str, Any]]:
        """Return all captured spans for *trace_id* (empty list if unknown)."""
        with self._lock:
            return list(self._traces.get(trace_id, []))

    def trace_count(self) -> int:
        """Number of distinct traces currently buffered."""
        with self._lock:
            return len(self._traces)

    def clear(self) -> None:
        """Drop all buffered traces (test/reset helper)."""
        with self._lock:
            self._traces.clear()


def _span_to_dict(span: ReadableSpan) -> dict[str, Any]:
    """Serialize a finished span to a JSON-friendly dict for the web panel."""
    ctx = span.get_span_context()
    parent = span.parent
    start_ns = span.start_time or 0
    end_ns = span.end_time or 0
    duration_ms: float | None = None
    if end_ns and start_ns:
        duration_ms = (end_ns - start_ns) / 1_000_000

    status_name = "UNSET"
    if span.status is not None:
        status_name = span.status.status_code.name

    attrs: dict[str, str] = {}
    for key, value in (span.attributes or {}).items():
        text = str(value)
        if len(text) > _ATTR_VALUE_TRUNCATE:
            text = text[:_ATTR_VALUE_TRUNCATE] + "…"
        attrs[key] = text

    return {
        "name": span.name,
        "span_id": f"{ctx.span_id:016x}",
        "parent_id": f"{parent.span_id:016x}" if parent else None,
        "trace_id": f"{ctx.trace_id:032x}",
        "start_ns": start_ns,
        "end_ns": end_ns,
        "duration_ms": duration_ms,
        "status": status_name,
        "attributes": attrs,
    }


_buffer_singleton: BufferingSpanProcessor | None = None


def get_buffer() -> BufferingSpanProcessor:
    """Return the process-wide span buffer, creating it on first call."""
    global _buffer_singleton
    if _buffer_singleton is None:
        _buffer_singleton = BufferingSpanProcessor()
    return _buffer_singleton


def reset_buffer() -> None:
    """Drop the singleton (test/reset helper)."""
    global _buffer_singleton
    _buffer_singleton = None
