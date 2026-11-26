"""Interrupciones reales, recuperación y persistencia del proyecto aislado."""

from __future__ import annotations

import re
import subprocess
import time
from contextlib import contextmanager
from uuid import uuid4

import pytest

from .conftest import ApiClient, BrowserSession

pytestmark = pytest.mark.e2e


@pytest.fixture
def outage(api: ApiClient, compose_command):
    @contextmanager
    def interrupt(service: str, *, paused: bool = False):
        assert service in {"svc-menu", "svc-pedidos", "svc-lealtad", "postgres"}
        try:
            subprocess.run(
                [*compose_command, "pause" if paused else "stop", service],
                check=True,
                capture_output=True,
            )
            yield
        finally:
            subprocess.run(
                [*compose_command, "unpause" if paused else "start", service],
                check=True,
                capture_output=True,
            )
            api.wait_until_healthy(timeout_seconds=90)

    return interrupt


def purchase(api, customer_id, key):
    return api.json(
        "POST",
        f"{api.orders_url}/api/v1/orders",
        payload={
            "customer_id": customer_id,
            "items": [{"product_id": 1, "quantity": 2}],
        },
        headers={"Idempotency-Key": key},
        timeout=15,
    )


def assert_problem(result, code="DEPENDENCY_UNAVAILABLE"):
    assert result.status == 503
    assert result.headers["content-type"].startswith("application/problem+json")
    assert result.body["code"] == code
    assert len(result.body["trace_id"]) == 32
    assert "x-request-id" in result.headers
    assert "Traceback" not in str(result.body)


def assert_one_purchase(api, customer_id, *, points, loyalty_snapshot):
    listed = api.json(
        "GET", f"{api.orders_url}/api/v1/orders", query={"customer_id": customer_id}
    )
    assert listed.status == 200
    assert listed.body["total"] == 1
    snapshot = loyalty_snapshot(customer_id)
    assert snapshot["balance"] == points
    assert snapshot["movement_count"] == 1
    assert snapshot["movement_points"] == points


def finish_browser_purchase(api, browser, loyalty_snapshot):
    response = browser.request("POST", f"{api.frontend_url}/checkout")
    assert response.status == 200
    assert "Pedido confirmado" in response.body
    assert "$35.00" in response.body
    order_id = re.search(r'data-order-id="([0-9a-f-]{36})"', response.body)[1]
    order = api.json("GET", f"{api.orders_url}/api/v1/orders/{order_id}").body
    assert_one_purchase(
        api, order["customer_id"], points=3, loyalty_snapshot=loyalty_snapshot
    )


@pytest.mark.parametrize("paused", [False, True], ids=["stopped", "read-timeout"])
def test_menu_failure_rejects_purchase_and_recovers_without_losing_cart(
    api: ApiClient, browser: BrowserSession, outage, loyalty_snapshot, paused
):
    browser.request("POST", f"{api.frontend_url}/cart/items/1")
    previous_customer = str(uuid4())
    previous = purchase(api, previous_customer, f"before-menu-outage-{uuid4()}")
    assert previous.status == 201
    failed_customer, key = str(uuid4()), f"menu-outage-{uuid4()}"

    with outage("svc-menu", paused=paused):
        health = api.json("GET", f"{api.frontend_url}/health", timeout=20)
        assert health.status == 200
        assert health.body["status"] == "degraded"
        assert health.body["dependencies"]["menu"] == "down"
        assert_problem(api.json("GET", f"{api.orders_url}/health", timeout=10))
        started = time.monotonic()
        assert_problem(purchase(api, failed_customer, key))
        assert time.monotonic() - started < 12
        saved = api.json("GET", f"{api.orders_url}/api/v1/orders/{previous.body['id']}")
        assert saved.status == 200
        assert saved.body["id"] == previous.body["id"]
        checkout = browser.request("POST", f"{api.frontend_url}/checkout")
        assert checkout.status == 503
        assert "No pudimos servir esta página" in checkout.body
        assert "Traceback" not in checkout.body
        assert api.text(f"{api.orders_url}/metrics").status == 200

    empty = api.json(
        "GET", f"{api.orders_url}/api/v1/orders", query={"customer_id": failed_customer}
    )
    assert empty.body["total"] == 0
    assert loyalty_snapshot(failed_customer)["movement_count"] == 0
    assert purchase(api, failed_customer, key).status == 201
    assert_one_purchase(
        api, failed_customer, points=7, loyalty_snapshot=loyalty_snapshot
    )
    finish_browser_purchase(api, browser, loyalty_snapshot)


