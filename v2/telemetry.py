"""
v2 Python-side OpenTelemetry setup.

Provides a TracerProvider + OTLP HTTP exporter that sends spans to the same
collector the Claude Code subprocess uses (http://127.0.0.1:4318).
"""

import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter


def init_telemetry() -> TracerProvider:
    """Initialize and return the TracerProvider. Idempotent."""
    resource = Resource.create({
        "service.name": os.getenv("OTEL_SERVICE_NAME_PYTHON", "tt-v2-agent-python"),
        "deployment.environment": "dev",
        "service.version": "v2",
    })

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318") + "/v1/traces",
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return provider


def get_tracer(name: str = "tt.v2.agent") -> trace.Tracer:
    return trace.get_tracer(name)
