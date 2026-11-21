# Servicio de lealtad

Las claves de idempotencia, incluidas las utilizadas para repetir un movimiento,
se reservan en `loyalty_request_keys`. Si tienes un volumen con datos existentes,
aplica el script idempotente antes de iniciar la nueva versión; consulta la
[migración y las garantías de concurrencia](../docs/concurrency-and-idempotency.md).

Microservicio FastAPI responsable del libro de movimientos y del saldo de
puntos por cliente. Una falla temporal de este servicio nunca elimina ni
revierte un pedido confirmado.

Contrato: [`svc-lealtad.openapi.json`](../docs/openapi/svc-lealtad.openapi.json).

## Regla de puntos

Se acredita un punto por cada 1000 centavos —$10 MXN completos— usando división
entera:

```text
points_earned = floor(amount_cents / 1000)
```

Cada `order_id` solo puede originar un movimiento. `Idempotency-Key` también es
única; repetir el mismo cuerpo devuelve la acreditación original con
`replayed=true`, mientras que cambiar los datos produce HTTP 409.

## Modelo de datos

```text
loyalty_accounts 1 ───── N loyalty_movements
```

- `loyalty_accounts` conserva el saldo actual por cliente.
- `loyalty_movements` es el libro inmutable de acreditaciones.
- El movimiento y la actualización del saldo ocurren en una transacción.
- Se almacena `balance_after` para que un replay devuelva el resultado original.

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/health` | Comprueba la conexión con PostgreSQL. |
| `GET` | `/metrics` | Métricas HTTP y de puntos para Prometheus. |
| `POST` | `/api/v1/points/earn` | Acredita puntos de forma idempotente. |
| `GET` | `/api/v1/customers/{customer_id}/points` | Consulta el saldo; clientes nuevos obtienen cero. |

## Ejecución con Podman

```bash
cd svc-lealtad
podman compose up --build
```

El servicio queda en `http://localhost:8003` y su OpenAPI interactivo en
`http://localhost:8003/docs`.

Ejemplo:

```bash
curl -X POST http://localhost:8003/api/v1/points/earn \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-loyalty-001" \
  -d '{"order_id":"22222222-2222-4222-8222-222222222222","customer_id":"11111111-1111-4111-8111-111111111111","amount_cents":10900,"currency":"MXN"}'
```

Para retirar el entorno local y sus datos regenerables:

```bash
podman compose down --volumes
```

## Desarrollo y validación

```bash
cd svc-lealtad
python -m venv .venv
source .venv/bin/activate  # En PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -p no:cacheprovider
ruff check app tests
ruff format --check app tests
```

Variables:

| Variable | Predeterminado |
|---|---|
| `DATABASE_URL` | PostgreSQL local `cafeteria` |
| `APP_VERSION` | `dev` |

Las credenciales del Compose son únicamente para desarrollo local.
