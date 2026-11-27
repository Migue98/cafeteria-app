"""Probes sobre procesos, PostgreSQL y HTTP reales en Compose aislado."""

import json
import subprocess
from time import monotonic

import pytest

from .test_failure_recovery import outage as outage

pytestmark = pytest.mark.e2e


def services(api):
    return {
        "frontend": api.frontend_url,
        "svc-menu": api.menu_url,
        "svc-pedidos": api.orders_url,
        "svc-lealtad": api.loyalty_url,
    }


def process_starts(compose_command):
    ids = subprocess.check_output([*compose_command, "ps", "--all", "--quiet"], text=True).split()
    engine = compose_command[: compose_command.index("compose")]
    records = json.loads(subprocess.check_output([*engine, "inspect", *ids], text=True))
    return {
        item["Config"]["Labels"]["com.docker.compose.service"]: item["State"]["StartedAt"]
        for item in records
    }


def test_all_probes_are_available_with_no_session(api):
    for name, url in services(api).items():
        live = api.json("GET", url + "/livez")
        ready = api.json("GET", url + "/readyz")
        assert live.status == ready.status == 200
        assert live.body == {"service": name, "status": "alive"}
        assert ready.body["status"] == "ready"
        assert set(ready.body["checks"].values()) == {"up"}
        assert ready.headers["cache-control"] == "no-store"
        assert api.json("GET", url + "/health").body["status"] == "healthy"


@pytest.mark.parametrize(
    "stopped,paused",
    [
        ("svc-lealtad", False),
        ("svc-pedidos", False),
        ("svc-menu", False),
        ("postgres", False),
        ("postgres", True),
    ],
)
def test_readiness_degrades_and_recovers_without_restarting_survivors(
    api, compose_command, outage, stopped, paused
):
    urls = services(api)
    expected_down = {
        "svc-lealtad": set(),
        "svc-pedidos": set(),
        "svc-menu": {"frontend", "svc-pedidos"},
        "postgres": set(urls),
    }[stopped]
    before = process_starts(compose_command)
    with outage(stopped, paused=paused):
        for name, url in urls.items():
            if name == stopped:
                continue
            assert api.json("GET", url + "/livez").status == 200
            started = monotonic()
            result = api.json("GET", url + "/readyz", timeout=5)
            assert result.status == (503 if name in expected_down else 200), (name, result)
            assert result.body["status"] == ("not_ready" if name in expected_down else "ready")
            assert monotonic() - started < 3.5
        during = process_starts(compose_command)
        assert all(during[name] == value for name, value in before.items() if name != stopped)
    for url in urls.values():
        assert api.json("GET", url + "/readyz").status == 200
