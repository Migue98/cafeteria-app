# Validación de locks de dependencias

- **Fecha:** 20 de noviembre de 2026.
- **Python local:** 3.13.1.
- **Generador:** `pip-tools==7.5.2`.
- **Docker Engine:** 28.4.0.
- **Docker Compose:** 2.39.2-desktop.1.

## Artefactos generados

Se generaron nueve locks con versiones exactas y hashes:

- runtime y desarrollo de `frontend`;
- runtime y desarrollo de `svc-menu`;
- runtime y desarrollo de `svc-pedidos`;
- runtime y desarrollo de `svc-lealtad`;
- dependencias de la suite E2E.

Cada conjunto se instaló desde cero en Python 3.13. `pip check` no encontró
dependencias rotas. Los workflows de CI ahora instalan juntos el lock de
runtime y el de desarrollo.

## Regresión local

| Componente | Lint y formato | Pruebas |
|---|---:|---:|
| Frontend | Correcto | 8 |
| Menú | Correcto | 11 |
| Pedidos | Correcto | 15 |
| Lealtad | Correcto | 13 |
| **Total unitarias** | **Correcto** | **47** |

Los tres contratos OpenAPI también pasaron su validador.

FastAPI 0.165.0 y Ruff 0.17.6 quedaron confirmados como línea común para los
cuatro componentes. Starlette muestra una advertencia de deprecación al usar
su `TestClient` basado en HTTPX; no provoca fallos y se revisará en una
actualización de dependencias separada.

## Contenedores y E2E

Compose construyó correctamente las cuatro imágenes de aplicación desde sus
locks en Linux. Después levantó PostgreSQL y los servicios reales. Pasaron las
nueve pruebas E2E:

- salud y correlación de solicitudes;
- compra completa y cálculo de puntos;
- compra desde la interfaz e historial;
- idempotencia y conflictos;
- validaciones de productos;
- métricas técnicas y de negocio;
- persistencia después de reiniciar PostgreSQL.

Resultado: `9 passed in 6.11s`.

Al terminar se eliminaron los contenedores, la red y el volumen temporal del
proyecto Compose `cafeteria-e2e`.

## Reproducción

Para regenerar los locks deliberadamente:

```powershell
python -m pip install pip-tools==7.5.2
python scripts/compile_requirements.py
```

Para repetir la regresión integral:

```powershell
python -m pip install -r tests/requirements.txt
python scripts/run_e2e.py
```

Decisión relacionada:
[`ADR-003 — Dependencias reproducibles`](decisions/ADR-003-reproducible-dependencies.md).
