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
    from opentelemetry import trace as otel_trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    from dietrace.observability.trace_buffer import get_buffer

    # Build the OTLP/HTTP exporter explicitly. phoenix.otel.register() does not wire
    # the exporter reliably here — it returns a provider with no exporter attached, so
    # every span is silently dropped. A direct exporter to the /v1/traces path with a
    # Bearer token is what Phoenix Cloud actually accepts (the bare api_key header 401s;
    # verified against app.phoenix.arize.com). Phoenix routes spans to a project via the
    # openinference.project.name resource attribute.
    traces_endpoint = endpoint.rstrip("/")
    if not traces_endpoint.endswith("/v1/traces"):
        traces_endpoint += "/v1/traces"
    resource = Resource.create(
        {"openinference.project.name": service_name, "service.name": service_name}
    )
    tracer_provider = SDKTracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=traces_endpoint,
                headers={"authorization": f"Bearer {api_key}"},
            )
        )
    )
    # Mirror finished spans into the in-process buffer so the web "reasoning" panel
    # works in production, not only in tests — a parallel, capped, in-memory observer
    # (see trace_buffer.py) alongside the Phoenix export.
    tracer_provider.add_span_processor(get_buffer())
    otel_trace.set_tracer_provider(tracer_provider)

    GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)
    GoogleGenAIInstrumentor().instrument(tracer_provider=tracer_provider)
    MCPInstrumentor().instrument(tracer_provider=tracer_provider)

    return tracer_provider
