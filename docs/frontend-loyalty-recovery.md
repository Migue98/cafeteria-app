# Puntos pendientes y recuperación en el frontend

El historial consulta los pedidos y el saldo por separado. Si lealtad no está
disponible, conserva la lista de pedidos y muestra **Saldo no disponible**.
Un saldo desconocido no se representa como cero.

## Actualización automática

El recibo y el historial utilizan HTMX para consultar su estado cada 15 segundos
mientras haya puntos pendientes. El recibo actualiza únicamente el bloque de
puntos; el historial actualiza su contenido y el saldo. Al recibir los pedidos
acreditados, el HTML deja de incluir el temporizador y las consultas se detienen.

Estas solicitudes solo leen información. La acreditación continúa a cargo del
worker de `svc-pedidos`, que ejecuta un lote al arrancar y cada 15 minutos. La
interfaz no reenvía `POST /checkout` ni llama al endpoint manual de reintentos.
Los 15 segundos de la vista no cambian el intervalo de recuperación del worker.

Sin JavaScript, el usuario puede volver a abrir **Mis pedidos** para consultar
el estado. La mejora automática usa la misma dependencia HTMX que el carrito.

## Rutas del frontend

| Ruta | Respuesta |
|---|---|
| `GET /orders` | Página completa del historial. Con `HX-Request: true`, solo el fragmento `order-history`. |
| `GET /orders/{order_id}/points` | Fragmento `receipt-points` para un pedido del cliente de la sesión. |

El fragmento del recibo verifica que `customer_id` coincida con el de la sesión.
Un pedido ajeno responde 404 y no muestra información. Ambas consultas propagan
`X-Request-ID` y `traceparent` y usan `Cache-Control: private, no-store`.
El historial distingue sus variantes con `Vary: HX-Request`.

Si falla la consulta de pedidos durante una actualización, se conserva el
contenido ya visible con `HX-Reswap: none`. El temporizador de la vista pendiente
continúa consultando. Una visita normal al historial mantiene su página de error
si el servicio de pedidos está caído; la degradación independiente aplica al saldo.

## Validación

Las pruebas del frontend cubren el historial con lealtad caído, el cambio de
pendiente a acreditado, la retirada del temporizador, el aislamiento entre
sesiones y la conservación del contenido ante errores temporales.

La prueba integral
`test_browser_history_survives_loyalty_outage_and_refreshes` detiene lealtad en
`cafeteria-e2e`, compra desde una sesión HTTP con cookies, consulta el historial,
restaura lealtad y comprueba los fragmentos actualizados. También confirma que
solo exista un pedido y una acreditación de puntos.

```powershell
# Desde frontend, con sus dependencias de desarrollo instaladas:
python -m pytest tests ../tests/observability -p no:cacheprovider

# Desde la raíz, con tests/requirements.txt instalado:
python scripts/run_e2e.py
```

## Evidencia de verificación — 21 de noviembre de 2026

| Límite del flujo | Evidencia |
|---|---|
| Interfaz → pedido | El navegador confirmó un café de $35 con lealtad detenido y mostró puntos pendientes. |
| Pedido → datos persistidos | La API de pedidos devolvió un solo pedido para el cliente de prueba. |
| Historial → lealtad caído | El navegador mostró el café comprado y **Saldo no disponible**, sin ocultar el historial. |
| Recuperación → interfaz | Al restaurar lealtad, recibo e historial cambiaron por sí solos a puntos acreditados; el recibo mostró **+3 puntos**. |
| Fin de consultas | Los atributos `hx-trigger` desaparecieron de ambos fragmentos después de acreditarse los puntos. |
| Sin duplicación | La API confirmó `order_count=1`, `loyalty_status=awarded`, `points_earned=3` y `balance=3`. |

- Frontend y contrato común: **23 pruebas aprobadas**.
- Suite E2E de los cuatro servicios y PostgreSQL: **12 pruebas aprobadas** en 29.70 segundos.
- Ruff y formato: correctos; los tres contratos OpenAPI son válidos.
- Consola del historial: sin errores durante la comprobación del navegador.

En las pruebas integrales el worker usa un intervalo de dos segundos para
acelerar la recuperación. En desarrollo normal mantiene sus 15 minutos; la
actualización de la interfaz conserva sus 15 segundos en ambos entornos.
