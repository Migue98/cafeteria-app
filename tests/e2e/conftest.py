"""Utilidades compartidas para las pruebas end-to-end."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from http.cookiejar import CookieJar
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen
from uuid import UUID

import pytest


@dataclass(frozen=True)
class HttpResult:
    status: int
    headers: dict[str, str]
    body: Any


class ApiClient:
    def __init__(self) -> None:
        self.frontend_url = os.getenv("E2E_FRONTEND_URL", "http://localhost:18000")
        self.menu_url = os.getenv("E2E_MENU_URL", "http://localhost:18001")
        self.orders_url = os.getenv("E2E_ORDERS_URL", "http://localhost:18002")
        self.loyalty_url = os.getenv("E2E_LOYALTY_URL", "http://localhost:18003")

    def json(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        query: dict[str, Any] | None = None,
        timeout: float = 5,
    ) -> HttpResult:
        if query:
            url = f"{url}?{urlencode(query)}"
        data = json.dumps(payload).encode() if payload is not None else None
        request_headers = {"Accept": "application/json", **(headers or {})}
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read().decode()
                return HttpResult(
                    response.status,
                    {key.lower(): value for key, value in response.headers.items()},
                    json.loads(raw),
                )
        except HTTPError as exc:
            raw = exc.read().decode()
            try:
                body: Any = json.loads(raw)
            except json.JSONDecodeError:
                body = raw
            return HttpResult(
                exc.code,
                {key.lower(): value for key, value in exc.headers.items()},
                body,
            )

    def text(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        timeout: float = 5,
    ) -> HttpResult:
        request = Request(
            url,
            data=b"" if method != "GET" else None,
            headers={"Accept": "text/plain", **(headers or {})},
            method=method,
        )
        with urlopen(request, timeout=timeout) as response:
            return HttpResult(
                response.status,
                {key.lower(): value for key, value in response.headers.items()},
                response.read().decode(),
            )

    def wait_until_healthy(self, timeout_seconds: int = 90) -> None:
        services = {
            "frontend": self.frontend_url,
            "menu": self.menu_url,
            "orders": self.orders_url,
            "loyalty": self.loyalty_url,
        }
        deadline = time.monotonic() + timeout_seconds
        pending = set(services)
        last_errors: dict[str, str] = {}
        while pending and time.monotonic() < deadline:
            for service in tuple(pending):
                try:
                    result = self.json("GET", f"{services[service]}/health", timeout=2)
                except (URLError, TimeoutError, OSError) as exc:
                    last_errors[service] = str(exc)
                    continue
                if result.status == 200 and result.body.get("status") == "healthy":
                    pending.remove(service)
                else:
                    last_errors[service] = f"HTTP {result.status}: {result.body}"
            if pending:
                time.sleep(1)
        if pending:
            pytest.fail(
                f"Servicios sin salud: {sorted(pending)}; último error: {last_errors}"
            )


class BrowserSession:
    """Navegador HTTP mínimo con cookies y seguimiento de redirecciones."""

    def __init__(self) -> None:
        self._cookies = CookieJar()
        self._opener = build_opener(HTTPCookieProcessor(self._cookies))

    def cookie_header(self, url: str) -> str:
        request = Request(url)
        self._cookies.add_cookie_header(request)
        return request.get_header("Cookie", "")

    def request(
        self, method: str, url: str, *, headers: dict[str, str] | None = None
    ) -> HttpResult:
        data = b"" if method != "GET" else None
        request = Request(url, data=data, method=method, headers=headers or {})
        try:
            response = self._opener.open(request, timeout=15)
        except HTTPError as exc:
            response = exc
        with response:
            return HttpResult(
                response.status,
                {key.lower(): value for key, value in response.headers.items()},
                response.read().decode(),
            )


@pytest.fixture(scope="session")
def api() -> ApiClient:
    client = ApiClient()
    client.wait_until_healthy()
    return client


@pytest.fixture
def browser() -> BrowserSession:
    return BrowserSession()


@pytest.fixture(scope="session")
def compose_command() -> list[str]:
    repository = Path(__file__).resolve().parents[2]
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
