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

Se admite W3C Trace Context mediante los propagadores de OpenTelemetry; las
respuestas emiten el formato `00`. Cada servicio conserva el `trace_id` y los
flags del padre y crea un span servidor propio. Si el encabezado falta o es
inválido, se inicia una traza nueva. No se aceptan identificadores de solo ceros.
El contexto del servidor se devuelve en la respuesta. Los instrumentadores
crean spans cliente HTTP e inyectan su contexto en las llamadas siguientes.

Los identificadores de logs y errores se obtienen del SDK. Los detalles están
en [Logs y correlación](../application-observability.md) y
[OpenTelemetry](../opentelemetry-tracing.md).

### `Idempotency-Key`

Es obligatorio en operaciones que crean efectos:

- `POST /api/v1/orders`.
- `POST /api/v1/points/earn`.

Repetir una solicitud con la misma clave y el mismo cuerpo devuelve el resultado original sin duplicar datos. Reutilizar la clave con otro cuerpo produce `409 IDEMPOTENCY_KEY_REUSED`.

Lealtad también devuelve el movimiento original cuando un pedido se repite con
otra clave y los mismos datos. Esa clave alterna queda reservada al movimiento
original; no podrá usarse después para acreditar otro pedido. Las reservas
concurrentes se resuelven de forma atómica en PostgreSQL.

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

Las rutas `/livez` y `/readyz` están implementadas en los cuatro componentes.
Sus respuestas, límites y matriz de dependencias están en el
[contrato de salud](../health-contract.md). La respuesta 503 de readiness usa
`application/json` con sus checks, como excepción operativa a los errores de
negocio. Esta sección describe el diagnóstico conservado de los backends; el
frontend conserva HTTP 200 con `degraded` cuando falla alguno de sus backends.

`GET /health` devuelve:

- `200`: el servicio puede atender su función principal; puede indicar `degraded` si falla una dependencia no crítica.
- `503`: una dependencia crítica impide atender solicitudes.

Dependencias críticas:

- Menú: PostgreSQL.
- Pedidos: PostgreSQL y menú.
- Lealtad: PostgreSQL.

Lealtad es no crítica para confirmar un pedido: si falla, el pedido se guarda con `loyalty_status=pending`.

Los timeouts y las respuestas inválidas de una dependencia siguen la misma
clasificación: menú es crítico y rechaza la creación con 503; lealtad conserva
el pedido confirmado y pendiente. Pedidos valida la identidad del producto y
de la acreditación, además de sus importes/puntos, antes de utilizar la respuesta.
Los escenarios están descritos en [Fallas y recuperación](../failure-recovery.md).

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
