"""Carrito e identidad anónima sobre una sesión mutable."""

from __future__ import annotations

import hashlib
import json
from collections.abc import MutableMapping
from typing import Any
from uuid import UUID, uuid4

Session = MutableMapping[str, Any]


def customer_id(session: Session) -> str:
    raw = session.get("customer_id")
    try:
        identifier = str(UUID(raw)) if raw else str(uuid4())
    except (TypeError, ValueError):
        identifier = str(uuid4())
    session["customer_id"] = identifier
    return identifier


def read_cart(session: Session) -> dict[int, int]:
    stored = session.get("cart", {})
    cart: dict[int, int] = {}
    if isinstance(stored, dict):
        for product_id, quantity in stored.items():
            try:
                parsed_id = int(product_id)
                parsed_quantity = int(quantity)
            except (TypeError, ValueError):
                continue
            if parsed_id >= 1 and 1 <= parsed_quantity <= 20:
                cart[parsed_id] = parsed_quantity
    return cart


def save_cart(session: Session, cart: dict[int, int]) -> None:
    session["cart"] = {str(key): value for key, value in cart.items()}
    if cart:
        customer_id(session)
        checkout_key(session, cart)
    else:
        session.pop("checkout_attempt", None)


def cart_context(cart: dict[int, int], products: list[dict[str, Any]]) -> dict[str, Any]:
    product_map = {product["id"]: product for product in products}
    rows = []
    for product_id, quantity in sorted(cart.items()):
        product = product_map.get(product_id)
        if product is None:
            continue
        rows.append(
            {
                **product,
                "quantity": quantity,
                "line_total_cents": product["price_cents"] * quantity,
            }
        )
    return {
        "cart_rows": rows,
        "cart_count": sum(row["quantity"] for row in rows),
        "cart_total_cents": sum(row["line_total_cents"] for row in rows),
    }


def checkout_key(session: Session, cart: dict[int, int]) -> str:
    fingerprint = hashlib.sha256(
        json.dumps(cart, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    attempt = session.get("checkout_attempt", {})
    if isinstance(attempt, dict) and attempt.get("fingerprint") == fingerprint:
        key = attempt.get("key")
        if isinstance(key, str):
            return key
    key = f"frontend-order-{uuid4()}"
    session["checkout_attempt"] = {"fingerprint": fingerprint, "key": key}
    return key


def add_item(session: Session, product_id: int) -> None:
    cart = read_cart(session)
    cart[product_id] = min(cart.get(product_id, 0) + 1, 20)
    save_cart(session, cart)


def decrement_item(session: Session, product_id: int) -> None:
    cart = read_cart(session)
    if product_id in cart:
        cart[product_id] -= 1
        if cart[product_id] <= 0:
            cart.pop(product_id)
    save_cart(session, cart)


def remove_item(session: Session, product_id: int) -> None:
    cart = read_cart(session)
    cart.pop(product_id, None)
    save_cart(session, cart)
