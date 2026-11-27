"""Pruebas end-to-end del flujo menú -> pedido -> lealtad -> persistencia."""

from __future__ import annotations

import json
import re
import subprocess
import time
from uuid import uuid4

import pytest

from .conftest import ApiClient, BrowserSession

pytestmark = pytest.mark.e2e


def order_payload(customer_id: str, *, product_id: int = 1, quantity: int = 2) -> dict:
    return {
        "customer_id": customer_id,
        "items": [{"product_id": product_id, "quantity": quantity}],
    }


def create_order(api: ApiClient, payload: dict, key: str | None = None):
    return api.json(
        "POST",
        f"{api.orders_url}/api/v1/orders",
        payload=payload,
        headers={"Idempotency-Key": key or f"e2e-order-{uuid4()}"},
    )


def test_health_and_request_correlation(api: ApiClient) -> None:
    request_id = str(uuid4())
    expected_services = {
        api.frontend_url: "frontend",
        api.menu_url: "svc-menu",
        api.orders_url: "svc-pedidos",
        api.loyalty_url: "svc-lealtad",
    }

    for url, service in expected_services.items():
        result = api.json("GET", f"{url}/health", headers={"X-Request-ID": request_id})
        assert result.status == 200
        assert result.body["service"] == service
        assert result.body["status"] == "healthy"
        assert result.headers["x-request-id"] == request_id


def test_complete_purchase_uses_menu_prices_and_awards_points(api: ApiClient) -> None:
    menu = api.json(
        "GET",
        f"{api.menu_url}/api/v1/products",
        query={"available": "true", "limit": 20},
    )
    assert menu.status == 200
    assert menu.body["total"] == 20

    customer_id = str(uuid4())
    payload = {
        "customer_id": customer_id,
        "items": [
            {"product_id": 1, "quantity": 2},
            {"product_id": 11, "quantity": 1},
        ],
    }
    created = create_order(api, payload)

    assert created.status == 201
    assert created.body["status"] == "confirmed"
    assert created.body["loyalty_status"] == "awarded"
    assert created.body["subtotal_cents"] == 10900
    assert created.body["total_cents"] == 10900
    assert created.body["points_earned"] == 10
    assert [item["unit_price_cents"] for item in created.body["items"]] == [3500, 3900]

    fetched = api.json("GET", f"{api.orders_url}/api/v1/orders/{created.body['id']}")
    listed = api.json(
        "GET",
        f"{api.orders_url}/api/v1/orders",
        query={"customer_id": customer_id},
    )
    balance = api.json("GET", f"{api.loyalty_url}/api/v1/customers/{customer_id}/points")
    assert fetched.status == 200 and fetched.body["id"] == created.body["id"]
    assert listed.status == 200 and listed.body["total"] == 1
    assert balance.status == 200 and balance.body["balance"] == 10


def test_browser_completes_purchase_and_opens_history(
    api: ApiClient, browser: BrowserSession
) -> None:
    home = browser.request("GET", f"{api.frontend_url}/")
    assert home.status == 200
    assert "Café americano" in home.body
    assert "Croissant" in home.body

    browser.request("POST", f"{api.frontend_url}/cart/items/1")
    browser.request("POST", f"{api.frontend_url}/cart/items/1")
    browser.request("POST", f"{api.frontend_url}/cart/items/11")
    receipt = browser.request("POST", f"{api.frontend_url}/checkout")

    assert receipt.status == 200
    assert "Pedido confirmado" in receipt.body
    assert "$109.00" in receipt.body
    assert "+10 puntos" in receipt.body

    history = browser.request("GET", f"{api.frontend_url}/orders")
    assert history.status == 200
    assert "Café americano" in history.body
    assert "Croissant" in history.body


