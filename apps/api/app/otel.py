from __future__ import annotations

import os
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

try:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
except Exception:  # pragma: no cover - runtime environment fallback
    OTLPSpanExporter = None  # type: ignore[assignment]


_configured = False
_provider: TracerProvider | None = None


def _get_or_create_provider(service_name: str) -> TracerProvider:
    global _provider

    provider = _provider
    if provider is not None:
        return provider

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": os.getenv("APP_VERSION", "0.1.0"),
        }
    )
    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)
    _provider = provider
    return provider


def setup_otel(service_name: str, enable: bool) -> TracerProvider | None:
    global _configured, _provider

    if not enable:
        return None

    provider = _get_or_create_provider(service_name)

    if _configured:
        return provider

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint and OTLPSpanExporter is not None:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))

    if os.getenv("OTEL_CONSOLE_EXPORTER", "false").lower() == "true":
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    _configured = True
    return provider


def setup_inmemory_otel(service_name: str = "api") -> InMemorySpanExporter:
    provider = _get_or_create_provider(service_name)
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


def get_tracer(name: str):
    return trace.get_tracer(name)


def get_fastapi_server_request_hook():
    def server_request_hook(span, scope: dict[str, Any]) -> None:  # type: ignore[no-untyped-def]
        if span is None:
            return
        headers = dict(scope.get("headers", []))
        correlation_raw = headers.get(b"x-correlation-id")
        if correlation_raw:
            span.set_attribute("correlation_id", correlation_raw.decode("utf-8"))

    return server_request_hook
