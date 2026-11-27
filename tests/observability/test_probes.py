"""Contrato y fallas de probes, ejecutado en los cuatro entornos independientes."""

import ast
import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic

import httpx
import pytest
from fastapi.testclient import TestClient

from app import probes
from app.main import LOGGER, create_app

SERVICE = LOGGER.name
CRITICAL = probes.DEPENDENCIES[SERVICE]


@pytest.fixture(autouse=True)
def isolate_probe_unit_tests(monkeypatch):
    # La recuperación real del worker se verifica en API/E2E, no con DB externa aquí.
    monkeypatch.setenv("LOYALTY_RETRY_ENABLED", "false")


def checks_for(states):
    def make_check(name):
        async def check():
            value = states[name]
            if isinstance(value, Exception):
                raise value
            return value

        return check

    return {name: make_check(name) for name in CRITICAL}


def test_liveness_never_calls_dependencies(telemetry):
    async def forbidden():
        raise AssertionError("Liveness must not query a dependency")

    app = create_app(telemetry=telemetry[0], readiness_checks=dict.fromkeys(CRITICAL, forbidden))
    response = TestClient(app).get("/livez")
    assert response.status_code == 200
    assert response.json() == {"service": SERVICE, "status": "alive"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["traceparent"]
    assert response.headers["x-request-id"]


@pytest.mark.parametrize("failed", [None, *CRITICAL])
def test_readiness_only_checks_critical_dependencies_and_recovers(telemetry, failed):
    states = dict.fromkeys(CRITICAL, True)
    app = create_app(telemetry=telemetry[0], readiness_checks=checks_for(states))
    client = TestClient(app)
    if failed:
        states[failed] = RuntimeError("secret-dsn-must-not-leak")
    response = client.get("/readyz")
    assert response.status_code == (503 if failed else 200)
    assert response.json() == {
        "service": SERVICE,
        "status": "not_ready" if failed else "ready",
        "checks": {name: "down" if name == failed else "up" for name in CRITICAL},
    }
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["cache-control"] == "no-store"
    assert "secret-dsn" not in response.text
    assert client.get("/livez").status_code == 200
    states.update(dict.fromkeys(CRITICAL, True))
    assert client.get("/readyz").status_code == 200


def test_timeout_cancels_work_and_recovers_without_pending_tasks(telemetry, monkeypatch):
    monkeypatch.setattr(probes, "READINESS_BUDGET_SECONDS", 0.05)
    active = set()
    blocked = True

    def make_check(name):
        async def check():
            active.add(name)
            try:
                if blocked:
                    await asyncio.sleep(60)
                return True
            finally:
                active.remove(name)

        return check

    app = create_app(
        telemetry=telemetry[0], readiness_checks={name: make_check(name) for name in CRITICAL}
    )
    with TestClient(app) as client:
        for _ in range(3):
            started = monotonic()
            response = client.get("/readyz")
            assert response.status_code == 503
            assert monotonic() - started < 1
            assert set(response.json()["checks"].values()) == {"down"}
            assert not active
        blocked = False
        assert client.get("/readyz").status_code == 200


def test_concurrent_probes_do_not_queue_and_liveness_stays_responsive(telemetry):
    started = threading.Event()
    calls = 0

    async def check():
        nonlocal calls
        calls += 1
        started.set()
        await asyncio.sleep(0.5)
        return True

    app = create_app(telemetry=telemetry[0], readiness_checks=dict.fromkeys(CRITICAL, check))
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(client.get, "/readyz")
        assert started.wait(timeout=2)
        response = client.get("/readyz")
        assert response.status_code == 503
        assert client.get("/livez").status_code == 200
        assert first.result(timeout=3).status_code == 200
        assert calls == len(CRITICAL)
        assert client.get("/readyz").status_code == 200


@pytest.mark.parametrize(
    "status,payload,media",
    [
        (
            200,
            {"service": "svc-menu", "status": "ready", "checks": {"postgres": "up"}},
            "application/json",
        ),
        (
            503,
            {"service": "svc-menu", "status": "ready", "checks": {"postgres": "up"}},
            "application/json",
        ),
        (200, {"service": "svc-menu", "status": "ready", "checks": {}}, "application/json"),
        (
            200,
            {"service": "svc-pedidos", "status": "ready", "checks": {"postgres": "up"}},
            "application/json",
        ),
        (
            200,
            {"service": "svc-menu", "status": "degraded", "checks": {"postgres": "up"}},
            "application/json",
        ),
        (
            200,
            {"service": "svc-menu", "status": "ready", "checks": {"postgres": "down"}},
            "application/json",
        ),
        (302, {}, "application/json"),
        (
            200,
            {"service": "svc-menu", "status": "ready", "checks": {"postgres": "up"}},
            "text/html",
        ),
        (200, "invalid json", "application/json"),
    ],
)
def test_menu_probe_validates_remote_contract_without_retry(monkeypatch, status, payload, media):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            content=b"invalid json" if isinstance(payload, str) else json.dumps(payload).encode(),
            headers={"content-type": media},
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )

    async def check():
        try:
            return await probes.menu_ready("http://menu.internal:8001/")
        except Exception:
            return False

    valid = (
        status == 200
        and media == "application/json"
        and payload == {"service": "svc-menu", "status": "ready", "checks": {"postgres": "up"}}
    )
    assert asyncio.run(check()) is valid
    assert len(calls) == 1
    assert calls[0].url.path == "/readyz"


def test_generated_openapi_agrees_with_probe_contract(telemetry):
    states = dict.fromkeys(CRITICAL, True)
    app = create_app(telemetry=telemetry[0], readiness_checks=checks_for(states))
    generated = app.openapi()
    if SERVICE != "frontend":
        path = Path(__file__).resolve().parents[2] / "docs/openapi" / f"{SERVICE}.openapi.json"
        declared = json.loads(path.read_text(encoding="utf-8"))
        for route in ("/livez", "/readyz"):
            assert (
                generated["paths"][route]["get"]["operationId"]
                == declared["paths"][route]["get"]["operationId"]
            )
        assert set(generated["components"]["schemas"]["ReadinessChecks"]["required"]) == set(
            declared["components"]["schemas"]["ReadinessChecks"]["required"]
        )
    assert set(generated["paths"]["/readyz"]["get"]["responses"]) >= {"200", "503"}
    assert (
        generated["components"]["schemas"]["LivenessResponse"]["properties"]["service"]["const"]
        == SERVICE
    )


def test_probe_modules_stay_identical_across_independent_images():
    root = Path(__file__).resolve().parents[2]
    modules = [
        ast.dump(ast.parse((root / service / "app/probes.py").read_text(encoding="utf-8")))
        for service in probes.DEPENDENCIES
    ]
    assert len(set(modules)) == 1
