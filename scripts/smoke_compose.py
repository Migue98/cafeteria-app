"""Prueba rápida del flujo menú -> pedido -> puntos en el Compose raíz."""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

SERVICES = {
    "frontend": "http://localhost:8000",
    "menu": "http://localhost:8001",
    "orders": "http://localhost:8002",
    "loyalty": "http://localhost:8003",
}


def request_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    body = json.dumps(payload).encode() if payload is not None else None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        response_body = exc.read().decode()
        try:
            parsed = json.loads(response_body)
        except json.JSONDecodeError:
            parsed = {"detail": response_body}
        return exc.code, parsed


def request_text(url: str) -> str:
    with urlopen(url, timeout=5) as response:
        return response.read().decode()


def wait_until_healthy(timeout_seconds: int = 60) -> None:
    deadline = time.monotonic() + timeout_seconds
    pending = set(SERVICES)
    while pending and time.monotonic() < deadline:
        for service in tuple(pending):
            try:
                status, payload = request_json("GET", f"{SERVICES[service]}/health")
            except (URLError, TimeoutError):
                continue
            if status == 200 and payload.get("status") == "healthy":
                pending.remove(service)
        if pending:
            time.sleep(1)
    if pending:
        raise RuntimeError(
            f"Servicios sin salud después de {timeout_seconds}s: {pending}"
        )


def main() -> None:
    wait_until_healthy()

    home = request_text(f"{SERVICES['frontend']}/")
    assert "Café americano" in home, "El frontend no mostró el menú"
    assert "Carrito" in home, "El frontend no mostró el carrito"

    menu_status, menu = request_json(
        "GET",
        f"{SERVICES['menu']}/api/v1/products?{urlencode({'available': 'true', 'limit': 20})}",
    )
    assert menu_status == 200, menu
    assert menu["total"] >= 20, menu

    customer_id = str(uuid4())
    idempotency_key = f"smoke-order-{uuid4()}"
    order_request = {
        "customer_id": customer_id,
        "items": [
            {"product_id": 1, "quantity": 2},
            {"product_id": 11, "quantity": 1},
        ],
    }
    headers = {"Idempotency-Key": idempotency_key}
    create_status, order = request_json(
        "POST",
        f"{SERVICES['orders']}/api/v1/orders",
        payload=order_request,
        headers=headers,
    )
    assert create_status == 201, order
    assert order["status"] == "confirmed", order
    assert order["loyalty_status"] == "awarded", order
    assert order["total_cents"] == 10900, order
    assert order["points_earned"] == 10, order

    replay_status, replay = request_json(
        "POST",
        f"{SERVICES['orders']}/api/v1/orders",
        payload=order_request,
        headers=headers,
    )
    assert replay_status == 200, replay
    assert replay["id"] == order["id"], replay
    assert replay["replayed"] is True, replay

    get_status, fetched = request_json(
        "GET", f"{SERVICES['orders']}/api/v1/orders/{order['id']}"
    )
    assert get_status == 200 and fetched["id"] == order["id"], fetched

    list_status, orders = request_json(
        "GET",
        f"{SERVICES['orders']}/api/v1/orders?{urlencode({'customer_id': customer_id})}",
    )
    assert list_status == 200 and orders["total"] == 1, orders

    balance_status, balance = request_json(
        "GET", f"{SERVICES['loyalty']}/api/v1/customers/{customer_id}/points"
    )
    assert balance_status == 200 and balance["balance"] == 10, balance

    expected_metrics = {
        "frontend": "http_requests_total",
        "menu": "http_requests_total",
        "orders": "cafe_orders_total",
        "loyalty": "cafe_loyalty_points_total",
    }
    for service, metric in expected_metrics.items():
        metrics = request_text(f"{SERVICES[service]}/metrics")
        assert metric in metrics, f"{metric} no apareció en {service}"

    print(
        json.dumps(
            {
                "status": "ok",
                "products": menu["total"],
                "order_id": order["id"],
                "order_total_cents": order["total_cents"],
                "points_earned": order["points_earned"],
                "balance": balance["balance"],
                "idempotent_replay": replay["replayed"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
