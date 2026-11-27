"""Persistencia transaccional del libro de puntos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import Protocol
from uuid import UUID

import psycopg
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.trace import TracerProvider
from psycopg import errors
from psycopg.rows import dict_row

from .models import EarnPointsRequest, PointAward, PointsBalance


class RepositoryUnavailable(RuntimeError):
    """PostgreSQL no puede atender la operación."""


@dataclass(frozen=True, slots=True)
class StoredAward:
    award: PointAward
    request_hash: str


class LoyaltyRepository(Protocol):
    def health(self) -> float: ...

    def get_by_idempotency_key(self, key: str) -> StoredAward | None: ...

    def get_by_order_id(self, order_id: UUID) -> StoredAward | None: ...

    def bind_idempotency_key(self, key: str, movement_id: UUID) -> StoredAward: ...

    def save_award(
        self,
        payload: EarnPointsRequest,
        *,
        points_earned: int,
        idempotency_key: str,
        request_hash: str,
        movement_id: UUID,
        awarded_at: datetime,
    ) -> PointAward | None: ...

    def get_balance(self, customer_id: UUID) -> PointsBalance: ...


class PostgresLoyaltyRepository:
    def __init__(self, database_url: str, *, tracer_provider: TracerProvider | None = None) -> None:
        self._database_url = database_url
        self._tracer_provider = tracer_provider

    def _connect(self) -> psycopg.Connection:
        try:
            connection = psycopg.connect(
                self._database_url,
                connect_timeout=3,
                row_factory=dict_row,
            )
            return PsycopgInstrumentor().instrument_connection(
                connection, tracer_provider=self._tracer_provider
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

    @staticmethod
    def _stored_award(row: dict) -> StoredAward:
        return StoredAward(
            award=PointAward(
                movement_id=row["movement_id"],
                order_id=row["order_id"],
                customer_id=row["customer_id"],
                points_earned=row["points_earned"],
                balance=row["balance_after"],
                awarded_at=row["awarded_at"],
            ),
            request_hash=row["request_hash"],
        )

    def get_by_idempotency_key(self, key: str) -> StoredAward | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT movement.* FROM loyalty_movements AS movement
                    JOIN loyalty_request_keys AS request_key
                      ON request_key.movement_id = movement.movement_id
                    WHERE request_key.idempotency_key = %(key)s
                    """,
                    {"key": key},
                ).fetchone()
        except psycopg.Error as exc:
            raise RepositoryUnavailable("No fue posible consultar la idempotencia") from exc
        return self._stored_award(row) if row is not None else None

    def bind_idempotency_key(self, key: str, movement_id: UUID) -> StoredAward:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO loyalty_request_keys (idempotency_key, movement_id)
                    VALUES (%(key)s, %(movement_id)s)
                    ON CONFLICT (idempotency_key) DO NOTHING
                    """,
                    {"key": key, "movement_id": movement_id},
                )
                # Tras esperar un conflicto, READ COMMITTED observa al ganador
                # en esta segunda sentencia; el llamador compara el request_hash.
                row = connection.execute(
                    """
                    SELECT movement.* FROM loyalty_movements AS movement
                    JOIN loyalty_request_keys AS request_key
                      ON request_key.movement_id = movement.movement_id
                    WHERE request_key.idempotency_key = %(key)s
                    """,
                    {"key": key},
                ).fetchone()
                if row is None:
                    raise RepositoryUnavailable("No fue posible reservar la clave de idempotencia")
                return self._stored_award(row)
        except psycopg.Error as exc:
            raise RepositoryUnavailable("No fue posible reservar la clave de idempotencia") from exc

    def get_by_order_id(self, order_id: UUID) -> StoredAward | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM loyalty_movements WHERE order_id = %(order_id)s",
                    {"order_id": order_id},
                ).fetchone()
        except psycopg.Error as exc:
            raise RepositoryUnavailable("No fue posible consultar el pedido acreditado") from exc
        return self._stored_award(row) if row is not None else None

    def save_award(
        self,
        payload: EarnPointsRequest,
        *,
        points_earned: int,
        idempotency_key: str,
        request_hash: str,
        movement_id: UUID,
        awarded_at: datetime,
    ) -> PointAward | None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO loyalty_accounts (customer_id, balance, updated_at)
                    VALUES (%(customer_id)s, 0, %(awarded_at)s)
                    ON CONFLICT (customer_id) DO NOTHING
                    """,
                    {"customer_id": payload.customer_id, "awarded_at": awarded_at},
                )
                balance_row = connection.execute(
                    """
                    UPDATE loyalty_accounts
                    SET balance = balance + %(points_earned)s,
                        updated_at = %(awarded_at)s
                    WHERE customer_id = %(customer_id)s
                    RETURNING balance
                    """,
                    {
                        "customer_id": payload.customer_id,
                        "points_earned": points_earned,
                        "awarded_at": awarded_at,
                    },
                ).fetchone()
                balance = int(balance_row["balance"])
                connection.execute(
                    """
                    INSERT INTO loyalty_movements (
                        movement_id, order_id, customer_id, amount_cents,
                        points_earned, balance_after, rule, idempotency_key,
                        request_hash, occurred_at, awarded_at
                    ) VALUES (
                        %(movement_id)s, %(order_id)s, %(customer_id)s,
                        %(amount_cents)s, %(points_earned)s, %(balance_after)s,
                        '1-point-per-10-mxn-v1', %(idempotency_key)s,
                        %(request_hash)s, %(occurred_at)s, %(awarded_at)s
                    )
                    """,
                    {
                        "movement_id": movement_id,
                        "order_id": payload.order_id,
                        "customer_id": payload.customer_id,
                        "amount_cents": payload.amount_cents,
                        "points_earned": points_earned,
                        "balance_after": balance,
                        "idempotency_key": idempotency_key,
                        "request_hash": request_hash,
                        "occurred_at": payload.occurred_at,
                        "awarded_at": awarded_at,
                    },
                )
                connection.execute(
                    """
                    INSERT INTO loyalty_request_keys (idempotency_key, movement_id)
                    VALUES (%(key)s, %(movement_id)s)
                    """,
                    {"key": idempotency_key, "movement_id": movement_id},
                )
            return PointAward(
                movement_id=movement_id,
                order_id=payload.order_id,
                customer_id=payload.customer_id,
                points_earned=points_earned,
                balance=balance,
                awarded_at=awarded_at,
            )
        except errors.UniqueViolation:
            return None
        except psycopg.Error as exc:
            raise RepositoryUnavailable("No fue posible acreditar los puntos") from exc

    def get_balance(self, customer_id: UUID) -> PointsBalance:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT customer_id, balance, updated_at
                    FROM loyalty_accounts
                    WHERE customer_id = %(customer_id)s
                    """,
                    {"customer_id": customer_id},
                ).fetchone()
        except psycopg.Error as exc:
            raise RepositoryUnavailable("No fue posible consultar el saldo") from exc
        if row is None:
            return PointsBalance(customer_id=customer_id, balance=0, updated_at=None)
        return PointsBalance.model_validate(row)
