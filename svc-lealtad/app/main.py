"""API HTTP del servicio de lealtad."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
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
from .observability import Telemetry, create_telemetry, get_logger, install_observability
from .probes import ProbeChecks, install_probes
from .repository import (
    LoyaltyRepository,
    PostgresLoyaltyRepository,
    RepositoryUnavailable,
    StoredAward,
)

LOGGER = get_logger("svc-lealtad")

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
    problem = Problem(
        type=f"https://cafeteria.example/problems/{slug}",
        title=title,
        status=status,
        detail=detail,
        code=code,
        trace_id=request.state.trace_id,
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


def create_app(
    repository: LoyaltyRepository | None = None,
    *,
    telemetry: Telemetry | None = None,
    readiness_checks: ProbeChecks | None = None,
) -> FastAPI:
    settings = load_settings()
    telemetry = telemetry or create_telemetry(LOGGER.name, settings.app_version)
    application = FastAPI(
        title="Cafetería - Servicio de lealtad",
        version="0.1.0",
        description="Acreditación idempotente y consulta de puntos.",
    )
    application.state.repository = repository or PostgresLoyaltyRepository(
        settings.database_url, tracer_provider=telemetry.provider
    )
    application.state.app_version = settings.app_version

    def invalid_request_id(request: Request) -> JSONResponse:
        return _problem_response(
            request,
            status=422,
            title="Encabezado inválido",
            detail="X-Request-ID debe ser un UUID válido.",
            code="VALIDATION_ERROR",
            slug="validation-error",
        )

    install_observability(
        application,
        logger=LOGGER,
        requests=HTTP_REQUESTS,
        duration=HTTP_DURATION,
        invalid_response=invalid_request_id,
        telemetry=telemetry,
    )

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

        def replay_existing(stored: StoredAward, *, order_conflict: bool) -> PointAward:
            replay = _replay(stored, body_hash, order_conflict=order_conflict)
            if order_conflict:
                reserved = repository.bind_idempotency_key(
                    idempotency_key, stored.award.movement_id
                )
                replay = _replay(reserved, body_hash, order_conflict=False)
            response.status_code = 200
            AWARDS_TOTAL.labels(status="replayed").inc()
            return replay

        stored = repository.get_by_idempotency_key(idempotency_key)
        if stored is not None:
            return replay_existing(stored, order_conflict=False)

        stored = repository.get_by_order_id(payload.order_id)
        if stored is not None:
            return replay_existing(stored, order_conflict=True)

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
                return replay_existing(stored, order_conflict=False)
            stored = repository.get_by_order_id(payload.order_id)
            if stored is not None:
                return replay_existing(stored, order_conflict=True)
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

    install_probes(
        application, "svc-lealtad", checks=readiness_checks, database_url=settings.database_url
    )
    return application


app = create_app()
