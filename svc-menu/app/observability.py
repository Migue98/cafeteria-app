"""Métricas y logs correlacionados con trazas reales de OpenTelemetry."""

from __future__ import annotations

import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from traceback import format_exc
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.metrics import NoOpMeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from prometheus_client import Counter, Histogram


@dataclass(frozen=True, slots=True)
class TraceContext:
    """Vista del span del SDK para respuestas y logs, sin generar identificadores."""

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    flags: str = "01"

    @classmethod
    def from_span(cls, span: trace.Span, *, parent_span_id: str | None = None) -> TraceContext:
        context = span.get_span_context()
        parent = getattr(span, "parent", None)
        if parent is not None and parent.is_valid:
            parent_span_id = trace.format_span_id(parent.span_id)
        return cls(
            trace.format_trace_id(context.trace_id),
            trace.format_span_id(context.span_id),
            parent_span_id,
            f"{int(context.trace_flags):02x}",
        )

    @classmethod
    def current(cls) -> TraceContext | None:
        span = trace.get_current_span()
        return cls.from_span(span) if span.get_span_context().is_valid else None

    @property
    def traceparent(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-{self.flags}"


@dataclass(frozen=True, slots=True)
class Telemetry:
    """Un proveedor por aplicación; no modifica proveedores globales del proceso."""

    provider: TracerProvider

    @property
    def tracer(self) -> trace.Tracer:
        return self.provider.get_tracer("cafeteria")

    def shutdown(self) -> None:
        self.provider.shutdown()


def create_telemetry(service: str, version: str = "dev") -> Telemetry:
    configured_exporters = os.getenv("OTEL_TRACES_EXPORTER", "none").strip() or "none"
    exporters = {item.strip() for item in configured_exporters.split(",")}
    if not exporters <= {"none", "console", "otlp"} or ("none" in exporters and len(exporters) > 1):
        raise ValueError("OTEL_TRACES_EXPORTER debe ser none, console, otlp o console,otlp")
    if "otlp" in exporters:
        protocol = os.getenv(
            "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL",
            os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf"),
        )
        if protocol != "http/protobuf":
            raise ValueError("El exportador instalado usa OTLP http/protobuf")
    provider = TracerProvider(
        resource=Resource.create({"service.name": service, "service.version": version})
    )
    if "console" in exporters:
        provider.add_span_processor(
            BatchSpanProcessor(
                ConsoleSpanExporter(
                    out=sys.stdout, formatter=lambda span: span.to_json(indent=None) + "\n"
                )
            )
        )
    if "otlp" in exporters:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    return Telemetry(provider)


def get_logger(service: str) -> logging.Logger:
    """Emite también INFO en stdout cuando Uvicorn no configura el logger de app."""
    logger = logging.getLogger(service)
    logger.setLevel(logging.INFO)
    output = logging.getLogger(service.split(".")[0])
    output.setLevel(logging.INFO)
    if not any(handler.get_name() == "cafeteria-json" for handler in output.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.set_name("cafeteria-json")
        handler.setFormatter(logging.Formatter("%(message)s"))
        output.addHandler(handler)
    return logger


def log_event(
    logger: logging.Logger,
    message: str,
    *,
    level: int = logging.INFO,
    context: TraceContext | None = None,
    request_id: str | None = None,
    **fields: object,
) -> None:
    context = context or TraceContext.current()
    logger.log(
        level,
        json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": logging.getLevelName(level),
                "service": logger.name.split(".")[0],
                "message": message,
                "request_id": request_id,
                "trace_id": context.trace_id if context else None,
                "span_id": context.span_id if context else None,
                "parent_span_id": context.parent_span_id if context else None,
                **fields,
            },
            ensure_ascii=False,
        ),
    )


def install_observability(
    application: FastAPI,
    *,
    logger: logging.Logger,
    requests: Counter,
    duration: Histogram,
    invalid_response,
    telemetry: Telemetry | None = None,
) -> None:
    telemetry = telemetry or create_telemetry(logger.name)
    application.state.telemetry = telemetry
    original_lifespan = application.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            async with original_lifespan(app) as state:
                yield state
        finally:
            telemetry.shutdown()

    application.router.lifespan_context = lifespan

    @application.middleware("http")
    async def request_context(request: Request, call_next):
        started = perf_counter()
        remote_parent = trace.get_current_span(
            propagate.extract(request.headers)
        ).get_span_context()
        context = TraceContext.from_span(
            trace.get_current_span(),
            parent_span_id=trace.format_span_id(remote_parent.span_id)
            if remote_parent.is_valid
            else None,
        )
        request.state.trace_context = context
        request.state.trace_id = context.trace_id
        request.state.traceparent = context.traceparent
        supplied = request.headers.get("X-Request-ID")
        valid_request_id = True
        try:
            request.state.request_id = str(UUID(supplied)) if supplied else str(uuid4())
        except ValueError:
            request.state.request_id = str(uuid4())
            valid_request_id = False

        status_code = 500
        try:
            response = await call_next(request) if valid_request_id else invalid_response(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request.state.request_id
            response.headers["traceparent"] = context.traceparent
            return response
        except Exception:
            log_event(
                logger,
                "request_failed",
                level=logging.ERROR,
                context=context,
                request_id=request.state.request_id,
                exception=format_exc(),
            )
            raise
        finally:
            route = getattr(request.scope.get("route"), "path", "unmatched")
            elapsed = perf_counter() - started
            requests.labels(
                service=logger.name,
                method=request.method,
                route=route,
                status_code=str(status_code),
            ).inc()
            duration.labels(service=logger.name, method=request.method, route=route).observe(
                elapsed
            )
            level = (
                logging.ERROR
                if status_code >= 500
                else logging.WARNING
                if status_code >= 400
                else logging.INFO
            )
            log_event(
                logger,
                "request_completed",
                level=level,
                context=context,
                request_id=request.state.request_id,
                method=request.method,
                path=request.url.path,
                route=route,
                status_code=status_code,
                duration_ms=round(elapsed * 1000, 3),
            )

    FastAPIInstrumentor.instrument_app(
        application,
        tracer_provider=telemetry.provider,
        meter_provider=NoOpMeterProvider(),
        exclude_spans=["receive", "send"],
    )
