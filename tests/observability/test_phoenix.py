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
    register = MagicMock()
    monkeypatch.setattr("phoenix.otel.register", register)

    assert mod.init_tracer("dietrace") is None
    register.assert_not_called()


def test_raises_when_endpoint_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A key without a collector endpoint is a misconfiguration, not a no-op."""
    mod = _reload_phoenix(monkeypatch, {"PHOENIX_API_KEY": "fake-key"})
    with pytest.raises(RuntimeError, match="PHOENIX_COLLECTOR_ENDPOINT"):
        mod.init_tracer("dietrace")


def test_instrumentors_invoked_when_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the key set, register runs and all three instrumentors are wired."""
    mod = _reload_phoenix(
        monkeypatch,
        {
            "PHOENIX_API_KEY": "fake-key",
            "PHOENIX_COLLECTOR_ENDPOINT": "http://localhost:6006/v1/traces",
        },
    )

    provider = MagicMock()
    register = MagicMock(return_value=provider)
    adk = MagicMock()
    genai = MagicMock()
    mcp = MagicMock()
    monkeypatch.setattr("phoenix.otel.register", register)
    monkeypatch.setattr(
        "openinference.instrumentation.google_adk.GoogleADKInstrumentor", adk
    )
    monkeypatch.setattr(
        "openinference.instrumentation.google_genai.GoogleGenAIInstrumentor", genai
    )
    monkeypatch.setattr("openinference.instrumentation.mcp.MCPInstrumentor", mcp)

    result = mod.init_tracer("dietrace-svc")

    assert result is provider
    register.assert_called_once()
    assert register.call_args.kwargs["project_name"] == "dietrace-svc"
    for instrumentor in (adk, genai, mcp):
        instrumentor.return_value.instrument.assert_called_once_with(
            tracer_provider=provider
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

    provider = MagicMock()
    monkeypatch.setattr("phoenix.otel.register", MagicMock(return_value=provider))
    monkeypatch.setattr(
        "openinference.instrumentation.google_adk.GoogleADKInstrumentor", MagicMock()
    )
    monkeypatch.setattr(
        "openinference.instrumentation.google_genai.GoogleGenAIInstrumentor",
        MagicMock(),
    )
    monkeypatch.setattr("openinference.instrumentation.mcp.MCPInstrumentor", MagicMock())

    mod.init_tracer("dietrace-svc")

    provider.add_span_processor.assert_called_once_with(get_buffer())
