# Recuperación automática de puntos pendientes

- **Implementado:** 21 de noviembre de 2026.
- **Responsable:** `svc-pedidos`.

## Comportamiento

Un pedido se confirma incluso si `svc-lealtad` no está disponible. En ese caso
se conserva con `loyalty_status=pending` y `points_earned=null`.

`svc-pedidos` inicia un trabajador junto con la aplicación. El trabajador:

1. ejecuta un lote inmediatamente al arrancar;
2. consulta los pedidos pendientes más antiguos;
3. intenta acreditar cada pedido sin detener el lote cuando uno falla;
4. vuelve a ejecutarse cada 900 segundos;
5. se cancela ordenadamente cuando termina la aplicación.

El endpoint manual `POST /api/v1/orders/{order_id}/loyalty/retry` se conserva
para operación y diagnóstico, pero ya no es necesario para la recuperación
normal.

## Idempotencia y concurrencia

Cada llamada a `svc-lealtad` usa el UUID del pedido como `Idempotency-Key`.
Reintentar después de una respuesta perdida o desde dos réplicas no duplica el
movimiento de puntos. Cuando lealtad confirma la acreditación, pedidos actualiza
el registro a `loyalty_status=awarded`.

La consulta se limita por lote y usa el índice parcial
`orders_loyalty_pending_idx`. Varias réplicas podrían seleccionar el mismo
pedido, pero la idempotencia en lealtad mantiene el resultado correcto.

## Configuración

| Variable | Predeterminado | Función |
|---|---:|---|
| `LOYALTY_RETRY_ENABLED` | `true` | Habilita el trabajador. |
| `LOYALTY_RETRY_INTERVAL_SECONDS` | `900` | Espera entre lotes. |
| `LOYALTY_RETRY_BATCH_SIZE` | `100` | Máximo de pedidos por lote. |

Los valores de intervalo y lote deben ser mayores que cero. La suite E2E reduce
el intervalo a dos segundos únicamente dentro de su proyecto Compose aislado.

## Observabilidad

- `cafe_loyalty_pending_orders`: cantidad pendiente observada por el último lote.
- `cafe_loyalty_retry_attempts_total{outcome="awarded"}`: acreditaciones recuperadas.
- `cafe_loyalty_retry_attempts_total{outcome="loyalty_unavailable"}`: dependencia caída.
- `cafe_loyalty_retry_attempts_total{outcome="repository_unavailable"}`: fallo al actualizar PostgreSQL.

Cada intento escribe un evento con `order_id`, `request_id`, `trace_id` y
`span_id`, y propaga el contexto a lealtad. Se utiliza el
[formato común de logs](application-observability.md).

OpenTelemetry crea una traza por lote y un span hijo por intento. Las llamadas
HTTP y consultas SQL se instrumentan con el mismo proveedor del servicio.
Al apagar la aplicación se espera el hilo del lote activo antes de cerrar
clientes y exportadores. Consulta la [guía de trazas](opentelemetry-tracing.md).

## Validación

- Ruff y formato: correctos.
- Contratos OpenAPI: 3 válidos.
- Pruebas unitarias de pedidos: `17 passed`.
- Suite integral: `10 passed in 15.25s`.
- La prueba integral apaga lealtad, crea un pedido pendiente, restaura el
  servicio y verifica tanto el pedido acreditado como el saldo sin llamar al
  endpoint manual.

Los contenedores, la red y el volumen E2E se eliminaron al terminar.
