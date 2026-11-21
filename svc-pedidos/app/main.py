"""API HTTP del servicio de pedidos."""

from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, Path, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from .clients import (
    DependencyUnavailable,
    HttpLoyaltyClient,
    HttpMenuClient,
    LoyaltyClient,
    LoyaltyUnavailable,
    MenuClient,
)
from .config import load_settings
from .loyalty_retry import loyalty_retry_loop
from .models import (
    CreateOrderRequest,
    DependencyHealth,
    HealthDependencies,
    HealthResponse,
    Order,
    OrderItem,
    OrderList,
    Problem,
)
from .observability import get_logger, install_observability
from .repository import (
    OrderRepository,
    PostgresOrderRepository,
    RepositoryUnavailable,
    StoredOrder,
)

LOGGER = get_logger("svc-pedidos")

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
ORDERS_CREATED = Counter(
    "cafe_orders_total",
    "Pedidos creados.",
    ["status"],
)
ORDER_VALUE = Counter(
    "cafe_order_value_cents_total",
    "Valor acumulado de pedidos confirmados en centavos.",
)


class ProductUnavailable(RuntimeError):
    def __init__(self, product_id: int) -> None:
        self.product_id = product_id
        super().__init__(f"El producto {product_id} no está disponible")


class IdempotencyConflict(RuntimeError):
    """La misma clave fue reutilizada con una solicitud diferente."""


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


