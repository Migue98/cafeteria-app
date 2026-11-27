"""Fixtures del entorno Compose compartidas por HTTP y navegador real."""

import json
import os
import shlex
import subprocess
from pathlib import Path
from uuid import UUID

import pytest

from .support import ApiClient


@pytest.fixture(scope="session")
def api() -> ApiClient:
    client = ApiClient()
    client.wait_until_healthy()
    return client


@pytest.fixture(scope="session")
def compose_command() -> list[str]:
    repository = Path(__file__).resolve().parents[1]
    engine = shlex.split(os.getenv("E2E_CONTAINER_ENGINE", "docker"))
    project = os.getenv("E2E_COMPOSE_PROJECT", "cafeteria-e2e")
    compose_file = os.getenv("E2E_COMPOSE_FILE", str(repository / "compose.yaml"))
    return [*engine, "compose", "-p", project, "-f", compose_file]


@pytest.fixture
def loyalty_snapshot(compose_command: list[str]):
    """Lee el saldo y los movimientos persistidos para un UUID de prueba."""

    def read(customer_id: str) -> dict:
        customer_id = str(UUID(customer_id))
        sql = f"""
            SELECT json_build_object(
                'account_count', (SELECT COUNT(*) FROM loyalty_accounts
                                  WHERE customer_id = '{customer_id}'::uuid),
                'balance', COALESCE((SELECT balance FROM loyalty_accounts
                                     WHERE customer_id = '{customer_id}'::uuid), 0),
                'movement_count', COUNT(*),
                'distinct_orders', COUNT(DISTINCT order_id),
                'movement_points', COALESCE(SUM(points_earned), 0)
            )
            FROM loyalty_movements WHERE customer_id = '{customer_id}'::uuid
        """
        result = subprocess.run(
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
                "-A",
                "-t",
                "-c",
                sql,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout.strip())

    return read
