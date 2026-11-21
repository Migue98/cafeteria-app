from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.clients import BackendError
from app.main import create_app


class FakeGateway:
    def __init__(self) -> None:
        now = datetime(2026, 11, 19, tzinfo=UTC).isoformat()
        self.products = [
            {
                "id": 1,
                "sku": "CAFE-AMERICANO",
                "name": "Café americano",
                "description": "Espresso diluido con agua caliente.",
                "category": "bebidas-calientes",
                "price_cents": 3500,
                "currency": "MXN",
                "available": True,
                "image_url": None,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": 11,
                "sku": "CROISSANT",
                "name": "Croissant",
                "description": "Croissant de mantequilla.",
                "category": "panaderia",
                "price_cents": 3900,
                "currency": "MXN",
                "available": True,
                "image_url": None,
                "created_at": now,
                "updated_at": now,
            },
        ]
        self.orders: list[dict[str, Any]] = []
        self.create_calls: list[dict[str, Any]] = []
        self.balance = 0
        self.closed = False
        self.loyalty_available = True
        self.orders_available = True

    def list_products(
        self, *, request_id: str, traceparent: str
    ) -> list[dict[str, Any]]:
        UUID(request_id)
        return self.products

    def create_order(
        self,
        *,
        customer_id: str,
        items: list[dict[str, int]],
        idempotency_key: str,
        request_id: str,
        traceparent: str,
    ) -> dict[str, Any]:
        UUID(customer_id)
        UUID(request_id)
        assert idempotency_key.startswith("frontend-order-")
        self.create_calls.append(
            {
                "customer_id": customer_id,
                "items": items,
                "idempotency_key": idempotency_key,
            }
        )
        product_map = {product["id"]: product for product in self.products}
        order_items = [
            {
                "product_id": item["product_id"],
                "sku": product_map[item["product_id"]]["sku"],
                "product_name": product_map[item["product_id"]]["name"],
                "quantity": item["quantity"],
                "unit_price_cents": product_map[item["product_id"]]["price_cents"],
                "line_total_cents": product_map[item["product_id"]]["price_cents"]
                * item["quantity"],
            }
            for item in items
        ]
        total = sum(item["line_total_cents"] for item in order_items)
        points = total // 1000
        if self.loyalty_available:
            self.balance += points
        order = {
            "id": str(uuid4()),
            "customer_id": customer_id,
            "status": "confirmed",
            "loyalty_status": "awarded" if self.loyalty_available else "pending",
            "points_earned": points if self.loyalty_available else None,
            "currency": "MXN",
            "subtotal_cents": total,
            "total_cents": total,
            "items": order_items,
            "replayed": False,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self.orders.insert(0, order)
        return order

    def list_orders(
        self, *, customer_id: str, request_id: str, traceparent: str
    ) -> list[dict[str, Any]]:
        if not self.orders_available:
            raise BackendError("Pedidos no disponible.")
        return [order for order in self.orders if order["customer_id"] == customer_id]

    def get_order(
        self, *, order_id: str, request_id: str, traceparent: str
    ) -> dict[str, Any]:
        if not self.orders_available:
            raise BackendError("Pedidos no disponible.")
        return next(order for order in self.orders if order["id"] == order_id)

    def get_balance(
        self, *, customer_id: str, request_id: str, traceparent: str
    ) -> dict[str, Any]:
        if not self.loyalty_available:
            raise BackendError("Lealtad no disponible.")
        return {"customer_id": customer_id, "balance": self.balance, "updated_at": None}

    def health(self, *, request_id: str, traceparent: str) -> dict[str, str]:
        return {"menu": "healthy", "orders": "healthy", "loyalty": "healthy"}

    def close(self) -> None:
        self.closed = True


class FailingGateway(FakeGateway):
    def list_products(
        self, *, request_id: str, traceparent: str
    ) -> list[dict[str, Any]]:
        raise BackendError("El menú no está disponible.")


def make_client(gateway: FakeGateway | None = None) -> tuple[TestClient, FakeGateway]:
    gateway = gateway or FakeGateway()
    return TestClient(create_app(gateway)), gateway


def test_home_renders_menu_balance_and_signed_session() -> None:
    client, _ = make_client()

    response = client.get("/")

    assert response.status_code == 200
    assert "Café americano" in response.text
    assert "Croissant" in response.text
    assert "0" in response.text
    assert "cafeteria_session" in response.cookies
    UUID(response.headers["X-Request-ID"])


def test_category_filter_keeps_only_matching_products() -> None:
    client, _ = make_client()

    response = client.get("/", params={"category": "panaderia"})

    assert response.status_code == 200
    assert "Croissant" in response.text
    assert "Café americano" not in response.text


def test_cart_supports_progressive_redirect_and_htmx_partial() -> None:
    client, _ = make_client()

    redirect = client.post("/cart/items/1", follow_redirects=False)
    partial = client.post("/cart/items/1", headers={"HX-Request": "true"})

    assert redirect.status_code == 303
    assert redirect.headers["location"] == "/#cart-panel"
    assert partial.status_code == 200
    assert 'id="cart-panel"' in partial.text
    assert "Café americano" in partial.text
    assert ">2<" in partial.text
    assert "$70.00" in partial.text


def test_checkout_creates_order_clears_cart_and_renders_receipt() -> None:
    client, gateway = make_client()
    client.post("/cart/items/1")
    client.post("/cart/items/1")
    client.post("/cart/items/11")

    response = client.post("/checkout")

    assert response.status_code == 200
    assert "Pedido confirmado" in response.text
    assert "$109.00" in response.text
    assert "+10 puntos" in response.text
    assert gateway.create_calls[0]["items"] == [
        {"product_id": 1, "quantity": 2},
        {"product_id": 11, "quantity": 1},
    ]

    home = client.get("/")
    assert "Tu carrito está esperando" in home.text


def test_empty_checkout_is_rejected_without_calling_orders() -> None:
    client, gateway = make_client()

    response = client.post("/checkout")

    assert response.status_code == 400
    assert "Agrega al menos un producto" in response.text
    assert gateway.create_calls == []


def test_order_history_uses_same_customer_session() -> None:
    client, _ = make_client()
    client.post("/cart/items/11")
    checkout = client.post("/checkout")

    history = client.get("/orders")

    assert checkout.status_code == 200
    assert history.status_code == 200
    assert "Croissant" in history.text
    assert "$39.00" in history.text
    assert "3" in history.text


def test_health_metrics_and_invalid_request_id() -> None:
    client, _ = make_client()

    health = client.get("/health")
    metrics = client.get("/metrics")
    invalid = client.get("/health", headers={"X-Request-ID": "invalid"})

    assert health.status_code == 200
    assert health.json()["status"] == "healthy"
    assert metrics.status_code == 200
    assert "http_requests_total" in metrics.text
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "VALIDATION_ERROR"


def test_menu_failure_has_user_friendly_page() -> None:
    client, _ = make_client(FailingGateway())

    response = client.get("/")

    assert response.status_code == 503
    assert "No pudimos servir esta página" in response.text
    assert "El menú no está disponible" in response.text


def test_history_survives_loyalty_outage_and_marks_balance_unavailable() -> None:
    client, gateway = make_client()
    client.post("/cart/items/1")
    client.post("/checkout")
    gateway.loyalty_available = False

    history = client.get("/orders")

    assert history.status_code == 200
    assert "Café americano" in history.text
    assert "$35.00" in history.text
    assert "Puntos acreditados" in history.text
    assert "Saldo no disponible" in history.text
    assert "None" not in history.text
    assert 'hx-trigger="every 15s"' not in history.text
    assert history.headers["cache-control"] == "private, no-store"


def test_pending_points_refresh_receipt_and_history_without_repeating_checkout() -> (
    None
):
    client, gateway = make_client()
    gateway.loyalty_available = False
    client.post("/cart/items/1")
    receipt = client.post("/checkout")
    order = gateway.orders[0]
    endpoint = f"/orders/{order['id']}/points"

    assert receipt.status_code == 200
    assert "Puntos pendientes" in receipt.text
    assert f'hx-get="{endpoint}"' in receipt.text
    assert 'hx-trigger="every 15s"' in receipt.text
    history = client.get("/orders")
    assert history.status_code == 200
    assert "Saldo no disponible" in history.text
    assert "Puntos pendientes" in history.text
    assert 'hx-get="/orders"' in history.text

    # Simula que el worker confirmó la acreditación en el servicio de pedidos.
    gateway.loyalty_available = True
    gateway.balance = 3
    order.update(loyalty_status="awarded", points_earned=3)
    points = client.get(endpoint, headers={"HX-Request": "true"})
    history = client.get("/orders", headers={"HX-Request": "true"})

    assert points.status_code == 200
    assert "+3 puntos" in points.text
    assert "Tu nuevo saldo es de 3 puntos" in points.text
    assert 'id="receipt-points"' in points.text
    assert 'hx-trigger="every 15s"' not in points.text
    assert "<!doctype" not in points.text
    assert history.status_code == 200
    assert "Puntos acreditados" in history.text
    assert "Saldo no disponible" not in history.text
    assert 'hx-trigger="every 15s"' not in history.text
    assert 'id="order-history"' in history.text
    assert "<!doctype" not in history.text
    assert "HX-Request" in history.headers["vary"]
    assert len(gateway.create_calls) == 1
    assert len(gateway.orders) == 1


def test_refresh_failure_preserves_existing_content() -> None:
    client, gateway = make_client()
    gateway.loyalty_available = False
    client.post("/cart/items/1")
    client.post("/checkout")
    gateway.orders_available = False
    points = client.get(f"/orders/{gateway.orders[0]['id']}/points")
    history = client.get("/orders", headers={"HX-Request": "true"})
    for response in (points, history):
        assert response.status_code == 503
        assert response.headers["HX-Reswap"] == "none"
        assert response.headers["cache-control"] == "private, no-store"
        assert response.text == ""
    assert client.get("/orders").status_code == 503
    assert len(gateway.create_calls) == 1


def test_receipt_points_are_restricted_to_customer_session() -> None:
    owner, gateway = make_client()
    owner.post("/cart/items/1")
    owner.post("/checkout")
    stranger, _ = make_client(gateway)
    response = stranger.get(f"/orders/{gateway.orders[0]['id']}/points")
    assert response.status_code == 404
    assert "Café americano" not in response.text
    assert "+3 puntos" not in response.text


def test_empty_history_handles_missing_balance_without_polling() -> None:
    client, gateway = make_client()
    gateway.loyalty_available = False
    response = client.get("/orders")
    assert response.status_code == 200
    assert "Todavía no tienes pedidos" in response.text
    assert "Saldo no disponible" in response.text
    assert 'hx-trigger="every 15s"' not in response.text
