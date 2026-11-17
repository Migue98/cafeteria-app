"""API HTTP del servicio de lealtad."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from time import perf_counter
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, Path, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from .config import load_settings
from .models import (
    DependencyHealth,
    EarnPointsRequest,
    HealthDependencies,
    HealthResponse,
    PointAward,
    PointsBalance,
    Problem,
)
from .repository import (
    LoyaltyRepository,
    PostgresLoyaltyRepository,
    RepositoryUnavailable,
    StoredAward,
)

LOGGER = logging.getLogger("svc-lealtad")
TRACEPARENT_PATTERN = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$")

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Peticiones HTTP atendidas.",
    ["service", "method", "route", "status_code"],
)
HTTP_DURATION = Histogram(
    "http_request_duration_seconds",
    "Duración de las peticiones HTTP.",
    ["service", "method", "route"],
)
POINTS_TOTAL = Counter(
    "cafe_loyalty_points_total",
    "Puntos de lealtad acreditados.",
)
AWARDS_TOTAL = Counter(
    "cafe_loyalty_awards_total",
    "Operaciones de acreditación.",
    ["status"],
)


class LoyaltyConflict(RuntimeError):
    def __init__(self, message: str, *, code: str, slug: str) -> None:
        self.code = code
        self.slug = slug
        super().__init__(message)


def _trace_context(request: Request) -> tuple[str, str]:
    incoming = request.headers.get("traceparent", "").lower()
    match = TRACEPARENT_PATTERN.fullmatch(incoming)
    if match:
        return match.group(1), incoming
    trace_id = uuid4().hex
    span_id = uuid4().hex[:16]
    return trace_id, f"00-{trace_id}-{span_id}-01"


def _problem_response(
    request: Request,
    *,
    status: int,
    title: str,
    detail: str,
    code: str,
    slug: str,
    errors: list[dict] | None = None,
) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", _trace_context(request)[0])
    problem = Problem(
        type=f"https://cafeteria.example/problems/{slug}",
        title=title,
        status=status,
        detail=detail,
        code=code,
        trace_id=trace_id,
        instance=request.url.path,
        errors=errors,
    )
    return JSONResponse(
        status_code=status,
        content=problem.model_dump(exclude_none=True),
        media_type="application/problem+json",
    )


def _request_hash(payload: EarnPointsRequest) -> str:
    canonical = json.dumps(
        payload.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _replay(stored: StoredAward, request_hash: str, *, order_conflict: bool) -> PointAward:
    if stored.request_hash != request_hash:
        if order_conflict:
            raise LoyaltyConflict(
                "El pedido ya fue acreditado con datos diferentes.",
                code="ORDER_ALREADY_AWARDED",
                slug="order-already-awarded",
            )
        raise LoyaltyConflict(
            "La clave ya fue utilizada con otra solicitud.",
            code="IDEMPOTENCY_KEY_REUSED",
            slug="idempotency-key-reused",
        )
    return stored.award.model_copy(update={"replayed": True})


def get_repository(request: Request) -> LoyaltyRepository:
    return request.app.state.repository


RepositoryDependency = Annotated[LoyaltyRepository, Depends(get_repository)]


def create_app(repository: LoyaltyRepository | None = None) -> FastAPI:
    settings = load_settings()
    application = FastAPI(
        title="Cafetería - Servicio de lealtad",
        version="0.1.0",
        description="Acreditación idempotente y consulta de puntos.",
    )
    application.state.repository = repository or PostgresLoyaltyRepository(settings.database_url)
    application.state.app_version = settings.app_version

    @application.middleware("http")
    async def request_context(request: Request, call_next):
        started = perf_counter()
        supplied_request_id = request.headers.get("X-Request-ID")
        try:
            request_id = UUID(supplied_request_id) if supplied_request_id else uuid4()
        except ValueError:
            request.state.trace_id, request.state.traceparent = _trace_context(request)
            response = _problem_response(
                request,
                status=422,
                title="Encabezado inválido",
                detail="X-Request-ID debe ser un UUID válido.",
                code="VALIDATION_ERROR",
                slug="validation-error",
            )
            response.headers["X-Request-ID"] = str(uuid4())
            return response

        request.state.request_id = str(request_id)
        request.state.trace_id, request.state.traceparent = _trace_context(request)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id

        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")
        duration = perf_counter() - started
        HTTP_REQUESTS.labels(
            service="svc-lealtad",
            method=request.method,
            route=route_path,
            status_code=str(response.status_code),
        ).inc()
        HTTP_DURATION.labels(
            service="svc-lealtad",
            method=request.method,
            route=route_path,
        ).observe(duration)
        LOGGER.info(
            json.dumps(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "level": "INFO",
                    "service": "svc-lealtad",
                    "message": "request_completed",
                    "method": request.method,
                    "path": request.url.path,
                    "route": route_path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration * 1000, 3),
                    "request_id": request.state.request_id,
                    "trace_id": request.state.trace_id,
                }
            )
        )
        return response

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return _problem_response(
            request,
            status=422,
            title="Solicitud inválida",
            detail="Uno o más campos no cumplen el contrato.",
            code="VALIDATION_ERROR",
            slug="validation-error",
            errors=jsonable_encoder(exc.errors()),
        )

    @application.exception_handler(LoyaltyConflict)
    async def conflict_handler(request: Request, exc: LoyaltyConflict):
        AWARDS_TOTAL.labels(status="conflict").inc()
        return _problem_response(
            request,
            status=409,
            title="Conflicto de acreditación",
            detail=str(exc),
            code=exc.code,
            slug=exc.slug,
        )

    @application.exception_handler(RepositoryUnavailable)
    async def repository_error_handler(request: Request, exc: RepositoryUnavailable):
        return _problem_response(
            request,
            status=503,
            title="Servicio no disponible",
            detail=str(exc),
            code="DEPENDENCY_UNAVAILABLE",
            slug="dependency-unavailable",
        )

    @application.get(
        "/health",
        response_model=HealthResponse,
        tags=["operación"],
        operation_id="loyaltyHealth",
    )
    def health(request: Request, repository: RepositoryDependency) -> HealthResponse:
        latency = repository.health()
        return HealthResponse(
            status="healthy",
            version=request.app.state.app_version,
            dependencies=HealthDependencies(
                postgres=DependencyHealth(status="up", latency_ms=latency)
            ),
        )

    @application.get(
        "/metrics",
        response_class=Response,
        tags=["operación"],
        operation_id="loyaltyMetrics",
    )
    def metrics() -> Response:
        return Response(content=generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})

    @application.post(
        "/api/v1/points/earn",
        response_model=PointAward,
        status_code=201,
        tags=["lealtad"],
        operation_id="earnPoints",
    )
    def earn_points(
        response: Response,
        payload: EarnPointsRequest,
        repository: RepositoryDependency,
        idempotency_key: Annotated[
            str,
            Header(
                alias="Idempotency-Key",
                min_length=8,
                max_length=128,
                pattern=r"^[A-Za-z0-9._:-]+$",
            ),
        ],
    ) -> PointAward:
        body_hash = _request_hash(payload)
        stored = repository.get_by_idempotency_key(idempotency_key)
        if stored is not None:
            response.status_code = 200
            replay = _replay(stored, body_hash, order_conflict=False)
            AWARDS_TOTAL.labels(status="replayed").inc()
            return replay

        stored = repository.get_by_order_id(payload.order_id)
        if stored is not None:
            response.status_code = 200
            replay = _replay(stored, body_hash, order_conflict=True)
            AWARDS_TOTAL.labels(status="replayed").inc()
            return replay

        points_earned = payload.amount_cents // 1000
        award = repository.save_award(
            payload,
            points_earned=points_earned,
            idempotency_key=idempotency_key,
            request_hash=body_hash,
            movement_id=uuid4(),
            awarded_at=datetime.now(UTC),
        )
        if award is None:
            stored = repository.get_by_idempotency_key(idempotency_key)
            if stored is not None:
                response.status_code = 200
                replay = _replay(stored, body_hash, order_conflict=False)
                AWARDS_TOTAL.labels(status="replayed").inc()
                return replay
            stored = repository.get_by_order_id(payload.order_id)
            if stored is not None:
                response.status_code = 200
                replay = _replay(stored, body_hash, order_conflict=True)
                AWARDS_TOTAL.labels(status="replayed").inc()
                return replay
            raise RepositoryUnavailable("No fue posible recuperar la acreditación concurrente")

        POINTS_TOTAL.inc(points_earned)
        AWARDS_TOTAL.labels(status="awarded").inc()
        return award

    @application.get(
        "/api/v1/customers/{customer_id}/points",
        response_model=PointsBalance,
        tags=["lealtad"],
        operation_id="getPointsBalance",
    )
    def get_balance(
        repository: RepositoryDependency,
        customer_id: Annotated[UUID, Path()],
    ) -> PointsBalance:
        return repository.get_balance(customer_id)

    return application


app = create_app()
