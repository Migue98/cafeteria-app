"""API HTTP del servicio de menú."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, FastAPI, Path, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from .config import load_settings
from .models import (
    DependencyHealth,
    HealthDependencies,
    HealthResponse,
    Problem,
    Product,
    ProductList,
)
from .observability import get_logger, install_observability, log_event
from .repository import (
    PostgresProductRepository,
    ProductRepository,
    RepositoryUnavailable,
)

LOGGER = get_logger("svc-menu")

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


def get_repository(request: Request) -> ProductRepository:
    return request.app.state.repository


RepositoryDependency = Annotated[ProductRepository, Depends(get_repository)]


def create_app(repository: ProductRepository | None = None) -> FastAPI:
    settings = load_settings()
    application = FastAPI(
        title="Cafetería - Servicio de menú",
        version="0.1.0",
        description="Catálogo de productos, precios y disponibilidad.",
    )
    application.state.repository = repository or PostgresProductRepository(settings.database_url)
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
    )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return _problem_response(
            request,
            status=422,
            title="Solicitud inválida",
            detail="Uno o más parámetros no cumplen el contrato.",
            code="VALIDATION_ERROR",
            slug="validation-error",
            errors=jsonable_encoder(exc.errors()),
        )

    @application.exception_handler(RepositoryUnavailable)
    async def repository_error_handler(request: Request, exc: RepositoryUnavailable):
        log_event(
            LOGGER,
            "repository_unavailable",
            level=logging.WARNING,
            context=request.state.trace_context,
            request_id=request.state.request_id,
            detail=str(exc),
        )
        return _problem_response(
            request,
            status=503,
            title="Servicio no disponible",
            detail="PostgreSQL no está disponible temporalmente.",
            code="DEPENDENCY_UNAVAILABLE",
            slug="dependency-unavailable",
        )

    @application.get(
        "/health",
        response_model=HealthResponse,
        tags=["operación"],
        operation_id="menuHealth",
    )
    def health(repository: RepositoryDependency, request: Request) -> HealthResponse:
        latency_ms = repository.health()
        return HealthResponse(
            status="healthy",
            version=request.app.state.app_version,
            dependencies=HealthDependencies(
                postgres=DependencyHealth(status="up", latency_ms=latency_ms)
            ),
        )

    @application.get(
        "/metrics",
        response_class=Response,
        tags=["operación"],
        operation_id="menuMetrics",
    )
    def metrics() -> Response:
        return Response(content=generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})

    @application.get(
        "/api/v1/products",
        response_model=ProductList,
        tags=["productos"],
        operation_id="listProducts",
    )
    def list_products(
        repository: RepositoryDependency,
        category: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
        available: Annotated[bool, Query()] = True,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> ProductList:
        products, total = repository.list_products(
            category=category,
            available=available,
            limit=limit,
            offset=offset,
        )
        return ProductList(items=products, total=total, limit=limit, offset=offset)

    @application.get(
        "/api/v1/products/{product_id}",
        response_model=Product,
        tags=["productos"],
        operation_id="getProduct",
    )
    def get_product(
        request: Request,
        repository: RepositoryDependency,
        product_id: Annotated[int, Path(ge=1)],
    ) -> Product | JSONResponse:
        product = repository.get_product(product_id)
        if product is None:
            return _problem_response(
                request,
                status=404,
                title="Producto no encontrado",
                detail=f"No existe el producto {product_id}.",
                code="PRODUCT_NOT_FOUND",
                slug="product-not-found",
            )
        return product

    return application


app = create_app()
