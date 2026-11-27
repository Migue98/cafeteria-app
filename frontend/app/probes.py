"""Probes HTTP acotadas; cada imagen conserva su implementación autónoma."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from opentelemetry.trace import TracerProvider
from pydantic import BaseModel, ConfigDict, create_model

ProbeChecks = Mapping[str, Callable[[], Awaitable[bool]]]
READINESS_BUDGET_SECONDS = 3.0
HEADERS = {"Cache-Control": "no-store"}
DEPENDENCIES = {
    "frontend": ("menu",),
    "svc-menu": ("postgres",),
    "svc-pedidos": ("postgres", "menu"),
    "svc-lealtad": ("postgres",),
}


class MenuReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service: Literal["svc-menu"]
    status: Literal["ready"]
    checks: dict[Literal["postgres"], Literal["up"]]


async def menu_ready(url: str, *, tracer_provider: TracerProvider | None = None) -> bool:
    import httpx

    async with httpx.AsyncClient(timeout=1.0, follow_redirects=False, trust_env=False) as client:
        if tracer_provider is not None:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

            HTTPXClientInstrumentor.instrument_client(client, tracer_provider=tracer_provider)
        response = await client.get(url.rstrip("/") + "/readyz")
        if response.status_code != 200:
            return False
        if response.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            return False
        result = MenuReadiness.model_validate(response.json())
        return result.checks == {"postgres": "up"}


async def postgres_ready(url: str) -> bool:
    # El frontend no instala Psycopg y nunca necesita este check.
    from psycopg import AsyncConnection

    async with await AsyncConnection.connect(
        url,
        connect_timeout=1,
        options="-c statement_timeout=1000 -c lock_timeout=1000",
        autocommit=True,
        application_name="cafeteria-readiness",
    ) as connection:
        cursor = await connection.execute("SELECT 1")
        return await cursor.fetchone() == (1,)


async def collect_checks(checks: ProbeChecks) -> dict[str, str]:
    result = dict.fromkeys(checks, "down")

    async def run(name: str, check: Callable[[], Awaitable[bool]]) -> None:
        try:
            if await check() is True:
                result[name] = "up"
        except Exception:
            # Una probe devuelve estado sanitizado; nunca detalles de credenciales/SQL.
            result[name] = "down"

    try:
        async with asyncio.timeout(READINESS_BUDGET_SECONDS):
            async with asyncio.TaskGroup() as group:
                for name, check in checks.items():
                    group.create_task(run(name, check))
    except TimeoutError:
        pass
    return result


def install_probes(
    application: FastAPI,
    service: str,
    *,
    database_url: str | None = None,
    menu_url: str | None = None,
    checks: ProbeChecks | None = None,
) -> None:
    if checks is None:
        checks = {}
        if "postgres" in DEPENDENCIES[service]:
            if not database_url:
                raise ValueError("Readiness requiere DATABASE_URL")
            checks["postgres"] = lambda: postgres_ready(database_url)
        if "menu" in DEPENDENCIES[service]:
            if not menu_url:
                raise ValueError("Readiness requiere MENU_URL")
            checks["menu"] = lambda: menu_ready(
                menu_url, tracer_provider=application.state.telemetry.provider
            )
    if set(checks) != set(DEPENDENCIES[service]):
        raise ValueError("Los checks deben coincidir con las dependencias críticas")
    configured_checks = dict(checks)
    lock = asyncio.Lock()
    prefix = {
        "frontend": "frontend",
        "svc-menu": "menu",
        "svc-pedidos": "orders",
        "svc-lealtad": "loyalty",
    }[service]
    live_model = create_model(
        "LivenessResponse",
        __config__=ConfigDict(extra="forbid"),
        service=(Literal[service], ...),
        status=(Literal["alive"], ...),
    )
    check_model = create_model(
        "ReadinessChecks",
        __config__=ConfigDict(extra="forbid"),
        **{name: (Literal["up", "down"], ...) for name in DEPENDENCIES[service]},
    )
    ready_model = create_model(
        "ReadinessResponse",
        __config__=ConfigDict(extra="forbid"),
        service=(Literal[service], ...),
        status=(Literal["ready", "not_ready"], ...),
        checks=(check_model, ...),
    )

    @application.get(
        "/livez", tags=["operación"], operation_id=prefix + "Liveness", response_model=live_model
    )
    async def liveness():
        return JSONResponse({"service": service, "status": "alive"}, headers=HEADERS)

    @application.get(
        "/readyz",
        tags=["operación"],
        operation_id=prefix + "Readiness",
        response_model=ready_model,
        responses={503: {"model": ready_model}},
    )
    async def readiness():
        # No se encolan comprobaciones si una dependencia lenta ya ocupa la probe.
        result = dict.fromkeys(configured_checks, "down")
        if not lock.locked():
            async with lock:
                result = await collect_checks(configured_checks)
        ready = all(value == "up" for value in result.values())
        return JSONResponse(
            {"service": service, "status": "ready" if ready else "not_ready", "checks": result},
            status_code=200 if ready else 503,
            headers=HEADERS,
        )
