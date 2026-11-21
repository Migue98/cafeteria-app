# Convenciones de los contratos

## Direcciones y versiones

| Servicio | Desarrollo local | DNS interno en Kubernetes |
|---|---|---|
| Menú | `http://localhost:8001` | `http://svc-menu:8001` |
| Pedidos | `http://localhost:8002` | `http://svc-pedidos:8002` |
| Lealtad | `http://localhost:8003` | `http://svc-lealtad:8003` |

Las rutas de negocio empiezan con `/api/v1`. Los endpoints `/health` y `/metrics` no se versionan.

## Identificadores, importes y fechas

- Productos: entero positivo asignado por `svc-menu`.
- Clientes, pedidos y movimientos: UUID.
- Moneda: exclusivamente MXN durante el MVP.
- Importes: enteros en centavos, por ejemplo `$55.00` se representa como `5500`.
- Fechas: RFC 3339 en UTC, por ejemplo `2026-11-11T20:15:30Z`.
- Cantidades: enteros entre 1 y 20 por partida.

No se usan números de punto flotante para dinero.

## Encabezados

### `X-Request-ID`

El cliente puede enviarlo. Si falta, el primer servicio genera un UUID. Todos los servicios lo propagan y lo devuelven en la respuesta.

### `traceparent`

Se admite el formato W3C Trace Context de versión `00`. Cada servicio conserva
el `trace_id` y los flags, genera su propio `span_id` y registra el span recibido
como `parent_span_id`. Si el encabezado falta o es inválido, se inicia una traza
nueva. No se aceptan identificadores de solo ceros. El contexto del servicio se
devuelve en la respuesta y se propaga a sus llamadas HTTP.

Actualmente la correlación se implementa en la aplicación, sin SDK ni exportador
de OpenTelemetry. Los detalles están en [Logs y correlación](../application-observability.md).

### `Idempotency-Key`

Es obligatorio en operaciones que crean efectos:

- `POST /api/v1/orders`.
- `POST /api/v1/points/earn`.

Repetir una solicitud con la misma clave y el mismo cuerpo devuelve el resultado original sin duplicar datos. Reutilizar la clave con otro cuerpo produce `409 IDEMPOTENCY_KEY_REUSED`.

## Errores

Los errores usan `application/problem+json`:

```json
{
  "type": "https://cafeteria.example/problems/product-unavailable",
  "title": "Producto no disponible",
  "status": 409,
  "detail": "El producto 7 no puede incluirse en el pedido.",
  "code": "PRODUCT_UNAVAILABLE",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "instance": "/api/v1/orders"
}
```

El cliente decide por `status` y `code`, nunca analizando el texto de `detail`. No se exponen excepciones, SQL, credenciales o rutas internas.

## Salud

`GET /health` devuelve:

- `200`: el servicio puede atender su función principal; puede indicar `degraded` si falla una dependencia no crítica.
- `503`: una dependencia crítica impide atender solicitudes.

Dependencias críticas:

- Menú: PostgreSQL.
- Pedidos: PostgreSQL y menú.
- Lealtad: PostgreSQL.

Lealtad es no crítica para confirmar un pedido: si falla, el pedido se guarda con `loyalty_status=pending`.

## Reglas de negocio fijadas

- El precio válido es el devuelto por `svc-menu`, nunca el enviado por el navegador.
- Productos repetidos en una solicitud se rechazan con `422`; el frontend debe consolidarlos.
- Solo se aceptan productos disponibles.
- Un pedido confirmado no se elimina si falla lealtad.
- Lealtad otorga `floor(amount_cents / 1000)` puntos: un punto por cada $10 MXN completos.
- `order_id` es único en lealtad, por lo que un pedido no puede acreditar puntos dos veces.

## Métricas

Todos los backends publican:

```text
http_requests_total{service,method,route,status_code}
http_request_duration_seconds{service,method,route}
```

Pedidos publica:

```text
cafe_orders_total{status}
cafe_order_value_cents_total
```

Lealtad publica:

```text
cafe_loyalty_points_total
cafe_loyalty_awards_total{status}
```

Los pedidos por minuto son una consulta de Prometheus, no un contador independiente:

```promql
sum(increase(cafe_orders_total{status="confirmed"}[1m]))
```
