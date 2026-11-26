"""Validación HTTP de pedidos y delegación a los casos de uso."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query, Request, Response

from ..dependencies import OrderServiceDependency
from ..models import CreateOrderRequest, Order, OrderList

router = APIRouter()


@router.post(
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
    service: OrderServiceDependency,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key", min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
        ),
    ],
) -> Order:
    order = service.create_order(
        payload,
        idempotency_key=idempotency_key,
        request_id=request.state.request_id,
        traceparent=request.state.traceparent,
    )
    if order.replayed:
        response.status_code = 200
    return order


@router.get(
    "/api/v1/orders",
    response_model=OrderList,
    tags=["pedidos"],
    operation_id="listOrders",
)
def list_orders(
    service: OrderServiceDependency,
    customer_id: Annotated[UUID, Query()],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OrderList:
    return service.list_orders(customer_id, limit=limit, offset=offset)


@router.get(
    "/api/v1/orders/{order_id}",
    response_model=Order,
    tags=["pedidos"],
    operation_id="getOrder",
)
def get_order(service: OrderServiceDependency, order_id: Annotated[UUID, Path()]) -> Order:
    return service.get_order(order_id)


@router.post(
    "/api/v1/orders/{order_id}/loyalty/retry",
    response_model=Order,
    tags=["pedidos"],
    operation_id="retryOrderLoyalty",
)
def retry_loyalty(
    request: Request,
    service: OrderServiceDependency,
    order_id: Annotated[UUID, Path()],
) -> Order:
    return service.retry_loyalty(
        order_id,
        request_id=request.state.request_id,
        traceparent=request.state.traceparent,
    )
