# Servicio de pedidos

Microservicio FastAPI responsable de validar productos, calcular importes,
persistir pedidos y coordinar la acreditación de puntos. PostgreSQL y
`svc-menu` son dependencias críticas; `svc-lealtad` es no crítica.

Contrato: [`svc-pedidos.openapi.json`](../docs/openapi/svc-pedidos.openapi.json).

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/health` | Salud de PostgreSQL, menú y lealtad. |
| `GET` | `/metrics` | Métricas Prometheus HTTP y de negocio. |
| `POST` | `/api/v1/orders` | Crea un pedido de forma idempotente. |
| `GET` | `/api/v1/orders` | Lista pedidos de un cliente. |
| `GET` | `/api/v1/orders/{order_id}` | Consulta un pedido. |
| `POST` | `/api/v1/orders/{order_id}/loyalty/retry` | Reintenta puntos pendientes. |

## Regla de consistencia

El servicio obtiene nombre, SKU, disponibilidad y precio desde `svc-menu`; no
confía en precios enviados por el navegador. Después guarda el pedido como
confirmado y solicita los puntos. Si lealtad falla, responde con el pedido
confirmado y `loyalty_status=pending`, que puede recuperarse posteriormente con
el endpoint de reintento.

`Idempotency-Key` evita pedidos duplicados. Repetir la misma solicitud devuelve
el pedido original con HTTP 200 y `replayed=true`; reutilizar la clave con otro
cuerpo devuelve HTTP 409.

## Ejecución con Podman

El Compose local levanta PostgreSQL, `svc-menu` y `svc-pedidos`. Lealtad se deja
intencionalmente fuera para demostrar que el pedido se conserva como pendiente.

```bash
cd svc-pedidos
podman compose up --build
```

Servicios:

- Menú: `http://localhost:8001`
- Pedidos: `http://localhost:8002`
- OpenAPI: `http://localhost:8002/docs`

Ejemplo:

```bash
curl -X POST http://localhost:8002/api/v1/orders \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-order-001" \
  -d '{"customer_id":"11111111-1111-4111-8111-111111111111","items":[{"product_id":1,"quantity":2}]}'
```

Para retirar el entorno local y su base regenerable:

```bash
podman compose down --volumes
```

## Desarrollo y validación

```bash
cd svc-pedidos
python -m venv .venv
source .venv/bin/activate  # En PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest -p no:cacheprovider
ruff check app tests
ruff format --check app tests
```

Variables disponibles:

| Variable | Predeterminado |
|---|---|
| `DATABASE_URL` | PostgreSQL local `cafeteria` |
| `MENU_URL` | `http://localhost:8001` |
| `LOYALTY_URL` | `http://localhost:8003` |
| `HTTP_TIMEOUT_SECONDS` | `3` |
| `APP_VERSION` | `dev` |

Las credenciales del Compose son únicamente para desarrollo local.
