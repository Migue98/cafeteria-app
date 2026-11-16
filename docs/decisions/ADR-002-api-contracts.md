# ADR-002 — Contratos HTTP del MVP

- **Estado:** aceptado.
- **Fecha:** 11 de noviembre de 2026.

## Contexto

Frontend, menú, pedidos y lealtad se desarrollarán y desplegarán de manera independiente. Necesitan reglas estables para intercambiar precios, identificadores, errores y contexto de trazas sin acoplarse a detalles internos.

## Decisión

- OpenAPI 3.1 es la fuente de verdad de los tres backends.
- Las rutas de negocio usan `/api/v1`; salud y métricas permanecen en `/health` y `/metrics`.
- El dinero se representa como centavos enteros y la moneda se fija en MXN.
- Productos usan ID entero; clientes, pedidos y movimientos usan UUID.
- Errores usan `application/problem+json` con un `code` estable y `trace_id`.
- `X-Request-ID` permite correlación funcional y `traceparent` transporta el contexto de OpenTelemetry.
- Crear pedidos y acreditar puntos requiere `Idempotency-Key`.
- Un pedido se confirma aunque lealtad no esté disponible; queda con puntos pendientes.
- Lealtad asigna un punto por cada $10 MXN completos.

## Alternativas rechazadas

- Importes `float`: introducen errores de redondeo.
- Precio enviado por el frontend: permite manipulación y resultados inconsistentes.
- Duplicar todo el catálogo dentro de pedidos: produce precios desactualizados.
- Transacción distribuida entre pedidos y lealtad: excede el alcance del MVP.
- API sin versión: dificulta cambiar contratos después de publicar imágenes independientes.

## Consecuencias

- El frontend debe convertir centavos a una representación monetaria legible.
- `svc-pedidos` guarda nombre y precio como instantánea histórica del producto.
- Las implementaciones necesitan almacenamiento de claves idempotentes o restricciones equivalentes.
- Las pruebas pueden construirse antes que el código usando ejemplos y esquemas OpenAPI.

Contratos: [`docs/openapi/`](../openapi/README.md).
