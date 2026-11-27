"""Chromium real: sesión nueva por caso y diagnóstico de errores del cliente."""

import subprocess
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pytest
from playwright.sync_api import Page

from ..support import ApiClient


@pytest.fixture
def browser_context_args(browser_context_args: dict) -> dict:
    return {**browser_context_args, "locale": "es-MX", "timezone_id": "America/Mexico_City"}


@pytest.fixture
def browser_errors(page: Page, api: ApiClient) -> list[str]:
    """Los casos fallan si el navegador registra errores de JS, consola o red."""
    errors: list[str] = []
    page.set_default_timeout(10_000)
    page.on("pageerror", lambda error: errors.append(f"JavaScript: {error}"))
    page.on(
        "console",
        lambda message: (
            errors.append(f"Consola: {message.text}") if message.type == "error" else None
        ),
    )
    page.on(
        "requestfailed",
        lambda request: errors.append(f"Red: {request.method} {request.url}: {request.failure}"),
    )
    page.on(
        "response",
        lambda response: (
            errors.append(f"HTTP {response.status}: {response.url}")
            if response.url.startswith(f"{api.frontend_url}/") and response.status >= 400
            else None
        ),
    )
    return errors


@pytest.fixture
def loyalty_outage(api: ApiClient, compose_command: list[str]) -> Callable:
    """Restaura lealtad incluso si falla una aserción durante la caída."""

    @contextmanager
    def stopped() -> Iterator[None]:
        try:
            subprocess.run([*compose_command, "stop", "svc-lealtad"], check=True)
            yield
        finally:
            subprocess.run([*compose_command, "start", "svc-lealtad"], check=True)
            api.wait_until_healthy()

    return stopped
