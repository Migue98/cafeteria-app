"""Creación, consulta y recuperación de pedidos."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from ..clients import LoyaltyClient, LoyaltyUnavailable, MenuClient
from ..exceptions import IdempotencyConflict, OrderNotFound, ProductUnavailable
from ..metrics import ORDER_VALUE, ORDERS_CREATED
from ..models import CreateOrderRequest, Order, OrderItem, OrderList
from ..repository import OrderRepository, RepositoryUnavailable, StoredOrder


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


class OrderService:
    def __init__(
        self, repository: OrderRepository, menu: MenuClient, loyalty: LoyaltyClient
    ) -> None:
        self.repository = repository
        self.menu = menu
        self.loyalty = loyalty

    def create_order(
        self,
        payload: CreateOrderRequest,
        *,
        idempotency_key: str,
        request_id: str,
        traceparent: str,
    ) -> Order:
        body_hash = _request_hash(payload)
        stored = self.repository.get_by_idempotency_key(idempotency_key)
        if stored is not None:
            return _replay(stored, body_hash)

        order_items: list[OrderItem] = []
        for requested_item in payload.items:
            product = self.menu.get_product(
                requested_item.product_id,
                request_id=request_id,
                traceparent=traceparent,
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
        inserted = self.repository.save(
            order,
            idempotency_key=idempotency_key,
            request_hash=body_hash,
        )
        if not inserted:
            stored = self.repository.get_by_idempotency_key(idempotency_key)
            if stored is None:
                raise RepositoryUnavailable("No fue posible recuperar el pedido concurrente")
            return _replay(stored, body_hash)

        try:
            points = self.loyalty.award(order, request_id=request_id, traceparent=traceparent)
            order = self.repository.mark_loyalty_awarded(order.id, points)
        except LoyaltyUnavailable:
            pass

        ORDERS_CREATED.labels(status="confirmed").inc()
        ORDER_VALUE.inc(order.total_cents)
        return order

    def list_orders(self, customer_id: UUID, *, limit: int, offset: int) -> OrderList:
        orders, total = self.repository.list_for_customer(customer_id, limit=limit, offset=offset)
        return OrderList(items=orders, total=total, limit=limit, offset=offset)

    def get_order(self, order_id: UUID) -> Order:
        order = self.repository.get(order_id)
        if order is None:
            raise OrderNotFound(order_id)
        return order

    def retry_loyalty(self, order_id: UUID, *, request_id: str, traceparent: str) -> Order:
        order = self.get_order(order_id)
        if order.loyalty_status == "awarded":
            return order
        points = self.loyalty.award(order, request_id=request_id, traceparent=traceparent)
        return self.repository.mark_loyalty_awarded(order.id, points)
