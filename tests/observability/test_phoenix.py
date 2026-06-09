"""Unit tests for src/dietrace/observability/phoenix.py.

The OpenInference instrumentors and phoenix.otel.register are mocked — no real
Phoenix collector is contacted (the conftest no-network guard would block it).
"""

import importlib
import sys
from unittest.mock import MagicMock

import pytest


def _reload_phoenix(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> object:
    """Re-import the module with a clean Phoenix env, returning the module."""
    for key in ("PHOENIX_API_KEY", "PHOENIX_COLLECTOR_ENDPOINT"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    sys.modules.pop("dietrace.observability.phoenix", None)
    return importlib.import_module("dietrace.observability.phoenix")


def test_no_op_when_api_key_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without PHOENIX_API_KEY, init is a silent no-op returning None."""
    mod = _reload_phoenix(monkeypatch, {})
    assert mod.init_tracer("dietrace") is None


def test_raises_when_endpoint_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A key without a collector endpoint is a misconfiguration, not a no-op."""
    mod = _reload_phoenix(monkeypatch, {"PHOENIX_API_KEY": "fake-key"})
    with pytest.raises(RuntimeError, match="PHOENIX_COLLECTOR_ENDPOINT"):
        mod.init_tracer("dietrace")


def _patch_otel(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    """Mock the OTEL SDK pieces init_tracer builds, returning the mocks for asserting."""
    provider = MagicMock()
    mocks = {
        "provider": provider,
        "TracerProvider": MagicMock(return_value=provider),
        "OTLPSpanExporter": MagicMock(),
        "BatchSpanProcessor": MagicMock(),
        "set_tracer_provider": MagicMock(),
        "adk": MagicMock(),
        "genai": MagicMock(),
        "mcp": MagicMock(),
    }
    monkeypatch.setattr("opentelemetry.sdk.trace.TracerProvider", mocks["TracerProvider"])
    monkeypatch.setattr(
        "opentelemetry.sdk.trace.export.BatchSpanProcessor", mocks["BatchSpanProcessor"]
    )
    monkeypatch.setattr(
        "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter",
        mocks["OTLPSpanExporter"],
    )
    monkeypatch.setattr(
        "opentelemetry.trace.set_tracer_provider", mocks["set_tracer_provider"]
    )
    monkeypatch.setattr(
        "openinference.instrumentation.google_adk.GoogleADKInstrumentor", mocks["adk"]
    )
    monkeypatch.setattr(
        "openinference.instrumentation.google_genai.GoogleGenAIInstrumentor", mocks["genai"]
    )
    monkeypatch.setattr("openinference.instrumentation.mcp.MCPInstrumentor", mocks["mcp"])
    return mocks


def test_exporter_targets_traces_path_with_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the key set, init builds an OTLP exporter to the /v1/traces path with a
    Bearer token, registers it globally, and wires all three instrumentors. (The bare
    api_key header 401s against Phoenix Cloud; the path + Bearer is what authenticates.)"""
    mod = _reload_phoenix(
        monkeypatch,
        {
            "PHOENIX_API_KEY": "fake-key",
            "PHOENIX_COLLECTOR_ENDPOINT": "https://app.phoenix.example/s/space",
        },
    )
    m = _patch_otel(monkeypatch)

    result = mod.init_tracer("dietrace-svc")

    assert result is m["provider"]
    kw = m["OTLPSpanExporter"].call_args.kwargs
    assert kw["endpoint"] == "https://app.phoenix.example/s/space/v1/traces"
    assert kw["headers"] == {"authorization": "Bearer fake-key"}
    m["set_tracer_provider"].assert_called_once_with(m["provider"])
    for instrumentor in (m["adk"], m["genai"], m["mcp"]):
        instrumentor.return_value.instrument.assert_called_once_with(
            tracer_provider=m["provider"]
        )


def test_in_process_buffer_attached_when_key_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """init_tracer wires the in-process span buffer onto the registered provider,
    so the web /reasoning panel sees spans in production — not only in tests
    (the spans still export to Phoenix; this is a parallel in-memory observer)."""
    from dietrace.observability.trace_buffer import get_buffer

    mod = _reload_phoenix(
        monkeypatch,
        {
            "PHOENIX_API_KEY": "fake-key",
            "PHOENIX_COLLECTOR_ENDPOINT": "http://localhost:6006/v1/traces",
        },
    )
    m = _patch_otel(monkeypatch)

    mod.init_tracer("dietrace-svc")

    added = [c.args[0] for c in m["provider"].add_span_processor.call_args_list]
    assert get_buffer() in added  # buffer attached alongside the OTLP batch processor
    assert len(added) == 2


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        # Bare collector endpoint: the /v1/traces path is appended (Phoenix Cloud
        # rejects spans posted to the space root).
        ("https://app.phoenix.example/s/space", "https://app.phoenix.example/s/space/v1/traces"),
        # Already-suffixed endpoint: left intact, NOT doubled to /v1/traces/v1/traces
        # (a doubled path 404s and silently drops every span — the idempotency guard).
        ("http://localhost:6006/v1/traces", "http://localhost:6006/v1/traces"),
        # A trailing slash is normalized before the suffix decision, both ways.
        ("https://app.phoenix.example/s/space/", "https://app.phoenix.example/s/space/v1/traces"),
        ("http://localhost:6006/v1/traces/", "http://localhost:6006/v1/traces"),
    ],
)
def test_traces_endpoint_normalized_idempotently(
    monkeypatch: pytest.MonkeyPatch, configured: str, expected: str
) -> None:
    """The OTLP exporter always targets a single /v1/traces path regardless of how
    PHOENIX_COLLECTOR_ENDPOINT is written — appended when absent, left intact when
    already present, with any trailing slash normalized first. Pins phoenix.py's
    idempotency guard so a regression that blindly re-appends the path (producing
    a span-dropping /v1/traces/v1/traces) is caught."""
    mod = _reload_phoenix(
        monkeypatch,
        {"PHOENIX_API_KEY": "fake-key", "PHOENIX_COLLECTOR_ENDPOINT": configured},
    )
    m = _patch_otel(monkeypatch)

    mod.init_tracer("dietrace-svc")

    assert m["OTLPSpanExporter"].call_args.kwargs["endpoint"] == expected
