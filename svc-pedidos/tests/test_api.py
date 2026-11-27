from __future__ import annotations

import asyncio
import threading
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from app.clients import DependencyUnavailable, HttpLoyaltyClient, HttpMenuClient, LoyaltyUnavailable
from app.loyalty_retry import loyalty_retry_loop, retry_pending_loyalty
from app.main import create_app
from app.models import MenuProduct, Order
from app.repository import StoredOrder

CUSTOMER_ID = "11111111-1111-4111-8111-111111111111"


class FakeRepository:
    def __init__(self) -> None:
        self.orders: dict[UUID, Order] = {}
        self.idempotency: dict[str, tuple[UUID, str]] = {}

    def health(self) -> float:
        return 1.2

    def get_by_idempotency_key(self, key: str):
        stored = self.idempotency.get(key)
        if stored is None:
            return None
        order_id, request_hash = stored
        return StoredOrder(order=self.orders[order_id], request_hash=request_hash)

    def save(self, order: Order, *, idempotency_key: str, request_hash: str) -> bool:
        if idempotency_key in self.idempotency:
            return False
        self.orders[order.id] = order
        self.idempotency[idempotency_key] = (order.id, request_hash)
        return True

    def get(self, order_id: UUID):
        return self.orders.get(order_id)

    def list_for_customer(self, customer_id: UUID, *, limit: int, offset: int):
        orders = [order for order in self.orders.values() if order.customer_id == customer_id]
        orders.sort(key=lambda order: order.created_at, reverse=True)
        return orders[offset : offset + limit], len(orders)

    def mark_loyalty_awarded(self, order_id: UUID, points_earned: int) -> Order:
        order = self.orders[order_id].model_copy(
            update={"loyalty_status": "awarded", "points_earned": points_earned}
        )
        self.orders[order_id] = order
        return order

    def list_pending_loyalty(self, *, limit: int):
        orders = [order for order in self.orders.values() if order.loyalty_status == "pending"]
        orders.sort(key=lambda order: (order.created_at, order.id))
        return orders[:limit], len(orders)


class FakeMenu:
    def __init__(self, *, health_fails: bool = False) -> None:
        self.health_fails = health_fails
        self.products = {
            1: MenuProduct(
                id=1,
                sku="CAFE-AMERICANO",
                name="Café americano",
                price_cents=3500,
                currency="MXN",
                available=True,
            ),
            2: MenuProduct(
                id=2,
                sku="CROISSANT",
                name="Croissant",
                price_cents=3900,
                currency="MXN",
                available=True,
            ),
            3: MenuProduct(
                id=3,
                sku="AGOTADO",
                name="Producto agotado",
                price_cents=1000,
                currency="MXN",
                available=False,
            ),
        }

    def health(self, *, request_id: str, traceparent: str) -> float:
        if self.health_fails:
            raise DependencyUnavailable("svc-menu no está disponible")
        return 2.3

    def get_product(self, product_id: int, *, request_id: str, traceparent: str):
        return self.products.get(product_id)


class FakeLoyalty:
    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails
        self.award_calls = 0

    def health(self, *, request_id: str, traceparent: str) -> float:
        if self.fails:
            raise LoyaltyUnavailable("svc-lealtad no está disponible")
        return 3.4

    def award(self, order: Order, *, request_id: str, traceparent: str) -> int:
        self.award_calls += 1
        if self.fails:
            raise LoyaltyUnavailable("svc-lealtad no está disponible")
        return order.total_cents // 1000


def make_client(
    *,
    repository: FakeRepository | None = None,
    menu: FakeMenu | None = None,
    loyalty: FakeLoyalty | None = None,
) -> tuple[TestClient, FakeRepository, FakeLoyalty]:
    repository = repository or FakeRepository()
    loyalty = loyalty or FakeLoyalty()
    app = create_app(repository, menu or FakeMenu(), loyalty)
    return TestClient(app), repository, loyalty


def order_payload(*, quantity: int = 2, product_id: int = 1) -> dict:
    return {
        "customer_id": CUSTOMER_ID,
        "items": [{"product_id": product_id, "quantity": quantity}],
    }


