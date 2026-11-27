# Servicio de menú

Microservicio FastAPI responsable del catálogo, precios y disponibilidad. Usa
PostgreSQL como fuente de verdad y carga 20 productos de ejemplo de forma
idempotente al crear la base local. `db/init.sql` crea únicamente el esquema;
`db/seed.sql` agrega los ejemplos sin sobrescribir productos existentes.
Consulta la [inicialización de BD](../docs/database-initialization.md).

Contrato: [`svc-menu.openapi.json`](../docs/openapi/svc-menu.openapi.json).

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/health` | Comprueba el servicio y la conexión con PostgreSQL. |
| `GET` | `/livez` | Comprueba el proceso sin consultar dependencias. |
| `GET` | `/readyz` | 200 con PostgreSQL disponible; 503 si falla. |
| `GET` | `/metrics` | Métricas para Prometheus. |
| `GET` | `/api/v1/products` | Lista y filtra productos con paginación. |
| `GET` | `/api/v1/products/{product_id}` | Obtiene un producto por ID. |
| `GET` | `/docs` | Interfaz OpenAPI generada por FastAPI. |

## Ejecución con Podman

Requiere Podman y un proveedor de Compose (`podman-compose` o Docker Compose).

```bash
cd svc-menu
podman compose up --build
```

El servicio queda disponible en `http://localhost:8001` y la documentación en
`http://localhost:8001/docs`.

Comprobaciones rápidas:

```bash
curl http://localhost:8001/health
curl "http://localhost:8001/api/v1/products?available=true&limit=5"
curl http://localhost:8001/metrics
```

Para eliminar también la base local:

```bash
podman compose down --volumes
```

El usuario y contraseña de `compose.yaml` son exclusivos del entorno local y
no deben reutilizarse en staging o producción.

## Desarrollo sin contenedor de aplicación

Levanta PostgreSQL con Compose y ejecuta FastAPI desde un entorno virtual:

```bash
cd svc-menu
python3.13 -m venv .venv
source .venv/bin/activate  # En PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

La configuración disponible es:

| Variable | Valor local predeterminado |
|---|---|
| `DATABASE_URL` | `postgresql://cafeteria:cafeteria@localhost:5432/cafeteria` |
| `APP_VERSION` | `dev` |

## Validación

```bash
python -m pytest -c pyproject.toml tests ../tests/observability -p no:cacheprovider
ruff check app tests ../tests/observability
ruff format --check app tests ../tests/observability
```

La configuración de pytest está en `pyproject.toml`; Ruff hereda las reglas
comunes de `../ruff.toml`. En Windows se crea el entorno con
`py -3.13 -m venv .venv`. Consulta la
[guía de herramientas](../docs/development-tooling.md).

Las pruebas HTTP usan un repositorio falso; no necesitan PostgreSQL. La
integración real con PostgreSQL se valida al ejecutar `compose.yaml`.

## Decisiones operativas

- Los importes son centavos enteros en MXN.
- `X-Request-ID` se valida o genera y siempre se devuelve.
- Los errores cumplen `application/problem+json`.
- Los logs de petición son JSON e incluyen `request_id` y `trace_id`.
- La imagen usa UID/GID `10001` y no ejecuta el servicio como root.
- `/health` devuelve `503` cuando PostgreSQL no está disponible.
