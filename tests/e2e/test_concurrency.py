"""Carreras reales sobre HTTP y PostgreSQL, con arranque sincronizado."""

from __future__ import annotations

import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest

from .conftest import ApiClient, BrowserSession

pytestmark = pytest.mark.e2e


def parallel_calls(calls):
    gate = Barrier(len(calls))

    def invoke(call):
        gate.wait(timeout=15)
        return call()

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return list(pool.map(invoke, calls))


def purchase(api, customer_id, key, quantity=2):
    return api.json(
        "POST",
        f"{api.orders_url}/api/v1/orders",
        payload={
            "customer_id": customer_id,
            "items": [{"product_id": 1, "quantity": quantity}],
        },
        headers={"Idempotency-Key": key},
        timeout=15,
    )


def award(api, customer_id, order_id, key, amount=7000):
    return api.json(
        "POST",
        f"{api.loyalty_url}/api/v1/points/earn",
        payload={
            "customer_id": customer_id,
            "order_id": order_id,
            "amount_cents": amount,
            "currency": "MXN",
        },
        headers={"Idempotency-Key": key},
        timeout=15,
    )


def assert_ledger(snapshot, *, orders, points):
    assert snapshot["account_count"] == 1
    assert snapshot["balance"] == points
    assert snapshot["movement_count"] == orders
    assert snapshot["distinct_orders"] == orders
    assert snapshot["movement_points"] == points


def test_simultaneous_order_replays_create_one_order_and_award(
    api: ApiClient, loyalty_snapshot
):
    customer_id, key = str(uuid4()), f"parallel-order-{uuid4()}"
    results = parallel_calls([lambda: purchase(api, customer_id, key)] * 4)
    assert [result.status for result in results].count(201) == 1
    assert [result.status for result in results].count(200) == 3
    assert len({result.body["id"] for result in results}) == 1
    assert sum(result.body["replayed"] for result in results) == 3
    listed = api.json(
        "GET", f"{api.orders_url}/api/v1/orders", query={"customer_id": customer_id}
    )
    assert listed.body["total"] == 1
    assert listed.body["items"][0]["loyalty_status"] == "awarded"
    assert_ledger(loyalty_snapshot(customer_id), orders=1, points=7)


def test_simultaneous_order_key_conflict_preserves_winning_request(
    api: ApiClient, loyalty_snapshot
):
    customer_id, key = str(uuid4()), f"parallel-conflict-{uuid4()}"
    results = parallel_calls(
        [
            lambda: purchase(api, customer_id, key, quantity=1),
            lambda: purchase(api, customer_id, key, quantity=2),
        ]
    )
    assert sorted(result.status for result in results) == [201, 409]
    winner = next(result for result in results if result.status == 201)
    loser = next(result for result in results if result.status == 409)
    assert loser.body["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert_ledger(
        loyalty_snapshot(customer_id), orders=1, points=winner.body["points_earned"]
    )


