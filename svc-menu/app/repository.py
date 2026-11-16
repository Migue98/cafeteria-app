"""Acceso al catálogo almacenado en PostgreSQL."""

from __future__ import annotations

from time import perf_counter
from typing import Protocol

import psycopg
from psycopg.rows import dict_row

from .models import Product


class RepositoryUnavailable(RuntimeError):
    """La base de datos no puede atender la operación."""


class ProductRepository(Protocol):
    def health(self) -> float: ...

    def list_products(
        self,
        *,
        category: str | None,
        available: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[Product], int]: ...

    def get_product(self, product_id: int) -> Product | None: ...


class PostgresProductRepository:
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

    def list_products(
        self,
        *,
        category: str | None,
        available: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[Product], int]:
        conditions = ["available = %(available)s"]
        parameters: dict[str, object] = {
            "available": available,
            "limit": limit,
            "offset": offset,
        }
        if category is not None:
            conditions.append("category = %(category)s")
            parameters["category"] = category

        where_clause = " AND ".join(conditions)
        try:
            with self._connect() as connection:
                total_row = connection.execute(
                    f"SELECT COUNT(*) AS total FROM products WHERE {where_clause}",
                    parameters,
                ).fetchone()
                rows = connection.execute(
                    f"""
                    SELECT id, sku, name, description, category, price_cents,
                           currency, available, image_url, created_at, updated_at
                    FROM products
                    WHERE {where_clause}
                    ORDER BY id
                    LIMIT %(limit)s OFFSET %(offset)s
                    """,
                    parameters,
                ).fetchall()
        except psycopg.Error as exc:
            raise RepositoryUnavailable("No fue posible consultar el catálogo") from exc

        total = int(total_row["total"]) if total_row is not None else 0
        return [Product.model_validate(row) for row in rows], total

    def get_product(self, product_id: int) -> Product | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT id, sku, name, description, category, price_cents,
                           currency, available, image_url, created_at, updated_at
                    FROM products
                    WHERE id = %(product_id)s
                    """,
                    {"product_id": product_id},
                ).fetchone()
        except psycopg.Error as exc:
            raise RepositoryUnavailable("No fue posible consultar el producto") from exc

        return Product.model_validate(row) if row is not None else None
