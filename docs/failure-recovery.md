# Degradación y recuperación ante fallas

Las pruebas interrumpen servicios únicamente dentro del proyecto Compose
`cafeteria-e2e`. Cada interrupción usa un bloque de limpieza que restaura el
servicio, espera su salud y conserva el volumen de datos durante el escenario.
El ejecutor elimina el entorno aislado cuando termina la suite.

## Comportamiento comprobado

| Falla | Durante la interrupción | Después de restaurar |
|---|---|---|
| Menú detenido | Crear pedidos responde 503. Los pedidos guardados siguen consultándose y el carrito se conserva. | Se puede confirmar el mismo carrito y reintentar la compra rechazada sin duplicados. |
| Menú pausado | Se verifica el timeout de lectura, con el mismo tratamiento que una caída. | El cliente HTTP vuelve a responder sin reiniciar las aplicaciones. |
| Pedidos detenido | El menú sigue disponible. El historial y el checkout informan indisponibilidad; una actualización HTMX conserva el contenido existente. | El checkout usa el carrito y la clave preparados antes de la falla. |
| PostgreSQL detenido | Los backends responden 503 en salud y operaciones de datos. Las métricas siguen accesibles. | Los pedidos y puntos previos permanecen; las aplicaciones recuperan sus conexiones sin reiniciarse. |
| Lealtad pausado | El timeout no cancela el pedido: se confirma con `loyalty_status=pending`. | El worker sincroniza la acreditación y se comprueba un solo movimiento de puntos. |

El frontend responde 200 y estado `degraded` en `/health` cuando alguna
dependencia falla. Los backends responden 503 cuando falla una dependencia
crítica. Esto permite distinguir una interfaz que todavía puede servir parte
del flujo de un backend que no puede atender su operación principal.

Las pruebas verifican los códigos HTTP, los errores Problem JSON y sus campos
de correlación, además de contar pedidos, saldo y movimientos después de la
recuperación. Un intento rechazado antes de guardar no debe dejar pedidos ni
puntos residuales.

## Respuestas inválidas de dependencias

`svc-pedidos` valida los productos recibidos de menú: identificador solicitado,
precio entero no negativo, moneda y disponibilidad. JSON inválido o datos que
no cumplen ese contrato se tratan como indisponibilidad de una dependencia
crítica y responden 503 antes de crear el pedido.

La acreditación de lealtad debe corresponder al pedido y al cliente solicitados
y contener puntos enteros no negativos. Se rechazan valores nulos, booleanos,
fraccionarios o cadenas. Si la respuesta no cumple este contrato, el pedido
permanece confirmado y pendiente para recuperarse mediante idempotencia.
Una cantidad válida de cero puntos sí se acepta.

El frontend convierte JSON inválido, respuestas que no son objetos, listas de
elementos con estructura inválida y saldos inválidos en errores controlados
`502 INVALID_BACKEND_RESPONSE`. Un saldo no disponible no impide consultar los
pedidos. Los timeouts de transporte se presentan con un mensaje público 503;
el detalle técnico de la excepción no se copia a la página.

Las respuestas de salud inesperadas se consideran una dependencia caída, en
lugar de provocar un error interno del frontend. Estas validaciones no intentan
reemplazar todas las reglas de negocio de los servicios productores.

## Límites de tiempo y reintentos

- `HTTP_TIMEOUT_SECONDS` conserva su valor predeterminado de 3 segundos por
  llamada entre servicios.
- Una petición del frontend puede hacer varias llamadas; su tiempo total no
  equivale al timeout de una sola llamada.
- Las pruebas permiten hasta 12 segundos para la operación de compra que
  encuentra una dependencia pausada, para evitar aserciones de tiempo frágiles.
- El frontend no reenvía una compra automáticamente. Conserva carrito y clave
  para que el usuario la reintente.
- El worker de pedidos recupera puntos pendientes. En E2E su intervalo es de
  dos segundos; en desarrollo normal conserva los 15 minutos configurados.

Si una solicitud a lealtad vence, puede que el servidor llegue a procesarla
después. El identificador del pedido y la clave idempotente permiten consultar
o repetir esa acreditación sin sumar puntos dos veces.

## Ejecución

```powershell
python -m pip install -r tests/requirements.txt
python scripts/run_e2e.py
```

Los escenarios nuevos viven en `tests/e2e/test_failure_recovery.py`. Se ejecutan
en serie porque detienen o pausan dependencias compartidas del entorno aislado.
El workflow `Integrated E2E` los incorpora mediante el mismo ejecutor.

## Evidencia — 21 de noviembre de 2026

- La regresión de JSON inválido de menú reprodujo un error interno 500 antes
  de corregirse; ahora responde 503 y no guarda ningún pedido.
- Frontend y contrato común: **39 pruebas aprobadas**.
- Pedidos y contrato común: **40 pruebas aprobadas**.
- Suite E2E completa: **28 pruebas aprobadas en 138.33 segundos**, incluidos
  los cinco casos nuevos de interrupción y timeout.
- Ruff y formato pasan; los tres contratos OpenAPI son válidos y las cuatro
  imágenes se construyeron.
- El ejecutor restauró los servicios interrumpidos y eliminó los contenedores,
  la red y el volumen sintético de `cafeteria-e2e` al terminar.

El commit previo `53b8814` ya fue publicado y sus cinco workflows de GitHub
terminaron correctamente, incluido
[Integrated E2E](https://github.com/Migue98/cafeteria-app/actions/runs/44956183642).
Las comprobaciones de este bloque corresponden a la ejecución local;
el workflow `Integrated E2E` las ejecuta también al publicar cambios en `main`.
