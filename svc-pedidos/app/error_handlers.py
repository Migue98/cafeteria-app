"""Traducción de errores de validación, negocio y dependencias a Problem JSON."""

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .clients import DependencyUnavailable, LoyaltyUnavailable
from .exceptions import IdempotencyConflict, OrderNotFound, ProductUnavailable
from .models import Problem
from .repository import RepositoryUnavailable


def problem_response(
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


def invalid_request_id(request: Request) -> JSONResponse:
    return problem_response(
        request,
        status=422,
        title="Encabezado inválido",
        detail="X-Request-ID debe ser un UUID válido.",
        code="VALIDATION_ERROR",
        slug="validation-error",
    )


def install_error_handlers(application: FastAPI) -> None:
    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return problem_response(
            request,
            status=422,
            title="Solicitud inválida",
            detail="Uno o más campos no cumplen el contrato.",
            code="VALIDATION_ERROR",
            slug="validation-error",
            errors=jsonable_encoder(exc.errors()),
        )

    @application.exception_handler(ProductUnavailable)
    async def product_unavailable_handler(request: Request, exc: ProductUnavailable):
        return problem_response(
            request,
            status=409,
            title="Producto no disponible",
            detail=str(exc),
            code="PRODUCT_UNAVAILABLE",
            slug="product-unavailable",
        )

    @application.exception_handler(IdempotencyConflict)
    async def idempotency_conflict_handler(request: Request, exc: IdempotencyConflict):
        return problem_response(
            request,
            status=409,
            title="Conflicto de idempotencia",
            detail=str(exc),
            code="IDEMPOTENCY_KEY_REUSED",
            slug="idempotency-key-reused",
        )

    @application.exception_handler(RepositoryUnavailable)
    @application.exception_handler(DependencyUnavailable)
    async def dependency_error_handler(request: Request, exc: RuntimeError):
        return problem_response(
            request,
            status=503,
            title="Servicio no disponible",
            detail=str(exc),
            code="DEPENDENCY_UNAVAILABLE",
            slug="dependency-unavailable",
        )

    @application.exception_handler(LoyaltyUnavailable)
    async def loyalty_error_handler(request: Request, exc: LoyaltyUnavailable):
        return problem_response(
            request,
            status=503,
            title="Lealtad no disponible",
            detail=str(exc),
            code="LOYALTY_UNAVAILABLE",
            slug="loyalty-unavailable",
        )

    @application.exception_handler(OrderNotFound)
    async def order_not_found_handler(request: Request, exc: OrderNotFound):
        return problem_response(
            request,
            status=404,
            title="Pedido no encontrado",
            detail=str(exc),
            code="ORDER_NOT_FOUND",
            slug="order-not-found",
        )
