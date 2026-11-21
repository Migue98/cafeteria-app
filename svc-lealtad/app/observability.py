"""Contexto de trazas y logs JSON; contrato común de los cuatro servicios."""

from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from traceback import format_exc
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from prometheus_client import Counter, Histogram

TRACEPARENT = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")


@dataclass(frozen=True, slots=True)
class TraceContext:
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    flags: str = "01"

    @classmethod
    def from_header(cls, incoming: str = "") -> TraceContext:
        match = TRACEPARENT.fullmatch(incoming)
        if match and int(match[1], 16) and int(match[2], 16):
            return cls(match[1], uuid4().hex[:16], match[2], match[3])
        return cls(uuid4().hex, uuid4().hex[:16])

    @property
    def traceparent(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-{self.flags}"


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
) -> None:
    @application.middleware("http")
    async def request_context(request: Request, call_next):
        started = perf_counter()
        context = TraceContext.from_header(request.headers.get("traceparent", ""))
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
