"""Valida métricas y, opcionalmente, logs/trazas con datos Compose desechables."""

from __future__ import annotations

import argparse
import os
import secrets
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "cafeteria-monitoring-e2e"
ENGINE = shlex.split(os.getenv("CONTAINER_ENGINE", "docker"))
COMPOSE = [
    *ENGINE,
    "compose",
    "-p",
    PROJECT,
    "-f",
    str(ROOT / "compose.yaml"),
    "-f",
    str(ROOT / "compose.monitoring.yaml"),
]


def run(command: list[str], env: dict[str, str]) -> None:
    print(f"+ {shlex.join(command)}", flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--telemetry", action="store_true", help="Incluye Alloy, Loki y Tempo")
    parser.add_argument(
        "--alerts", action="store_true", help="Prueba alertas con un webhook interno"
    )
    args = parser.parse_args()
    compose = [*COMPOSE]
    if args.telemetry:
        compose.extend(["-f", str(ROOT / "compose.telemetry.yaml")])
    if args.alerts:
        compose.extend(["-f", str(ROOT / "tests/monitoring/compose.alerts.yaml")])
    environment = os.environ.copy()
    ports = {
        "FRONTEND_PORT": "28000",
        "MENU_PORT": "28001",
        "ORDERS_PORT": "28002",
        "LOYALTY_PORT": "28003",
        "PROMETHEUS_PORT": "19090",
        "GRAFANA_PORT": "13000",
        "LOKI_PORT": "13100",
        "TEMPO_PORT": "13200",
        "ALLOY_PORT": "12346",
        "ALERT_RECEIVER_PORT": "13080",
    }
    environment.update(
        {key: os.getenv(f"MONITORING_E2E_{key}", default) for key, default in ports.items()}
    )
    environment.update(
        {
            "GRAFANA_ADMIN_USER": "monitoring-test",
            "GRAFANA_ADMIN_PASSWORD": secrets.token_urlsafe(32),
            "SESSION_SECRET": secrets.token_urlsafe(48),
            "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
            "APP_ENV": "development",
            "SESSION_HTTPS_ONLY": "false",
            "PUBLIC_ORIGIN": "",
            "ALLOWED_HOSTS": "localhost,127.0.0.1,[::1]",
            "OTEL_TRACES_EXPORTER": "none",
            "LOYALTY_RETRY_INTERVAL_SECONDS": "2",
            "E2E_FRONTEND_URL": f"http://localhost:{environment['FRONTEND_PORT']}",
            "E2E_MENU_URL": f"http://localhost:{environment['MENU_PORT']}",
            "E2E_ORDERS_URL": f"http://localhost:{environment['ORDERS_PORT']}",
            "E2E_LOYALTY_URL": f"http://localhost:{environment['LOYALTY_PORT']}",
            "E2E_PROMETHEUS_URL": f"http://localhost:{environment['PROMETHEUS_PORT']}",
            "E2E_GRAFANA_URL": f"http://localhost:{environment['GRAFANA_PORT']}",
            "E2E_LOKI_URL": f"http://localhost:{environment['LOKI_PORT']}",
            "E2E_TEMPO_URL": f"http://localhost:{environment['TEMPO_PORT']}",
            "E2E_ALLOY_URL": f"http://localhost:{environment['ALLOY_PORT']}",
            "E2E_TELEMETRY": "1" if args.telemetry else "0",
            "E2E_ALERTS": "1" if args.alerts else "0",
            "E2E_ALERT_RECEIVER_URL": f"http://localhost:{environment['ALERT_RECEIVER_PORT']}",
            "OTEL_TRACES_SAMPLER": "parentbased_always_on",
            "OTEL_BSP_SCHEDULE_DELAY": "100",
            "E2E_CONTAINER_ENGINE": shlex.join(ENGINE),
            "E2E_COMPOSE_PROJECT": PROJECT,
            "E2E_COMPOSE_FILE": str(ROOT / "compose.yaml"),
        }
    )
    if args.alerts:
        environment.update(
            {
                "ALERT_SERVICE_DOWN_FOR": "20s",
                "ALERT_HTTP_ERRORS_FOR": "20s",
                "ALERT_LOYALTY_PENDING_FOR": "20s",
            }
        )
    suites = ["tests/monitoring/test_monitoring.py", "tests/monitoring/test_dashboards.py"]
    if args.telemetry:
        suites.append("tests/monitoring/test_telemetry.py")
    if args.alerts:
        suites.append("tests/monitoring/test_alerts.py")
    try:
        run([*compose, "config", "--quiet"], environment)
        run(
            [
                *compose,
                "run",
                "--rm",
                "--no-deps",
                "--entrypoint",
                "promtool",
                "prometheus",
                "check",
                "config",
                "/etc/prometheus/prometheus.yml",
            ],
            environment,
        )
        if args.telemetry:
            validators = [
                ["alloy", "validate", "/etc/alloy/config.alloy"],
                ["loki", "-config.file=/etc/loki/local.yaml", "-verify-config=true"],
                [
                    "tempo",
                    "-config.file=/etc/tempo/local.yaml",
                    "-target=all",
                    "-config.verify=true",
                ],
            ]
            for validator in validators:
                run([*compose, "run", "--rm", "--no-deps", *validator], environment)
        run([*compose, "up", "--build", "--detach"], environment)
        run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-c",
                "pytest.ini",
                *suites,
                "-m",
                "monitoring",
                "-v",
                "--browser",
                "chromium",
                "--tracing",
                "retain-on-failure",
                "--screenshot",
                "only-on-failure",
                "--full-page-screenshot",
                "--output",
                "test-results/monitoring",
            ],
            environment,
        )
    except subprocess.CalledProcessError as exc:
        return exc.returncode or 1
    finally:
        if os.getenv("KEEP_MONITORING_STACK") != "1":
            run([*compose, "down", "--volumes", "--remove-orphans"], environment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
