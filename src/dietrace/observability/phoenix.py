"""Phoenix OpenTelemetry tracer bootstrap for DietTrace.

Wires the GoogleADK, GoogleGenAI, and MCP OpenInference instrumentors onto a
Phoenix-registered TracerProvider so the agent's reasoning is captured as spans.
Fail-soft: when ``PHOENIX_API_KEY`` is absent, initialization is a silent no-op
(see ) so the app and tests run with tracing disabled and zero spend.
"""

import os

from opentelemetry.trace import TracerProvider


def init_tracer(service_name: str) -> TracerProvider | None:
    """Initialize Phoenix OTEL tracing for ``service_name``.

    Returns the registered ``TracerProvider`` once the instrumentors are wired,
    or ``None`` when ``PHOENIX_API_KEY`` is absent (silent no-op).

    Raises ``RuntimeError`` if ``PHOENIX_API_KEY`` is set but
    ``PHOENIX_COLLECTOR_ENDPOINT`` is missing — that is a misconfiguration, not a
    reason to silently drop traces.
    """
    api_key = os.environ.get("PHOENIX_API_KEY", "")
    if not api_key:
        return None

    endpoint = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", "")
    if not endpoint:
        raise RuntimeError(
            "PHOENIX_COLLECTOR_ENDPOINT env var is required when PHOENIX_API_KEY is set."
        )

    from openinference.instrumentation.google_adk import GoogleADKInstrumentor
    from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor
    from openinference.instrumentation.mcp import MCPInstrumentor
    from phoenix.otel import register

    from dietrace.observability.trace_buffer import get_buffer

    # register() reads PHOENIX_API_KEY / PHOENIX_COLLECTOR_ENDPOINT from the env and
    # builds the auth headers itself; passing them explicitly mishandles the key.
    tracer_provider = register(
        project_name=service_name,
        auto_instrument=False,
        verbose=False,
    )

    GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)
    GoogleGenAIInstrumentor().instrument(tracer_provider=tracer_provider)
    MCPInstrumentor().instrument(tracer_provider=tracer_provider)

    # Mirror finished spans into the in-process buffer so the web "reasoning" panel
    # works in production, not only in tests. Spans still export to Phoenix; this is
    # a parallel, capped, in-memory observer (see trace_buffer.py).
    tracer_provider.add_span_processor(get_buffer())

    return tracer_provider