def create_order(client: TestClient, key: str = "test-order-001", payload: dict | None = None):
    return client.post(
        "/api/v1/orders",
        headers={"Idempotency-Key": key},
        json=payload or order_payload(),
    )


def test_health_reports_all_dependencies() -> None:
    client, _, _ = make_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["dependencies"] == {
        "postgres": {"status": "up", "critical": True, "latency_ms": 1.2},
        "menu": {"status": "up", "critical": True, "latency_ms": 2.3},
        "loyalty": {"status": "up", "critical": False, "latency_ms": 3.4},
    }


def test_health_is_degraded_when_loyalty_is_down() -> None:
    client, _, _ = make_client(loyalty=FakeLoyalty(fails=True))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["dependencies"]["loyalty"] == {
        "status": "down",
        "critical": False,
        "latency_ms": None,
    }


def test_health_fails_when_menu_is_down() -> None:
    client, _, _ = make_client(menu=FakeMenu(health_fails=True))

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["code"] == "DEPENDENCY_UNAVAILABLE"


def test_create_order_uses_menu_prices_and_awards_points() -> None:
    client, repository, loyalty = make_client()
    payload = {
        "customer_id": CUSTOMER_ID,
        "items": [
            {"product_id": 1, "quantity": 2},
            {"product_id": 2, "quantity": 1},
        ],
    }

    response = create_order(client, payload=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["subtotal_cents"] == 10900
    assert body["total_cents"] == 10900
    assert body["loyalty_status"] == "awarded"
    assert body["points_earned"] == 10
    assert len(repository.orders) == 1
    assert loyalty.award_calls == 1


def test_loyalty_failure_keeps_confirmed_order_pending() -> None:
    client, repository, _ = make_client(loyalty=FakeLoyalty(fails=True))

    response = create_order(client)

    assert response.status_code == 201
    assert response.json()["status"] == "confirmed"
    assert response.json()["loyalty_status"] == "pending"
    assert response.json()["points_earned"] is None
    assert len(repository.orders) == 1


@pytest.mark.parametrize("bad_points", [None, -1, "7", 7.5, True])
def test_invalid_loyalty_response_keeps_order_pending(monkeypatch, bad_points) -> None:
    def broken_award(*args, **kwargs):
        payload = kwargs["json"]
        return httpx.Response(
            200,
            json={
                "order_id": payload["order_id"],
                "customer_id": payload["customer_id"],
                "points_earned": bad_points,
            },
        )

    loyalty = HttpLoyaltyClient("http://loyalty", 1)
    monkeypatch.setattr(loyalty._client, "post", broken_award)
    client, repository, _ = make_client(loyalty=loyalty)
    response = create_order(client)
    assert response.status_code == 201
    assert response.json()["loyalty_status"] == "pending"
    assert response.json()["points_earned"] is None
    assert len(repository.orders) == 1


def test_malformed_menu_response_returns_503_without_saving_order(monkeypatch) -> None:
    menu = HttpMenuClient("http://menu", 1)
    monkeypatch.setattr(
        menu._client, "get", lambda *args, **kwargs: httpx.Response(200, text="bad-json")
    )
    client, repository, _ = make_client(menu=menu)
    response = create_order(client)
    assert response.status_code == 503
    assert response.json()["code"] == "DEPENDENCY_UNAVAILABLE"
    assert repository.orders == {}


@pytest.mark.parametrize(
    "field,value", [("id", 99), ("price_cents", "3500"), ("available", "true")]
)
def test_invalid_menu_product_is_not_used_to_create_order(monkeypatch, field, value):
    product = FakeMenu().products[1].model_dump()
    product[field] = value
    menu = HttpMenuClient("http://menu", 1)
    monkeypatch.setattr(menu._client, "get", lambda *a, **kw: httpx.Response(200, json=product))
    client, repository, _ = make_client(menu=menu)
    assert create_order(client).status_code == 503
    assert repository.orders == {}


@pytest.mark.parametrize("field", ["order_id", "customer_id"])
def test_loyalty_award_for_another_identity_keeps_order_pending(monkeypatch, field):
    def wrong_award(*args, **kwargs):
        payload = kwargs["json"]
        result = {
            "order_id": payload["order_id"],
            "customer_id": payload["customer_id"],
            "points_earned": 7,
        }
        result[field] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        return httpx.Response(200, json=result)

    loyalty = HttpLoyaltyClient("http://loyalty", 1)
    monkeypatch.setattr(loyalty._client, "post", wrong_award)
    client, repository, _ = make_client(loyalty=loyalty)
    response = create_order(client)
    assert response.status_code == 201
    assert response.json()["loyalty_status"] == "pending"
    assert len(repository.orders) == 1


@pytest.mark.parametrize("points", [0, 7])
def test_valid_integer_loyalty_response_is_accepted(monkeypatch, points):
    def valid_award(*args, **kwargs):
        payload = kwargs["json"]
        return httpx.Response(
            200,
            json={
                "order_id": payload["order_id"],
                "customer_id": payload["customer_id"],
                "points_earned": points,
            },
        )

    loyalty = HttpLoyaltyClient("http://loyalty", 1)
    monkeypatch.setattr(loyalty._client, "post", valid_award)
    client, _, _ = make_client(loyalty=loyalty)
    response = create_order(client)
    assert response.status_code == 201
    assert response.json()["loyalty_status"] == "awarded"
    assert response.json()["points_earned"] == points


def test_same_idempotency_key_replays_without_duplicate() -> None:
    client, repository, loyalty = make_client()

    first = create_order(client)
    second = create_order(client)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["replayed"] is True
    assert len(repository.orders) == 1
    assert loyalty.award_calls == 1


def test_reused_idempotency_key_with_other_body_conflicts() -> None:
    client, _, _ = make_client()
    create_order(client)

    response = create_order(client, payload=order_payload(quantity=3))

    assert response.status_code == 409
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_duplicate_products_are_rejected() -> None:
    client, _, _ = make_client()
    payload = {
        "customer_id": CUSTOMER_ID,
        "items": [
            {"product_id": 1, "quantity": 1},
            {"product_id": 1, "quantity": 2},
        ],
    }

    response = create_order(client, payload=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_unavailable_product_conflicts() -> None:
    client, _, _ = make_client()

    response = create_order(client, payload=order_payload(product_id=3))

    assert response.status_code == 409
    assert response.json()["code"] == "PRODUCT_UNAVAILABLE"


def test_get_and_list_orders() -> None:
    client, _, _ = make_client()
    created = create_order(client).json()

    get_response = client.get(f"/api/v1/orders/{created['id']}")
    list_response = client.get("/api/v1/orders", params={"customer_id": CUSTOMER_ID})

    assert get_response.status_code == 200
    assert get_response.json()["id"] == created["id"]
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["items"][0]["id"] == created["id"]


def test_missing_order_uses_problem_json() -> None:
    client, _, _ = make_client()

    response = client.get("/api/v1/orders/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "ORDER_NOT_FOUND"


def test_retry_awards_pending_points() -> None:
    loyalty = FakeLoyalty(fails=True)
    client, _, _ = make_client(loyalty=loyalty)
    created = create_order(client).json()
    loyalty.fails = False

    response = client.post(f"/api/v1/orders/{created['id']}/loyalty/retry")

    assert response.status_code == 200
    assert response.json()["loyalty_status"] == "awarded"
    assert response.json()["points_earned"] == 7


def test_retry_returns_503_while_loyalty_is_down() -> None:
    client, _, _ = make_client(loyalty=FakeLoyalty(fails=True))
    created = create_order(client).json()

    response = client.post(f"/api/v1/orders/{created['id']}/loyalty/retry")

    assert response.status_code == 503
    assert response.json()["code"] == "LOYALTY_UNAVAILABLE"


def test_automatic_retry_awards_pending_orders_in_a_batch() -> None:
    loyalty = FakeLoyalty(fails=True)
    client, repository, _ = make_client(loyalty=loyalty)
    first = create_order(client, key="pending-order-001").json()
    second = create_order(client, key="pending-order-002").json()
    loyalty.fails = False

    result = retry_pending_loyalty(repository, loyalty, batch_size=100)

    assert result.pending_total == 2
    assert result.attempted == 2
    assert result.awarded == 2
    assert result.failed == 0
    assert repository.orders[UUID(first["id"])].loyalty_status == "awarded"
    assert repository.orders[UUID(second["id"])].loyalty_status == "awarded"


def test_automatic_retry_keeps_order_pending_when_loyalty_is_down() -> None:
    loyalty = FakeLoyalty(fails=True)
    client, repository, _ = make_client(loyalty=loyalty)
    created = create_order(client, key="pending-order-003").json()

    result = retry_pending_loyalty(repository, loyalty, batch_size=100)

    assert result.pending_total == 1
    assert result.attempted == 1
    assert result.awarded == 0
    assert result.failed == 1
    assert repository.orders[UUID(created["id"])].loyalty_status == "pending"


@pytest.mark.parametrize("still_down", [False, True], ids=["recovered", "failed"])
def test_retry_exports_its_own_trace_and_correlated_outcome(still_down, caplog):
    import json

    loyalty = FakeLoyalty(fails=True)
    client, repository, _ = make_client(loyalty=loyalty)
    order = create_order(client).json()
    runtime = client.app.state.telemetry
    exporter = InMemorySpanExporter()
    runtime.provider.add_span_processor(SimpleSpanProcessor(exporter))
    loyalty.fails = still_down
    caplog.clear()
    try:
        result = retry_pending_loyalty(repository, loyalty, batch_size=100, tracer=runtime.tracer)
        spans = exporter.get_finished_spans()
        batch = next(span for span in spans if span.name == "loyalty.retry_batch")
        retry = next(span for span in spans if span.name == "loyalty.retry")
        assert batch.parent is None
        assert retry.parent.span_id == batch.context.span_id
        assert retry.context.trace_id == batch.context.trace_id
        assert result.failed == int(still_down)
        assert result.awarded == int(not still_down)
        assert retry.status.status_code == (StatusCode.ERROR if still_down else StatusCode.UNSET)
        event = next(
            json.loads(record.getMessage())
            for record in caplog.records
            if record.getMessage().startswith("{")
        )
        assert event["order_id"] == order["id"]
        assert event["trace_id"] == f"{retry.context.trace_id:032x}"
        assert event["span_id"] == f"{retry.context.span_id:016x}"
    finally:
        runtime.shutdown()


def test_worker_shutdown_waits_for_the_active_thread_before_closing_resources():
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    class SlowRepository(FakeRepository):
        def list_pending_loyalty(self, *, limit):
            started.set()
            release.wait(timeout=5)
            finished.set()
            return [], 0

    async def run():
        task = asyncio.create_task(
            loyalty_retry_loop(
                SlowRepository(), FakeLoyalty(), interval_seconds=900, batch_size=100
            )
        )
        try:
            assert await asyncio.to_thread(started.wait, 5)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
        finally:
            release.set()
            if not started.is_set():
                task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert finished.is_set()

    asyncio.run(run())


def test_idempotency_key_is_required() -> None:
    client, _, _ = make_client()

    response = client.post("/api/v1/orders", json=order_payload())

    assert response.status_code == 422


def test_metrics_and_openapi_paths_are_available() -> None:
    client, _, _ = make_client()
    create_order(client)

    metrics = client.get("/metrics")
    paths = client.get("/openapi.json").json()["paths"]

    assert metrics.status_code == 200
    assert "cafe_orders_total" in metrics.text
    assert "cafe_order_value_cents_total" in metrics.text
    assert "cafe_loyalty_pending_orders" in metrics.text
    assert "cafe_loyalty_retry_attempts_total" in metrics.text
    assert {
        "/health",
        "/metrics",
        "/api/v1/orders",
        "/api/v1/orders/{order_id}",
        "/api/v1/orders/{order_id}/loyalty/retry",
    } <= set(paths)
