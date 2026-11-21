"""Regenera todos los locks de Python de forma consistente."""

from __future__ import annotations

import os
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

PIP_TOOLS_VERSION = "7.5.2"
PYPI_INDEX = "https://pypi.org/simple"
ROOT = Path(__file__).resolve().parents[1]

LOCKS = (
    ("frontend", "requirements.in", "requirements.txt"),
    ("frontend", "requirements-dev.in", "requirements-dev.txt"),
    ("svc-menu", "requirements.in", "requirements.txt"),
    ("svc-menu", "requirements-dev.in", "requirements-dev.txt"),
    ("svc-pedidos", "requirements.in", "requirements.txt"),
    ("svc-pedidos", "requirements-dev.in", "requirements-dev.txt"),
    ("svc-lealtad", "requirements.in", "requirements.txt"),
    ("svc-lealtad", "requirements-dev.in", "requirements-dev.txt"),
    ("tests", "requirements.in", "requirements.txt"),
)


def ensure_tool_version() -> None:
    try:
        installed = version("pip-tools")
    except PackageNotFoundError as exc:
        raise SystemExit(
            f"Falta pip-tools. Instálalo con: pip install pip-tools=={PIP_TOOLS_VERSION}"
        ) from exc

    if installed != PIP_TOOLS_VERSION:
        raise SystemExit(
            f"Se requiere pip-tools=={PIP_TOOLS_VERSION}; está instalado {installed}."
        )


def compile_lock(component: str, source: str, target: str) -> None:
    command_for_header = (
        "pip-compile --generate-hashes --strip-extras "
        f"--resolver=backtracking --output-file={target} {source}"
    )
    environment = os.environ.copy()
    environment.pop("PIP_NO_INDEX", None)
    environment["CUSTOM_COMPILE_COMMAND"] = command_for_header

    command = (
        sys.executable,
        "-m",
        "piptools",
        "compile",
        "--quiet",
        "--no-config",
        "--upgrade",
        f"--index-url={PYPI_INDEX}",
        "--generate-hashes",
        "--strip-extras",
        "--resolver=backtracking",
        f"--output-file={target}",
        source,
    )

    print(f"Generando {component}/{target} desde {source}...")
    subprocess.run(
        command,
        cwd=ROOT / component,
        env=environment,
        check=True,
    )


def main() -> None:
    if sys.version_info[:2] != (3, 13):
        raise SystemExit("Los locks deben generarse con Python 3.13.")

    ensure_tool_version()
    for lock in LOCKS:
        compile_lock(*lock)

    print("Locks generados correctamente.")


if __name__ == "__main__":
    main()
