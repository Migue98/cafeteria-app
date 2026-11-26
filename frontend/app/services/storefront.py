"""Coordina catálogo, compras e historial sin conocer HTTP ni Jinja."""

from __future__ import annotations

from typing import Any

from ..clients import BackendError, BackendGateway
from ..exceptions import EmptyCart, ProductUnavailable
from .cart import (
    Session,
    add_item,
    cart_context,
    checkout_key,
    customer_id,
    read_cart,
    save_cart,
)


class StorefrontService:
    def __init__(self, backend: BackendGateway) -> None:
        self.backend = backend

    def customer_balance(
        self, identifier: str, *, request_id: str, traceparent: str
    ) -> int | None:
        try:
            return self.backend.get_balance(
                customer_id=identifier,
                request_id=request_id,
                traceparent=traceparent,
            )["balance"]
        except BackendError:
            return None

    def menu_context(
        self,
        session: Session,
        *,
        request_id: str,
        traceparent: str,
        category: str | None = None,
        checkout_error: str | None = None,
    ) -> dict[str, Any]:
        identifier = customer_id(session)
        cart = read_cart(session)
        if cart:
            checkout_key(session, cart)
        products = self.backend.list_products(
            request_id=request_id, traceparent=traceparent
        )
        categories = sorted({product["category"] for product in products})
        visible_products = [
            product
            for product in products
            if category is None or product["category"] == category
        ]
        try:
            balance = self.backend.get_balance(
                customer_id=identifier,
                request_id=request_id,
                traceparent=traceparent,
            )["balance"]
            balance_available = True
        except BackendError:
            balance = 0
            balance_available = False
        return {
            "products": visible_products,
            "all_products": products,
            "categories": categories,
            "selected_category": category,
            "customer_id": identifier,
            "balance": balance,
            "balance_available": balance_available,
            "checkout_error": checkout_error,
            **cart_context(cart, products),
        }

    def add_to_cart(
        self,
        session: Session,
        product_id: int,
        *,
        request_id: str,
        traceparent: str,
    ) -> dict[str, Any]:
        products = self.backend.list_products(
            request_id=request_id, traceparent=traceparent
        )
        if product_id not in {product["id"] for product in products}:
            raise ProductUnavailable("El producto no está disponible.")
        add_item(session, product_id)
        return cart_context(read_cart(session), products)

    def current_cart(
        self, session: Session, *, request_id: str, traceparent: str
    ) -> dict[str, Any]:
        products = self.backend.list_products(
            request_id=request_id, traceparent=traceparent
        )
        return cart_context(read_cart(session), products)

    def checkout(
        self, session: Session, *, request_id: str, traceparent: str
    ) -> dict[str, Any]:
        cart = read_cart(session)
        if not cart:
            raise EmptyCart("Agrega al menos un producto antes de confirmar.")
        identifier = customer_id(session)
        order = self.backend.create_order(
            customer_id=identifier,
            items=[
                {"product_id": pid, "quantity": qty}
                for pid, qty in sorted(cart.items())
            ],
            idempotency_key=checkout_key(session, cart),
            request_id=request_id,
            traceparent=traceparent,
        )
        save_cart(session, {})
        session.pop("checkout_attempt", None)
        return {
            "order": order,
            "balance": self.customer_balance(
                identifier,
                request_id=request_id,
                traceparent=traceparent,
            ),
        }

    def order_history(
        self, session: Session, *, request_id: str, traceparent: str
    ) -> dict[str, Any]:
        identifier = customer_id(session)
        orders = self.backend.list_orders(
            customer_id=identifier,
            request_id=request_id,
            traceparent=traceparent,
        )
        return {
            "orders": orders,
            "balance": self.customer_balance(
                identifier,
                request_id=request_id,
                traceparent=traceparent,
            ),
            "has_pending": any(
                order["loyalty_status"] == "pending" for order in orders
            ),
        }

    def order_points(
        self,
        session: Session,
        order_id: str,
        *,
        request_id: str,
        traceparent: str,
    ) -> dict[str, Any] | None:
        identifier = customer_id(session)
        order = self.backend.get_order(
            order_id=order_id,
            request_id=request_id,
            traceparent=traceparent,
        )
        if order["customer_id"] != identifier:
            return None
        return {
            "order": order,
            "balance": self.customer_balance(
                identifier,
                request_id=request_id,
                traceparent=traceparent,
            ),
        }
