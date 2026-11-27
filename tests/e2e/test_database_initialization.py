"""Inicialización real y persistencia sobre PostgreSQL del Compose de ensayo."""

import json
import os
import subprocess
from uuid import uuid4

import pytest

pytestmark = pytest.mark.e2e
SCHEMAS = (
    "/docker-entrypoint-initdb.d/001-menu.sql",
    "/docker-entrypoint-initdb.d/002-orders.sql",
    "/docker-entrypoint-initdb.d/003-loyalty.sql",
)
SEED = "/docker-entrypoint-initdb.d/004-menu-seed.sql"
TABLES = (
    "products",
    "orders",
    "order_items",
    "loyalty_accounts",
    "loyalty_movements",
    "loyalty_request_keys",
)


class Database:
    def __init__(self, compose_command, name):
        self.command = [
            *compose_command,
            "exec",
            "-T",
            "postgres",
            "psql",
            "-X",
            "-q",
            "-A",
            "-t",
            "-U",
            os.getenv("POSTGRES_USER", "cafeteria"),
            "-d",
            name,
            "-v",
            "ON_ERROR_STOP=1",
        ]

    def run(self, *arguments):
        result = subprocess.run(
            [*self.command, *arguments],
            check=True,
            capture_output=True,
            encoding="utf-8",
        )
        return result.stdout.strip()

    def query(self, sql):
        return json.loads(self.run("-c", sql))

    def apply_schema(self):
        for path in SCHEMAS:
            self.run("-f", path)

    def snapshot(self):
        # Nombres constantes; ordenar el JSON preserva todas las filas y columnas.
        return {
            table: self.query(
                "SELECT COALESCE(json_agg(row_to_json(t) ORDER BY row_to_json(t)::text), "
                f"'[]'::json) FROM {table} t"
            )
            for table in TABLES
        }


@pytest.fixture
def empty_database(api, compose_command):
    # El API listo garantiza que la inicialización del servidor haya terminado.
    # Cada prueba usa una BD nueva y solo elimina su propio nombre aleatorio.
    admin = Database(compose_command, os.getenv("POSTGRES_DB", "cafeteria"))
    name = "e2e_initialization_" + uuid4().hex
    admin.run("-c", f"CREATE DATABASE {name}")
    try:
        yield Database(compose_command, name)
    finally:
        admin.run("-c", f"DROP DATABASE {name} WITH (FORCE)")


def test_schema_initializes_empty_database_separately_from_demo_products(empty_database):
    database = empty_database
    database.apply_schema()
    assert database.snapshot() == dict.fromkeys(TABLES, [])
    for _ in range(2):
        database.run("-f", SEED)
    snapshot = database.snapshot()
    assert len(snapshot.pop("products")) == 20
    assert all(rows == [] for rows in snapshot.values())
    assert database.query("SELECT price_cents FROM products WHERE id = 1") == 3500


def test_reapplying_initialization_preserves_data_and_product_sequence(empty_database):
    database = empty_database
    database.apply_schema()
    database.run("-f", SEED)
    customer, order, movement = uuid4(), uuid4(), uuid4()
    database.run(
        "-c",
        f"""
        BEGIN;
        UPDATE products SET name = 'Precio ajustado', price_cents = 4100,
            available = FALSE, updated_at = CURRENT_TIMESTAMP WHERE id = 1;
        INSERT INTO orders (id, customer_id, status, loyalty_status, points_earned,
            currency, subtotal_cents, total_cents, idempotency_key, request_hash)
        VALUES ('{order}', '{customer}', 'confirmed', 'awarded', 4,
            'MXN', 4100, 4100, 'initialization-order', repeat('a', 64));
        INSERT INTO order_items (order_id, position, product_id, sku, product_name,
            quantity, unit_price_cents, line_total_cents)
        VALUES ('{order}', 1, 1, 'CAFE-AMERICANO', 'Precio ajustado', 1, 4100, 4100);
        INSERT INTO loyalty_accounts (customer_id, balance) VALUES ('{customer}', 4);
        INSERT INTO loyalty_movements (movement_id, order_id, customer_id, amount_cents,
            points_earned, balance_after, rule, idempotency_key, request_hash)
        VALUES ('{movement}', '{order}', '{customer}', 4100, 4, 4,
            '1-point-per-10-mxn-v1', 'initialization-points', repeat('b', 64));
        INSERT INTO loyalty_request_keys (idempotency_key, movement_id)
        VALUES ('initialization-points', '{movement}');
        COMMIT;
        """,
    )
    deleted_id = database.query(
        "INSERT INTO products (sku, name, category, price_cents) "
        "VALUES ('TEST-DELETED', 'Eliminado', 'prueba', 1234) RETURNING id"
    )
    database.run("-c", f"DELETE FROM products WHERE id = {deleted_id}")
    before = database.snapshot()
    for _ in range(2):
        database.apply_schema()
        database.run("-f", SEED)
    assert database.snapshot() == before
    next_id = database.query(
        "INSERT INTO products (sku, name, category, price_cents) "
        "VALUES ('TEST-NEW', 'Nuevo', 'prueba', 1234) RETURNING id"
    )
    assert next_id > deleted_id


def test_recreating_stack_keeps_catalog_order_balance_and_idempotency(
    api, compose_command, set_product_availability, loyalty_snapshot
):
    customer, key = str(uuid4()), "initialization-recreate-" + uuid4().hex
    payload = {"customer_id": customer, "items": [{"product_id": 1, "quantity": 1}]}
    created = api.json(
        "POST", api.orders_url + "/api/v1/orders", payload=payload, headers={"Idempotency-Key": key}
    )
    assert created.status == 201 and created.body["loyalty_status"] == "awarded"
    order = api.json("GET", api.orders_url + "/api/v1/orders/" + created.body["id"])
    ledger = loyalty_snapshot(customer)
    set_product_availability(1, False)
    product = api.json("GET", api.menu_url + "/api/v1/products/1")
    assert product.body["available"] is False
    try:
        # Conserva el volumen. La recreación hace pasar PostgreSQL por su entrypoint.
        subprocess.run([*compose_command, "down"], check=True, capture_output=True)
    finally:
        subprocess.run(
            [*compose_command, "up", "--detach", "--no-build"],
            check=True,
            capture_output=True,
        )
        api.wait_until_healthy(timeout_seconds=90)
    assert api.json("GET", api.menu_url + "/api/v1/products/1").body == product.body
    assert (
        api.json("GET", api.orders_url + "/api/v1/orders/" + created.body["id"]).body == order.body
    )
    assert loyalty_snapshot(customer) == ledger
    replay = api.json(
        "POST", api.orders_url + "/api/v1/orders", payload=payload, headers={"Idempotency-Key": key}
    )
    assert replay.status == 200 and replay.body["id"] == created.body["id"]
    assert loyalty_snapshot(customer) == ledger
