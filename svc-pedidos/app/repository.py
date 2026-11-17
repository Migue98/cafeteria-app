"""Persistencia de pedidos e idempotencia en PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Protocol
from uuid import UUID

import psycopg
from psycopg import errors
from psycopg.rows import dict_row

from .models import Order, OrderItem


class RepositoryUnavailable(RuntimeError):
    """PostgreSQL no puede atender la operación."""


@dataclass(frozen=True, slots=True)
class StoredOrder:
    order: Order
    request_hash: str


class OrderRepository(Protocol):
    def health(self) -> float: ...

    def get_by_idempotency_key(self, key: str) -> StoredOrder | None: ...

    def save(self, order: Order, *, idempotency_key: str, request_hash: str) -> bool: ...

    def get(self, order_id: UUID) -> Order | None: ...

    def list_for_customer(
        self, customer_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[Order], int]: ...

    def mark_loyalty_awarded(self, order_id: UUID, points_earned: int) -> Order: ...


class PostgresOrderRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def _connect(self) -> psycopg.Connection:
        try:
            return psycopg.connect(
                self._database_url,
                connect_timeout=3,
                row_factory=dict_row,
            )
        except (psycopg.Error, OSError) as exc:
            raise RepositoryUnavailable("PostgreSQL no está disponible") from exc

    def health(self) -> float:
        started = perf_counter()
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1")
        except psycopg.Error as exc:
            raise RepositoryUnavailable("PostgreSQL no está disponible") from exc
        return round((perf_counter() - started) * 1000, 3)

    def _hydrate_order(self, connection: psycopg.Connection, row: dict) -> Order:
        item_rows = connection.execute(
            """
            SELECT product_id, sku, product_name, quantity,
                   unit_price_cents, line_total_cents
            FROM order_items
            WHERE order_id = %(order_id)s
            ORDER BY position
            """,
            {"order_id": row["id"]},
        ).fetchall()
        return Order(
            id=row["id"],
            customer_id=row["customer_id"],
            status=row["status"],
            loyalty_status=row["loyalty_status"],
            points_earned=row["points_earned"],
            currency=row["currency"],
            subtotal_cents=row["subtotal_cents"],
            total_cents=row["total_cents"],
            items=[OrderItem.model_validate(item) for item in item_rows],
            replayed=False,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_by_idempotency_key(self, key: str) -> StoredOrder | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM orders WHERE idempotency_key = %(key)s",
                    {"key": key},
                ).fetchone()
                if row is None:
                    return None
                return StoredOrder(
                    order=self._hydrate_order(connection, row),
                    request_hash=row["request_hash"],
                )
        except psycopg.Error as exc:
            raise RepositoryUnavailable("No fue posible consultar la idempotencia") from exc

    def save(self, order: Order, *, idempotency_key: str, request_hash: str) -> bool:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO orders (
                        id, customer_id, status, loyalty_status, points_earned,
                        currency, subtotal_cents, total_cents, idempotency_key,
                        request_hash, created_at, updated_at
                    ) VALUES (
                        %(id)s, %(customer_id)s, %(status)s, %(loyalty_status)s,
                        %(points_earned)s, %(currency)s, %(subtotal_cents)s,
                        %(total_cents)s, %(idempotency_key)s, %(request_hash)s,
                        %(created_at)s, %(updated_at)s
                    )
                    """,
                    {
                        **order.model_dump(exclude={"items", "replayed"}),
                        "idempotency_key": idempotency_key,
                        "request_hash": request_hash,
                    },
                )
                with connection.cursor() as cursor:
                    cursor.executemany(
                        """
                        INSERT INTO order_items (
                            order_id, position, product_id, sku, product_name,
                            quantity, unit_price_cents, line_total_cents
                        ) VALUES (
                            %(order_id)s, %(position)s, %(product_id)s, %(sku)s,
                            %(product_name)s, %(quantity)s, %(unit_price_cents)s,
                            %(line_total_cents)s
                        )
                        """,
                        [
                            {
                                "order_id": order.id,
                                "position": position,
                                **item.model_dump(),
                            }
                            for position, item in enumerate(order.items, start=1)
                        ],
                    )
            return True
        except errors.UniqueViolation:
            return False
        except psycopg.Error as exc:
            raise RepositoryUnavailable("No fue posible guardar el pedido") from exc

    def get(self, order_id: UUID) -> Order | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM orders WHERE id = %(order_id)s",
                    {"order_id": order_id},
                ).fetchone()
                return self._hydrate_order(connection, row) if row is not None else None
        except psycopg.Error as exc:
            raise RepositoryUnavailable("No fue posible consultar el pedido") from exc

    def list_for_customer(
        self, customer_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[Order], int]:
        try:
            with self._connect() as connection:
                total_row = connection.execute(
                    "SELECT COUNT(*) AS total FROM orders WHERE customer_id = %(customer_id)s",
                    {"customer_id": customer_id},
                ).fetchone()
                rows = connection.execute(
                    """
                    SELECT * FROM orders
                    WHERE customer_id = %(customer_id)s
                    ORDER BY created_at DESC, id DESC
                    LIMIT %(limit)s OFFSET %(offset)s
                    """,
                    {"customer_id": customer_id, "limit": limit, "offset": offset},
                ).fetchall()
                orders = [self._hydrate_order(connection, row) for row in rows]
        except psycopg.Error as exc:
            raise RepositoryUnavailable("No fue posible listar los pedidos") from exc
        total = int(total_row["total"]) if total_row is not None else 0
        return orders, total

    def mark_loyalty_awarded(self, order_id: UUID, points_earned: int) -> Order:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    UPDATE orders
                    SET loyalty_status = 'awarded',
                        points_earned = %(points_earned)s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %(order_id)s
                    RETURNING *
                    """,
                    {"order_id": order_id, "points_earned": points_earned},
                ).fetchone()
                if row is None:
                    raise RepositoryUnavailable("El pedido desapareció durante la actualización")
                return self._hydrate_order(connection, row)
        except psycopg.Error as exc:
            raise RepositoryUnavailable("No fue posible actualizar los puntos") from exc