def test_distinct_concurrent_purchases_do_not_lose_points(
    api: ApiClient, loyalty_snapshot
):
    customer_id = str(uuid4())
    results = parallel_calls(
        [
            lambda n=n: purchase(
                api, customer_id, f"distinct-order-{uuid4()}", quantity=n
            )
            for n in range(1, 5)
        ]
    )
    assert all(result.status == 201 for result in results), results
    assert len({result.body["id"] for result in results}) == 4
    expected = sum(result.body["total_cents"] // 1000 for result in results)
    listed = api.json(
        "GET", f"{api.orders_url}/api/v1/orders", query={"customer_id": customer_id}
    )
    assert listed.body["total"] == 4
    assert_ledger(loyalty_snapshot(customer_id), orders=4, points=expected)


@pytest.mark.parametrize("same_key", [True, False])
def test_parallel_awards_for_one_order_share_one_movement(
    api: ApiClient, loyalty_snapshot, same_key
):
    customer_id, order_id = str(uuid4()), str(uuid4())
    original_key = f"parallel-award-{uuid4()}"
    keys = [original_key if same_key else f"parallel-award-{uuid4()}" for _ in range(4)]
    results = parallel_calls(
        [lambda key=key: award(api, customer_id, order_id, key) for key in keys]
    )
    assert [result.status for result in results].count(201) == 1
    assert [result.status for result in results].count(200) == 3
    assert len({result.body["movement_id"] for result in results}) == 1
    assert all(result.body["balance"] == 7 for result in results)
    assert_ledger(loyalty_snapshot(customer_id), orders=1, points=7)
    for key in keys:
        conflict = award(api, customer_id, str(uuid4()), key)
        assert conflict.status == 409
        assert conflict.body["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert_ledger(loyalty_snapshot(customer_id), orders=1, points=7)


def test_one_alias_key_cannot_bind_two_existing_movements(
    api: ApiClient, loyalty_snapshot
):
    customer_id, alias = str(uuid4()), f"alias-race-{uuid4()}"
    orders = [str(uuid4()), str(uuid4())]
    originals = [
        award(api, customer_id, order, f"original-{uuid4()}") for order in orders
    ]
    assert all(result.status == 201 for result in originals)
    results = parallel_calls(
        [lambda order=order: award(api, customer_id, order, alias) for order in orders]
    )
    assert sorted(result.status for result in results) == [200, 409]
    loser = next(result for result in results if result.status == 409)
    assert loser.body["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert_ledger(loyalty_snapshot(customer_id), orders=2, points=14)


def test_idempotent_migration_restores_keys_for_existing_movements(
    api: ApiClient, compose_command, loyalty_snapshot
):
    customer_id, order_id, key = str(uuid4()), str(uuid4()), str(uuid4())
    created = award(api, customer_id, order_id, key)
    assert created.status == 201
    psql = [
        *compose_command,
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        os.getenv("POSTGRES_USER", "cafeteria"),
        "-d",
        os.getenv("POSTGRES_DB", "cafeteria"),
        "-v",
        "ON_ERROR_STOP=1",
    ]
    # Solo borra la asociación del UUID sintético de esta prueba; simula el
    # movimiento histórico que todavía no tiene fila en la tabla nueva.
    subprocess.run(
        [
            *psql,
            "-c",
            f"DELETE FROM loyalty_request_keys WHERE idempotency_key = '{key}'",
        ],
        check=True,
        capture_output=True,
    )
    for _ in range(2):
        subprocess.run(
            [*psql, "-f", "/docker-entrypoint-initdb.d/003-loyalty.sql"],
            check=True,
            capture_output=True,
        )
    replay = award(api, customer_id, order_id, key)
    assert replay.status == 200
    assert replay.body["movement_id"] == created.body["movement_id"]
    assert_ledger(loyalty_snapshot(customer_id), orders=1, points=7)


def test_award_conflict_rolls_back_losing_customer_balance(
    api: ApiClient, loyalty_snapshot
):
    customers = [str(uuid4()), str(uuid4())]
    key = f"cross-customer-conflict-{uuid4()}"
    results = parallel_calls(
        [
            lambda customer=customer: award(api, customer, str(uuid4()), key)
            for customer in customers
        ]
    )
    assert sorted(result.status for result in results) == [201, 409]
    for customer, result in zip(customers, results, strict=True):
        snapshot = loyalty_snapshot(customer)
        if result.status == 201:
            assert_ledger(snapshot, orders=1, points=7)
        else:
            assert result.body["code"] == "IDEMPOTENCY_KEY_REUSED"
            assert snapshot == {
                "account_count": 0,
                "balance": 0,
                "movement_count": 0,
                "distinct_orders": 0,
                "movement_points": 0,
            }


def test_parallel_awards_with_different_amounts_preserve_first_movement(
    api: ApiClient, loyalty_snapshot
):
    customer_id, order_id = str(uuid4()), str(uuid4())
    results = parallel_calls(
        [
            lambda amount=amount: award(
                api, customer_id, order_id, f"amount-race-{uuid4()}", amount=amount
            )
            for amount in (3500, 7000)
        ]
    )
    assert sorted(result.status for result in results) == [201, 409]
    winner = next(result for result in results if result.status == 201)
    loser = next(result for result in results if result.status == 409)
    assert loser.body["code"] == "ORDER_ALREADY_AWARDED"
    assert_ledger(
        loyalty_snapshot(customer_id), orders=1, points=winner.body["points_earned"]
    )


def test_duplicate_frontend_checkout_cookie_creates_only_one_purchase(
    api: ApiClient, browser: BrowserSession, loyalty_snapshot
):
    # La sesión y el token se obtienen antes de enviar formularios protegidos.
    browser.request(
        "POST", f"{api.frontend_url}/cart/items/1", headers={"HX-Request": "true"}
    )
    url = f"{api.frontend_url}/checkout"
    cookie = browser.cookie_header(url)
    results = parallel_calls(
        [
            lambda: api.text(
                url,
                method="POST",
                headers={"Cookie": cookie, "X-CSRF-Token": browser.csrf_token},
                timeout=20,
            )
        ]
        * 4
    )
    assert all(result.status == 200 for result in results)
    order_ids = {
        re.search(r'data-order-id="([0-9a-f-]{36})"', result.body)[1]
        for result in results
    }
    assert len(order_ids) == 1
    order = api.json("GET", f"{api.orders_url}/api/v1/orders/{order_ids.pop()}").body
    listed = api.json(
        "GET",
        f"{api.orders_url}/api/v1/orders",
        query={"customer_id": order["customer_id"]},
    )
    assert listed.body["total"] == 1
    assert_ledger(loyalty_snapshot(order["customer_id"]), orders=1, points=3)


def test_two_retry_workers_and_manual_retries_do_not_duplicate_points(
    api: ApiClient, compose_command, loyalty_snapshot
):
    customer_id = str(uuid4())
    process = None
    subprocess.run(
        [*compose_command, "stop", "svc-lealtad"], check=True, capture_output=True
    )
    try:
        created = purchase(api, customer_id, f"worker-race-{uuid4()}")
        assert created.status == 201
        assert created.body["loyalty_status"] == "pending"
        order_id = created.body["id"]
        # Dos lotes reales leen el mismo pendiente antes de liberar sus llamadas
        # HTTP. La barrera fuerza la carrera aunque un thread arranque más tarde.
        script = f"""
import json, sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from threading import Barrier, Event
from app.config import load_settings
from app.clients import HttpLoyaltyClient
from app.loyalty_retry import retry_pending_loyalty
from app.repository import PostgresOrderRepository

gate, release = Barrier(3), Event()
settings = load_settings()
class SelectedRepository(PostgresOrderRepository):
    def list_pending_loyalty(self, *, limit):
        orders, _ = super().list_pending_loyalty(limit=limit)
        selected = [order for order in orders if str(order.id) == {order_id!r}]
        return selected, len(selected)
class SynchronizedLoyalty(HttpLoyaltyClient):
    def award(self, *args, **kwargs):
        gate.wait(timeout=20)
        if not release.wait(timeout=30):
            raise RuntimeError("La prueba no liberó los workers")
        return super().award(*args, **kwargs)
repository = SelectedRepository(settings.database_url)
loyalty = SynchronizedLoyalty(settings.loyalty_url, settings.http_timeout_seconds)
with ThreadPoolExecutor(max_workers=2) as pool:
    tasks = [pool.submit(retry_pending_loyalty, repository, loyalty, batch_size=100) for _ in range(2)]
    gate.wait(timeout=20)
    print("READY", flush=True)
    try:
        if sys.stdin.readline().strip() != "GO":
            raise RuntimeError("Se esperaba GO")
    finally:
        release.set()
    results = [asdict(task.result(timeout=20)) for task in tasks]
print("RESULT:" + json.dumps(results), flush=True)
"""
        process = subprocess.Popen(
            [
                *compose_command,
                "exec",
                "-T",
                "svc-pedidos",
                "python",
                "-u",
                "-c",
                script,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        assert process.stdout.readline().strip() == "READY"
    finally:
        subprocess.run(
            [*compose_command, "start", "svc-lealtad"], check=True, capture_output=True
        )

    try:
        api.wait_until_healthy(timeout_seconds=90)

        def release_workers():
            stdout, stderr = process.communicate("GO\n", timeout=30)
            assert process.returncode == 0, stderr
            result_line = next(
                line for line in stdout.splitlines() if line.startswith("RESULT:")
            )
            results = json.loads(result_line.removeprefix("RESULT:"))
            assert all(
                result["attempted"] == 1 and result["awarded"] == 1
                for result in results
            ), results

        def manual_retry():
            result = api.json(
                "POST",
                f"{api.orders_url}/api/v1/orders/{order_id}/loyalty/retry",
                timeout=15,
            )
            assert result.status == 200
            assert result.body["loyalty_status"] == "awarded"

        parallel_calls([release_workers, manual_retry, manual_retry])
        assert_ledger(loyalty_snapshot(customer_id), orders=1, points=7)
    finally:
        if process is not None and process.poll() is None:
            process.communicate("GO\n", timeout=35)
