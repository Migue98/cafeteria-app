"""Clientes del monitoreo real y Compose ampliado para el entorno aislado."""

import base64
import os
import time
from pathlib import Path
from urllib.error import URLError

import pytest

from ..support import ApiClient

SERVICES = {"frontend", "svc-menu", "svc-pedidos", "svc-lealtad"}


class Monitoring:
    def __init__(self, api: ApiClient) -> None:
        self.api = api
        self.prometheus_url = os.getenv("E2E_PROMETHEUS_URL", "http://localhost:19090")
        self.grafana_url = os.getenv("E2E_GRAFANA_URL", "http://localhost:13000")
        self.user = os.getenv("GRAFANA_ADMIN_USER", "admin")
        self.password = os.getenv("GRAFANA_ADMIN_PASSWORD", "local-grafana-change-me")

    def grafana(self, path: str, *, method="GET", payload=None, query=None):
        encoded = base64.b64encode(f"{self.user}:{self.password}".encode()).decode()
        return self.api.json(
            method,
            f"{self.grafana_url}{path}",
            payload=payload,
            query=query,
            headers={"Authorization": f"Basic {encoded}"},
        )

    def query(self, expression: str, *, grafana=False, at=None) -> list[dict]:
        parameters = {"query": expression}
        if at is not None:
            parameters["time"] = str(at)
        if grafana:
            response = self.grafana(
                "/api/datasources/proxy/uid/cafeteria-prometheus/api/v1/query", query=parameters
            )
        else:
            response = self.api.json("GET", f"{self.prometheus_url}/api/v1/query", query=parameters)
        assert response.status == 200, response.body
        assert response.body["status"] == "success", response.body
        return response.body["data"]["result"]

    def until(self, condition, *, timeout=90, description="estado de monitoreo"):
        deadline = time.monotonic() + timeout
        last_error = None
        while time.monotonic() < deadline:
            try:
                if result := condition():
                    return result
            except (URLError, TimeoutError, OSError, AssertionError) as exc:
                last_error = str(exc)
            time.sleep(0.5)
        pytest.fail(f"No se alcanzó {description}: {last_error}")

    def wait_ready(self):
        self.until(
            lambda: (
                self.api.text(f"{self.prometheus_url}/-/ready").status == 200
                and self.grafana("/api/health").body.get("database") == "ok"
            ),
            timeout=180,
            description="Prometheus y Grafana disponibles",
        )

    def wait_targets(self):
        def ready():
            rows = self.query('up{job="cafeteria"}')
            assert {row["metric"]["service"] for row in rows} == SERVICES, rows
            assert all(row["value"][1] == "1" for row in rows), rows
            return True

        self.until(ready, description="los cuatro targets UP")


@pytest.fixture(scope="session")
def compose_command(compose_command):
    override = Path(__file__).resolve().parents[2] / "compose.monitoring.yaml"
    command = [*compose_command, "-f", str(override)]
    if os.getenv("E2E_TELEMETRY") == "1":
        command.extend(["-f", str(override.parent / "compose.telemetry.yaml")])
    if os.getenv("E2E_ALERTS") == "1":
        command.extend(["-f", str(override.parent / "tests/monitoring/compose.alerts.yaml")])
    return command


@pytest.fixture(scope="session")
def monitoring(api):
    client = Monitoring(api)
    client.wait_ready()
    client.wait_targets()
    return client
