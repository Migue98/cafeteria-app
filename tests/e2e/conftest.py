"""Fixtures exclusivas de las pruebas HTTP sin JavaScript."""

import os
import subprocess

import pytest

from ..support import ApiClient as ApiClient
from ..support import BrowserSession as BrowserSession


@pytest.fixture
def browser() -> BrowserSession:
    return BrowserSession()


@pytest.fixture
def set_product_availability(compose_command: list[str]):
    changed_products: list[int] = []

    def update(product_id: int, available: bool) -> None:
        literal = "TRUE" if available else "FALSE"
        sql = f"UPDATE products SET available = {literal} WHERE id = {product_id};"
        subprocess.run(
            [
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
                "-c",
                sql,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        if not available:
            changed_products.append(product_id)

    yield update

    for product_id in changed_products:
        update(product_id, True)