def _request_hash(payload: CreateOrderRequest) -> str:
    canonical = json.dumps(
        payload.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _replay(stored: StoredOrder, request_hash: str) -> Order:
    if stored.request_hash != request_hash:
        raise IdempotencyConflict("La clave ya fue usada con otra solicitud")
    return stored.order.model_copy(update={"replayed": True})


def get_repository(request: Request) -> OrderRepository:
    return request.app.state.repository


def get_menu_client(request: Request) -> MenuClient:
    return request.app.state.menu_client


def get_loyalty_client(request: Request) -> LoyaltyClient:
    return request.app.state.loyalty_client


RepositoryDependency = Annotated[OrderRepository, Depends(get_repository)]
MenuDependency = Annotated[MenuClient, Depends(get_menu_client)]
LoyaltyDependency = Annotated[LoyaltyClient, Depends(get_loyalty_client)]


def create_app(
    repository: OrderRepository | None = None,
    menu_client: MenuClient | None = None,
    loyalty_client: LoyaltyClient | None = None,
) -> FastAPI:
    settings = load_settings()
    configured_repository = repository or PostgresOrderRepository(settings.database_url)
    configured_menu_client = menu_client or HttpMenuClient(
        settings.menu_url, settings.http_timeout_seconds
    )
    configured_loyalty_client = loyalty_client or HttpLoyaltyClient(
        settings.loyalty_url, settings.http_timeout_seconds
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        retry_task: asyncio.Task[None] | None = None
        if settings.loyalty_retry_enabled:
            retry_task = asyncio.create_task(
                loyalty_retry_loop(
                    configured_repository,
                    configured_loyalty_client,
                    interval_seconds=settings.loyalty_retry_interval_seconds,
                    batch_size=settings.loyalty_retry_batch_size,
                ),
                name="loyalty-retry",
            )
        app.state.loyalty_retry_task = retry_task
        try:
            yield
        finally:
            if retry_task is not None:
                retry_task.cancel()
                with suppress(asyncio.CancelledError):
                    await retry_task

    application = FastAPI(
        title="Cafetería - Servicio de pedidos",
        version="0.1.0",
        description="Creación, persistencia y consulta de pedidos.",
        lifespan=lifespan,
    )
    application.state.repository = configured_repository
    application.state.menu_client = configured_menu_client
    application.state.loyalty_client = configured_loyalty_client
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
            detail="Uno o más campos no cumplen el contrato.",
            code="VALIDATION_ERROR",
            slug="validation-error",
            errors=jsonable_encoder(exc.errors()),
        )

    @application.exception_handler(ProductUnavailable)
    async def product_unavailable_handler(request: Request, exc: ProductUnavailable):
        return _problem_response(
            request,
            status=409,
            title="Producto no disponible",
            detail=str(exc),
            code="PRODUCT_UNAVAILABLE",
            slug="product-unavailable",
        )

    @application.exception_handler(IdempotencyConflict)
    async def idempotency_conflict_handler(request: Request, exc: IdempotencyConflict):
        return _problem_response(
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
        return _problem_response(
            request,
            status=503,
            title="Servicio no disponible",
            detail=str(exc),
            code="DEPENDENCY_UNAVAILABLE",
            slug="dependency-unavailable",
        )

    @application.exception_handler(LoyaltyUnavailable)
    async def loyalty_error_handler(request: Request, exc: LoyaltyUnavailable):
        return _problem_response(
            request,
            status=503,
            title="Lealtad no disponible",
            detail=str(exc),
            code="LOYALTY_UNAVAILABLE",
            slug="loyalty-unavailable",
        )

    @application.get(
        "/health",
        response_model=HealthResponse,
        tags=["operación"],
        operation_id="ordersHealth",
    )
    def health(
        request: Request,
        repository: RepositoryDependency,
        menu: MenuDependency,
        loyalty: LoyaltyDependency,
    ) -> HealthResponse:
        postgres_latency = repository.health()
        menu_latency = menu.health(
            request_id=request.state.request_id,
            traceparent=request.state.traceparent,
        )
        try:
            loyalty_latency = loyalty.health(
                request_id=request.state.request_id,
                traceparent=request.state.traceparent,
            )
            loyalty_health = DependencyHealth(
                status="up", critical=False, latency_ms=loyalty_latency
            )
            status = "healthy"
        except LoyaltyUnavailable:
            loyalty_health = DependencyHealth(status="down", critical=False)
            status = "degraded"

        return HealthResponse(
            status=status,
            version=request.app.state.app_version,
            dependencies=HealthDependencies(
                postgres=DependencyHealth(status="up", critical=True, latency_ms=postgres_latency),
                menu=DependencyHealth(status="up", critical=True, latency_ms=menu_latency),
                loyalty=loyalty_health,
            ),
        )

    @application.get(
        "/metrics",
        response_class=Response,
        tags=["operación"],
        operation_id="ordersMetrics",
    )
    def metrics() -> Response:
        return Response(content=generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})

    @application.post(
        "/api/v1/orders",
        response_model=Order,
        status_code=201,
        tags=["pedidos"],
        operation_id="createOrder",
    )
    def create_order(
        request: Request,
        response: Response,
        payload: CreateOrderRequest,
        repository: RepositoryDependency,
        menu: MenuDependency,
        loyalty: LoyaltyDependency,
        idempotency_key: Annotated[
            str,
            Header(
                alias="Idempotency-Key",
                min_length=8,
                max_length=128,
                pattern=r"^[A-Za-z0-9._:-]+$",
            ),
        ],
    ) -> Order:
        body_hash = _request_hash(payload)
        stored = repository.get_by_idempotency_key(idempotency_key)
        if stored is not None:
            response.status_code = 200
            return _replay(stored, body_hash)

        order_items: list[OrderItem] = []
        for requested_item in payload.items:
            product = menu.get_product(
                requested_item.product_id,
                request_id=request.state.request_id,
                traceparent=request.state.traceparent,
            )
            if product is None or not product.available:
                raise ProductUnavailable(requested_item.product_id)
            line_total = product.price_cents * requested_item.quantity
            order_items.append(
                OrderItem(
                    product_id=product.id,
                    sku=product.sku,
                    product_name=product.name,
                    quantity=requested_item.quantity,
                    unit_price_cents=product.price_cents,
                    line_total_cents=line_total,
                )
            )

        now = datetime.now(UTC)
        total = sum(item.line_total_cents for item in order_items)
        order = Order(
            id=uuid4(),
            customer_id=payload.customer_id,
            loyalty_status="pending",
            subtotal_cents=total,
            total_cents=total,
            items=order_items,
            created_at=now,
            updated_at=now,
        )
        inserted = repository.save(
            order,
            idempotency_key=idempotency_key,
            request_hash=body_hash,
        )
        if not inserted:
            stored = repository.get_by_idempotency_key(idempotency_key)
            if stored is None:
                raise RepositoryUnavailable("No fue posible recuperar el pedido concurrente")
            response.status_code = 200
            return _replay(stored, body_hash)

        try:
            points = loyalty.award(
                order,
                request_id=request.state.request_id,
                traceparent=request.state.traceparent,
            )
            order = repository.mark_loyalty_awarded(order.id, points)
        except LoyaltyUnavailable:
            pass

        ORDERS_CREATED.labels(status="confirmed").inc()
        ORDER_VALUE.inc(order.total_cents)
        return order

    @application.get(
        "/api/v1/orders",
        response_model=OrderList,
        tags=["pedidos"],
        operation_id="listOrders",
    )
    def list_orders(
        repository: RepositoryDependency,
        customer_id: Annotated[UUID, Query()],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> OrderList:
        orders, total = repository.list_for_customer(customer_id, limit=limit, offset=offset)
        return OrderList(items=orders, total=total, limit=limit, offset=offset)

    @application.get(
        "/api/v1/orders/{order_id}",
        response_model=Order,
        tags=["pedidos"],
        operation_id="getOrder",
    )
    def get_order(
        request: Request,
        repository: RepositoryDependency,
        order_id: Annotated[UUID, Path()],
    ) -> Order | JSONResponse:
        order = repository.get(order_id)
        if order is None:
            return _problem_response(
                request,
                status=404,
                title="Pedido no encontrado",
                detail=f"No existe el pedido {order_id}.",
                code="ORDER_NOT_FOUND",
                slug="order-not-found",
            )
        return order

    @application.post(
        "/api/v1/orders/{order_id}/loyalty/retry",
        response_model=Order,
        tags=["pedidos"],
        operation_id="retryOrderLoyalty",
    )
    def retry_loyalty(
        request: Request,
        repository: RepositoryDependency,
        loyalty: LoyaltyDependency,
        order_id: Annotated[UUID, Path()],
    ) -> Order | JSONResponse:
        order = repository.get(order_id)
        if order is None:
            return _problem_response(
                request,
                status=404,
                title="Pedido no encontrado",
                detail=f"No existe el pedido {order_id}.",
                code="ORDER_NOT_FOUND",
                slug="order-not-found",
            )
        if order.loyalty_status == "awarded":
            return order
        points = loyalty.award(
            order,
            request_id=request.state.request_id,
            traceparent=request.state.traceparent,
        )
        return repository.mark_loyalty_awarded(order.id, points)

    return application


app = create_app()
