"""Unit tests for src/dietrace/observability/trace_buffer.py.

Spans are produced by a local in-process OpenTelemetry SDK TracerProvider — no
collector is contacted, so the conftest no-network guard stays satisfied. The
buffer is the data source for the web "reasoning" panel, so these tests
pin its add/get behavior, the capped LRU eviction, and the serialized span shape.
"""

from opentelemetry.sdk.trace import TracerProvider

from dietrace.observability.trace_buffer import (
    BufferingSpanProcessor,
    get_buffer,
    reset_buffer,
)


def _provider_with(buffer: BufferingSpanProcessor) -> TracerProvider:
    provider = TracerProvider()
    provider.add_span_processor(buffer)
    return provider


def test_add_and_get_returns_finished_span() -> None:
    """A finished span is retrievable by its trace_id; unknown ids return []."""
    buf = BufferingSpanProcessor()
    tracer = _provider_with(buf).get_tracer("test")

    with tracer.start_as_current_span("parse_meal") as span:
        trace_id = f"{span.get_span_context().trace_id:032x}"

    records = buf.get_trace(trace_id)
    assert len(records) == 1
    assert records[0]["name"] == "parse_meal"
    assert buf.get_trace("0" * 32) == []


def test_spans_grouped_by_trace_id() -> None:
    """Multiple spans in one trace accumulate under the same trace_id."""
    buf = BufferingSpanProcessor()
    tracer = _provider_with(buf).get_tracer("test")

    with tracer.start_as_current_span("root") as root:
        trace_id = f"{root.get_span_context().trace_id:032x}"
        with tracer.start_as_current_span("child"):
            pass

    records = buf.get_trace(trace_id)
    assert {r["name"] for r in records} == {"root", "child"}


def test_serialized_shape_and_parent_linkage() -> None:
    """Each record carries the documented keys; child points at its parent."""
    buf = BufferingSpanProcessor()
    tracer = _provider_with(buf).get_tracer("test")

    with tracer.start_as_current_span("root") as root:
        trace_id = f"{root.get_span_context().trace_id:032x}"
        root_span_id = f"{root.get_span_context().span_id:016x}"
        with tracer.start_as_current_span("child") as child:
            child.set_attribute("food", "egg")

    by_name = {r["name"]: r for r in buf.get_trace(trace_id)}
    expected_keys = {
        "name",
        "span_id",
        "parent_id",
        "trace_id",
        "start_ns",
        "end_ns",
        "duration_ms",
        "status",
        "attributes",
    }
    assert set(by_name["root"]) == expected_keys
    assert by_name["root"]["parent_id"] is None
    assert by_name["root"]["trace_id"] == trace_id
    assert by_name["child"]["parent_id"] == root_span_id
    assert by_name["child"]["attributes"]["food"] == "egg"
    assert by_name["root"]["duration_ms"] >= 0
    assert by_name["root"]["status"] == "UNSET"


def test_long_attribute_values_are_truncated() -> None:
    """Oversized attribute values are clipped so the buffer stays bounded."""
    buf = BufferingSpanProcessor()
    tracer = _provider_with(buf).get_tracer("test")

    with tracer.start_as_current_span("big") as span:
        trace_id = f"{span.get_span_context().trace_id:032x}"
        span.set_attribute("blob", "x" * 5000)

    value = buf.get_trace(trace_id)[0]["attributes"]["blob"]
    assert len(value) < 5000
    assert value.endswith("…")


def test_eviction_caps_at_max_and_drops_oldest() -> None:
    """Beyond the cap the least-recently-touched trace is evicted (LRU)."""
    buf = BufferingSpanProcessor()
    tracer = _provider_with(buf).get_tracer("test")

    trace_ids = []
    for i in range(150):
        with tracer.start_as_current_span(f"span-{i}") as span:
            trace_ids.append(f"{span.get_span_context().trace_id:032x}")

    assert buf.trace_count() == 100
    # The first 50 traces fell out; the last 100 remain.
    assert buf.get_trace(trace_ids[0]) == []
    assert buf.get_trace(trace_ids[49]) == []
    assert buf.get_trace(trace_ids[50]) != []
    assert buf.get_trace(trace_ids[-1]) != []


def test_clear_empties_the_buffer() -> None:
    buf = BufferingSpanProcessor()
    tracer = _provider_with(buf).get_tracer("test")
    with tracer.start_as_current_span("x"):
        pass

    assert buf.trace_count() == 1
    buf.clear()
    assert buf.trace_count() == 0


def test_get_buffer_is_a_singleton() -> None:
    """The process-wide accessor returns one shared instance until reset."""
    reset_buffer()
    first = get_buffer()
    assert get_buffer() is first
    reset_buffer()
    assert get_buffer() is not first
