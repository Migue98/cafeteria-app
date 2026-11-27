"""Levanta un Compose aislado, ejecuta la suite E2E y limpia sus recursos."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = os.getenv("E2E_COMPOSE_PROJECT", "cafeteria-e2e")
ENGINE = shlex.split(os.getenv("CONTAINER_ENGINE", "docker"))
COMPOSE_FILE = ROOT / "compose.yaml"
COMPOSE = [*ENGINE, "compose", "-p", PROJECT, "-f", str(COMPOSE_FILE)]


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    print(f"+ {shlex.join(command)}", flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("all", "http", "browser"), default="all")
    args = parser.parse_args()
    compose_env = os.environ.copy()
    compose_env.update(
        {
            "FRONTEND_PORT": os.getenv("E2E_FRONTEND_PORT", "18000"),
            "MENU_PORT": os.getenv("E2E_MENU_PORT", "18001"),
            "ORDERS_PORT": os.getenv("E2E_ORDERS_PORT", "18002"),
            "LOYALTY_PORT": os.getenv("E2E_LOYALTY_PORT", "18003"),
            "OTEL_TRACES_EXPORTER": "console",
            "OTEL_TRACES_SAMPLER": "parentbased_always_on",
            "OTEL_BSP_SCHEDULE_DELAY": "100",
            "LOYALTY_RETRY_INTERVAL_SECONDS": os.getenv("E2E_LOYALTY_RETRY_INTERVAL_SECONDS", "2"),
        }
    )
    test_env = compose_env.copy()
    test_env.update(
        {
            "E2E_FRONTEND_URL": f"http://localhost:{compose_env['FRONTEND_PORT']}",
            "E2E_MENU_URL": f"http://localhost:{compose_env['MENU_PORT']}",
            "E2E_ORDERS_URL": f"http://localhost:{compose_env['ORDERS_PORT']}",
            "E2E_LOYALTY_URL": f"http://localhost:{compose_env['LOYALTY_PORT']}",
            "E2E_CONTAINER_ENGINE": " ".join(ENGINE),
            "E2E_COMPOSE_PROJECT": PROJECT,
            "E2E_COMPOSE_FILE": str(COMPOSE_FILE),
        }
    )

    try:
        run([sys.executable, str(ROOT / "scripts" / "validate_contracts.py")])
        run([*COMPOSE, "up", "--build", "--detach"], env=compose_env)
        if args.suite in {"all", "http"}:
            run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-c",
                    "pytest.ini",
                    "tests/e2e",
                    "-m",
                    "e2e",
                    "-v",
                ],
                env=test_env,
            )
        if args.suite in {"all", "browser"}:
            run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-c",
                    "pytest.ini",
                    "tests/browser",
                    "-m",
                    "browser",
                    "-v",
                    "--browser",
                    "chromium",
                    "--tracing",
                    "retain-on-failure",
                    "--screenshot",
                    "only-on-failure",
                    "--full-page-screenshot",
                    "--output",
                    "test-results/browser",
                ],
                env=test_env,
            )
    except subprocess.CalledProcessError as exc:
        return exc.returncode or 1
    finally:
        if os.getenv("KEEP_E2E_STACK") != "1":
            try:
                run([*COMPOSE, "down", "--volumes", "--remove-orphans"], env=compose_env)
            except subprocess.CalledProcessError:
                print(
                    "No fue posible limpiar el stack E2E automáticamente.",
                    file=sys.stderr,
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