def test_orders_outage_keeps_menu_available_and_preserves_checkout_attempt(
    api: ApiClient, browser: BrowserSession, outage, loyalty_snapshot
):
    browser.request("POST", f"{api.frontend_url}/cart/items/1")
    with outage("svc-pedidos"):
        home = browser.request("GET", f"{api.frontend_url}/")
        assert home.status == 200
        assert "Café americano" in home.body
        health = api.json("GET", f"{api.frontend_url}/health")
        assert health.body["status"] == "degraded"
        assert health.body["dependencies"]["orders"] == "down"
        history = browser.request("GET", f"{api.frontend_url}/orders")
        assert history.status == 503
        assert "No pudimos servir esta página" in history.body
        fragment = browser.request(
            "GET", f"{api.frontend_url}/orders", headers={"HX-Request": "true"}
        )
        assert fragment.status == 503
        assert fragment.headers["hx-reswap"] == "none"
        assert fragment.body == ""
        checkout = browser.request("POST", f"{api.frontend_url}/checkout")
        assert checkout.status == 503
        assert "Un servicio no está disponible temporalmente" in checkout.body
        assert "Café americano" in checkout.body

    finish_browser_purchase(api, browser, loyalty_snapshot)


def test_postgres_outage_reports_503_and_restores_data_without_restart_of_apps(
    api: ApiClient, browser: BrowserSession, outage, loyalty_snapshot
):
    browser.request("POST", f"{api.frontend_url}/cart/items/1")
    customer_id = str(uuid4())
    created = purchase(api, customer_id, f"before-db-outage-{uuid4()}")
    assert created.status == 201
    failed_customer, key = str(uuid4()), f"database-outage-{uuid4()}"
    with outage("postgres"):
        for url in (api.menu_url, api.orders_url, api.loyalty_url):
            assert_problem(api.json("GET", f"{url}/health", timeout=10))
            assert api.text(f"{url}/metrics").status == 200
        assert_problem(
            api.json("GET", f"{api.orders_url}/api/v1/orders/{created.body['id']}")
        )
        assert_problem(purchase(api, failed_customer, key))
        health = api.json("GET", f"{api.frontend_url}/health", timeout=20)
        assert health.status == 200
        assert health.body["status"] == "degraded"
        assert set(health.body["dependencies"].values()) == {"down"}
        checkout = browser.request("POST", f"{api.frontend_url}/checkout")
        assert checkout.status == 503
        assert "No pudimos servir esta página" in checkout.body

    restored = api.json("GET", f"{api.orders_url}/api/v1/orders/{created.body['id']}")
    assert restored.status == 200
    assert restored.body["id"] == created.body["id"]
    assert_one_purchase(api, customer_id, points=7, loyalty_snapshot=loyalty_snapshot)
    empty = api.json(
        "GET", f"{api.orders_url}/api/v1/orders", query={"customer_id": failed_customer}
    )
    assert empty.body["total"] == 0
    assert purchase(api, failed_customer, key).status == 201
    assert_one_purchase(
        api, failed_customer, points=7, loyalty_snapshot=loyalty_snapshot
    )
    finish_browser_purchase(api, browser, loyalty_snapshot)


def test_loyalty_read_timeout_keeps_order_and_recovers_exactly_once(
    api: ApiClient, outage, loyalty_snapshot
):
    customer_id = str(uuid4())
    with outage("svc-lealtad", paused=True):
        started = time.monotonic()
        created = purchase(api, customer_id, f"loyalty-timeout-{uuid4()}")
        assert time.monotonic() - started < 12
        assert created.status == 201
        assert created.body["loyalty_status"] == "pending"
        assert created.body["points_earned"] is None

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        order = api.json("GET", f"{api.orders_url}/api/v1/orders/{created.body['id']}")
        if order.body.get("loyalty_status") == "awarded":
            break
        time.sleep(0.5)
    assert order.status == 200
    assert order.body["loyalty_status"] == "awarded"
    assert_one_purchase(api, customer_id, points=7, loyalty_snapshot=loyalty_snapshot)
