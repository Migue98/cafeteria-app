"""Validación mínima, sin dependencias, de los contratos OpenAPI locales."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "docs" / "openapi"


def resolve_pointer(document: dict[str, Any], pointer: str) -> Any:
    value: Any = document
    for raw_part in pointer.removeprefix("#/").split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        value = value[part]
    return value


def walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{path.name}: JSON inválido: {error}"]

    if not str(document.get("openapi", "")).startswith("3.1."):
        errors.append(f"{path.name}: se esperaba OpenAPI 3.1.x")
    if not document.get("info", {}).get("title"):
        errors.append(f"{path.name}: falta info.title")
    if not document.get("paths"):
        errors.append(f"{path.name}: no contiene paths")

    operation_ids: set[str] = set()
    for route, path_item in document.get("paths", {}).items():
        if route not in {"/health", "/metrics", "/livez", "/readyz"} and not route.startswith(
            "/api/v1/"
        ):
            errors.append(f"{path.name}: ruta sin versión: {route}")
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            operation_id = operation.get("operationId")
            if not operation_id:
                errors.append(f"{path.name}: {method.upper()} {route} sin operationId")
            elif operation_id in operation_ids:
                errors.append(f"{path.name}: operationId duplicado: {operation_id}")
            else:
                operation_ids.add(operation_id)
            if not operation.get("responses"):
                errors.append(f"{path.name}: {method.upper()} {route} sin responses")

    for node in walk(document):
        reference = node.get("$ref")
        if not reference:
            continue
        if not reference.startswith("#/"):
            errors.append(f"{path.name}: referencia externa no permitida: {reference}")
            continue
        try:
            resolve_pointer(document, reference)
        except (KeyError, TypeError):
            errors.append(f"{path.name}: referencia inexistente: {reference}")
    return errors


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    paths = sorted(CONTRACTS.glob("*.openapi.json"))
    if not paths:
        print("No se encontraron contratos.", file=sys.stderr)
        return 1
    errors = [error for path in paths for error in validate(path)]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Contratos válidos: {len(paths)}")
    for path in paths:
        print(f"- {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