def test_checkout_trace_links_all_four_services(
    api: ApiClient, browser: BrowserSession, compose_command: list[str]
) -> None:
    browser.request("POST", f"{api.frontend_url}/cart/items/1")
    request_id = str(uuid4())
    trace_id = uuid4().hex
    parent_span = uuid4().hex[:16]
    receipt = browser.request(
        "POST",
        f"{api.frontend_url}/checkout",
        headers={
            "X-Request-ID": request_id,
            "traceparent": f"00-{trace_id}-{parent_span}-01",
        },
    )
    assert receipt.status == 200
    assert receipt.headers["x-request-id"] == request_id
    frontend_span = receipt.headers["traceparent"].split("-")[2]

    events = []
    spans = {}
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        logs = subprocess.run(
            [
                *compose_command,
                "logs",
                "--no-color",
                "--no-log-prefix",
                "frontend",
                "svc-menu",
                "svc-pedidos",
                "svc-lealtad",
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        events = []
        spans = {}
        for line in logs.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("context", {}).get("trace_id") == f"0x{trace_id}":
                spans[event["context"]["span_id"][2:]] = event
            if event.get("trace_id") == trace_id and event.get("message") == "request_completed":
                events.append(event)
        if (
            {event["service"] for event in events}
            == {
                "frontend",
                "svc-menu",
                "svc-pedidos",
                "svc-lealtad",
            }
            and {
                span["resource"]["attributes"]["service.name"]
                for span in spans.values()
                if span["attributes"].get("db.system") == "postgresql"
                or span["attributes"].get("db.system.name") == "postgresql"
            }
            == {
                "svc-menu",
                "svc-pedidos",
                "svc-lealtad",
            }
            and all(event["span_id"] in spans for event in events)
        ):
            break
        time.sleep(0.2)

    by_service = {
        service: [event for event in events if event["service"] == service]
        for service in ("frontend", "svc-menu", "svc-pedidos", "svc-lealtad")
    }
    assert all(by_service.values()), events
    frontend_event = by_service["frontend"][0]
    order_event = next(
        event for event in by_service["svc-pedidos"] if event["route"] == "/api/v1/orders"
    )
    assert frontend_event["span_id"] == frontend_span
    assert frontend_event["parent_span_id"] == parent_span

    def assert_http_hop(server_event, parent_server_id):
        server_span = spans[server_event["span_id"]]
        client_span = spans[server_event["parent_span_id"]]
        assert server_span["kind"] == "SpanKind.SERVER"
        assert server_span["parent_id"] == client_span["context"]["span_id"]
        assert client_span["kind"] == "SpanKind.CLIENT"
        assert client_span["parent_id"] == f"0x{parent_server_id}"
        assert server_span["end_time"] > server_span["start_time"]

    assert_http_hop(order_event, frontend_span)
    menu_event = next(
        event
        for event in by_service["svc-menu"]
        if event["route"] == "/api/v1/products/{product_id}"
    )
    assert_http_hop(menu_event, order_event["span_id"])
    award = next(
        event for event in by_service["svc-lealtad"] if event["route"] == "/api/v1/points/earn"
    )
    assert_http_hop(award, order_event["span_id"])
    for server_event in [order_event, menu_event, award]:
        sql_spans = [
            span
            for span in spans.values()
            if span["parent_id"] == f"0x{server_event['span_id']}"
            and (
                span["attributes"].get("db.system") == "postgresql"
                or span["attributes"].get("db.system.name") == "postgresql"
            )
        ]
        assert sql_spans, server_event
        assert all(span["kind"] == "SpanKind.CLIENT" for span in sql_spans)
        assert all(span["end_time"] > span["start_time"] for span in sql_spans)
        assert all(
            span["resource"]["attributes"]["service.name"] == server_event["service"]
            for span in sql_spans
        )
    assert len({event["span_id"] for event in events}) == len(events)
    for event in events:
        assert event["request_id"] == request_id
        assert event["timestamp"]
        assert event["level"] == "INFO"
        assert event["duration_ms"] >= 0
        assert event["status_code"] < 400


def test_order_idempotency_does_not_duplicate_order_or_points(api: ApiClient) -> None:
    customer_id = str(uuid4())
    payload = order_payload(customer_id)
    key = f"e2e-idempotency-{uuid4()}"

    first = create_order(api, payload, key)
    replay = create_order(api, payload, key)
    listed = api.json(
        "GET",
        f"{api.orders_url}/api/v1/orders",
        query={"customer_id": customer_id},
    )
    balance = api.json("GET", f"{api.loyalty_url}/api/v1/customers/{customer_id}/points")

    assert first.status == 201
    assert replay.status == 200
    assert replay.body["id"] == first.body["id"]
    assert replay.body["replayed"] is True
    assert listed.body["total"] == 1
    assert balance.body["balance"] == 7


def test_reused_idempotency_key_with_different_body_conflicts(api: ApiClient) -> None:
    customer_id = str(uuid4())
    key = f"e2e-conflict-{uuid4()}"
    first = create_order(api, order_payload(customer_id, quantity=1), key)
    conflict = create_order(api, order_payload(customer_id, quantity=2), key)

    assert first.status == 201
    assert conflict.status == 409
    assert conflict.headers["content-type"].startswith("application/problem+json")
    assert conflict.body["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_validation_rejects_duplicate_products(api: ApiClient) -> None:
    payload = {
        "customer_id": str(uuid4()),
        "items": [
            {"product_id": 1, "quantity": 1},
            {"product_id": 1, "quantity": 2},
        ],
    }
    result = create_order(api, payload)

    assert result.status == 422
    assert result.body["code"] == "VALIDATION_ERROR"
    assert result.headers["content-type"].startswith("application/problem+json")


def test_missing_and_unavailable_products_are_rejected(
    api: ApiClient, set_product_availability
) -> None:
    missing = create_order(api, order_payload(str(uuid4()), product_id=999))
    assert missing.status == 409
    assert missing.body["code"] == "PRODUCT_UNAVAILABLE"

    set_product_availability(20, False)
    unavailable = create_order(api, order_payload(str(uuid4()), product_id=20))
    assert unavailable.status == 409
    assert unavailable.body["code"] == "PRODUCT_UNAVAILABLE"


def test_metrics_expose_business_and_http_signals(api: ApiClient) -> None:
    create_order(api, order_payload(str(uuid4()), quantity=1))
    expected = {
        api.frontend_url: ("http_requests_total",),
        api.menu_url: ("http_requests_total",),
        api.orders_url: (
            "http_requests_total",
            "cafe_orders_total",
            "cafe_order_value_cents_total",
            "cafe_loyalty_pending_orders",
            "cafe_loyalty_retry_attempts_total",
        ),
        api.loyalty_url: (
            "http_requests_total",
            "cafe_loyalty_points_total",
            "cafe_loyalty_awards_total",
        ),
    }

    for url, metrics in expected.items():
        response = api.text(f"{url}/metrics")
        assert response.status == 200
        for metric in metrics:
            assert metric in response.body


def test_pending_loyalty_recovers_automatically(api: ApiClient, compose_command: list[str]) -> None:
    customer_id = str(uuid4())
    subprocess.run(
        [*compose_command, "stop", "svc-lealtad"],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        created = create_order(api, order_payload(customer_id))
        assert created.status == 201
        assert created.body["loyalty_status"] == "pending"
    finally:
        subprocess.run(
            [*compose_command, "start", "svc-lealtad"],
            check=True,
            capture_output=True,
            text=True,
        )

    api.wait_until_healthy(timeout_seconds=90)
    deadline = time.monotonic() + 20
    fetched = None
    while time.monotonic() < deadline:
        fetched = api.json("GET", f"{api.orders_url}/api/v1/orders/{created.body['id']}")
        if fetched.status == 200 and fetched.body["loyalty_status"] == "awarded":
            break
        time.sleep(0.5)

    assert fetched is not None
    assert fetched.status == 200
    assert fetched.body["loyalty_status"] == "awarded"
    assert fetched.body["points_earned"] == 7
    balance = api.json("GET", f"{api.loyalty_url}/api/v1/customers/{customer_id}/points")
    assert balance.status == 200
    assert balance.body["balance"] == 7


def test_browser_history_survives_loyalty_outage_and_refreshes(
    api: ApiClient, browser: BrowserSession, compose_command: list[str]
) -> None:
    browser.request("POST", f"{api.frontend_url}/cart/items/1")
    browser.request("POST", f"{api.frontend_url}/cart/items/1")
    subprocess.run(
        [*compose_command, "stop", "svc-lealtad"],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        receipt = browser.request("POST", f"{api.frontend_url}/checkout")
        assert receipt.status == 200
        assert "Puntos pendientes" in receipt.body
        assert 'hx-trigger="every 15s"' in receipt.body
        order_id = re.search(r'data-order-id="([0-9a-f-]{36})"', receipt.body)[1]
        history = browser.request("GET", f"{api.frontend_url}/orders")
        assert history.status == 200
        assert "Café americano" in history.body
        assert "Saldo no disponible" in history.body
        assert "Puntos pendientes" in history.body
        assert 'hx-get="/orders"' in history.body
    finally:
        subprocess.run(
            [*compose_command, "start", "svc-lealtad"],
            check=True,
            capture_output=True,
            text=True,
        )

    api.wait_until_healthy(timeout_seconds=90)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        refreshed = browser.request(
            "GET",
            f"{api.frontend_url}/orders/{order_id}/points",
            headers={"HX-Request": "true"},
        )
        if "+7 puntos" in refreshed.body:
            break
        time.sleep(0.5)
    assert refreshed.status == 200
    assert "+7 puntos" in refreshed.body
    assert 'hx-trigger="every 15s"' not in refreshed.body
    history = browser.request("GET", f"{api.frontend_url}/orders", headers={"HX-Request": "true"})
    assert "Puntos acreditados" in history.body
    assert "Saldo no disponible" not in history.body
    assert 'hx-trigger="every 15s"' not in history.body
    assert "<!doctype" not in history.body

    order = api.json("GET", f"{api.orders_url}/api/v1/orders/{order_id}").body
    listed = api.json(
        "GET",
        f"{api.orders_url}/api/v1/orders",
        query={"customer_id": order["customer_id"]},
    )
    balance = api.json("GET", f"{api.loyalty_url}/api/v1/customers/{order['customer_id']}/points")
    assert listed.body["total"] == 1
    assert balance.body["balance"] == 7


def test_data_survives_postgres_restart(api: ApiClient, compose_command: list[str]) -> None:
    customer_id = str(uuid4())
    created = create_order(api, order_payload(customer_id, quantity=1))
    assert created.status == 201
    order_id = created.body["id"]

    subprocess.run(
        [*compose_command, "restart", "postgres"],
        check=True,
        capture_output=True,
        text=True,
    )
    api.wait_until_healthy(timeout_seconds=90)

    fetched = api.json("GET", f"{api.orders_url}/api/v1/orders/{order_id}")
    balance = api.json("GET", f"{api.loyalty_url}/api/v1/customers/{customer_id}/points")
    assert fetched.status == 200 and fetched.body["id"] == order_id
    assert balance.status == 200 and balance.body["balance"] == 3
