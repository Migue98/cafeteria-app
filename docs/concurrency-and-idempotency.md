# Concurrencia e idempotencia

Este bloque verifica compras y acreditaciones simultáneas con HTTP, PostgreSQL
y los clientes de servicio reales. También corrige dos regresiones reproducidas
antes de implementar sus soluciones.

## Compra duplicada desde el frontend

Antes, la clave de compra se generaba dentro de `POST /checkout`. Dos solicitudes
con la misma cookie podían crear claves distintas y, por tanto, pedidos distintos.
La prueba de regresión obtuvo dos claves para el mismo carrito.

Ahora se prepara el identificador del cliente y la clave de compra al guardar el
carrito, antes de entregar al navegador la cookie firmada. Las solicitudes que
repitan esa cookie utilizan la misma clave. Cambiar el contenido del carrito
prepara otra clave; al finalizar la compra se descarta el intento para permitir
una compra nueva, incluso si contiene los mismos productos. Al abrir un menú
con un carrito existente también se prepara el intento si faltaba.

El frontend sigue consultando el catálogo y confirmando el pedido por HTTP.
No introduce bloqueos locales que dependan de una única réplica.

## Reserva de claves alternas en lealtad

Una acreditación puede repetirse con otra `Idempotency-Key`, siempre que el
pedido y los datos coincidan. Antes esa clave alterna no se guardaba: después
podía reutilizarse para otro pedido y crear otro movimiento.

La tabla `loyalty_request_keys` relaciona todas las claves aceptadas con su
movimiento original. Su clave primaria impide que una clave se asigne a dos
movimientos. El alta de un movimiento registra también su clave inicial dentro
de la misma transacción que actualiza el saldo.

Una repetición válida reserva su clave con `INSERT ... ON CONFLICT DO NOTHING`
y lee la asociación ganadora. Después compara el `request_hash`. Si otra
solicitud la reservó para datos distintos, responde `409 IDEMPOTENCY_KEY_REUSED`.
Los datos distintos para un pedido ya acreditado mantienen
`409 ORDER_ALREADY_AWARDED` cuando la clave nueva todavía no está reservada.

Las restricciones de pedido y clave, el incremento atómico del saldo y la
transacción de movimiento/saldo se mantienen en PostgreSQL. Las llamadas HTTP
permanecen fuera de esas transacciones; no se mantiene un bloqueo de base de
datos mientras se espera a otro servicio.

## Base de datos existente

En una base nueva, el script de inicialización crea la tabla vacía; las nuevas
acreditaciones reservan sus claves dentro de la transacción de negocio.
En una base con volumen persistente, **reiniciar el contenedor no vuelve a ejecutar
los scripts de inicialización**. Solo si faltan claves históricas, antes de
levantar la nueva versión de lealtad, actualiza los montajes de PostgreSQL y
aplica los dos archivos desde la raíz del repositorio:

```powershell
docker compose up --detach --no-deps postgres
# Esperar a que PostgreSQL esté healthy; se conserva su volumen.
docker compose exec -T postgres psql -U cafeteria -d cafeteria -v ON_ERROR_STOP=1 -f /docker-entrypoint-initdb.d/003-loyalty.sql
docker compose exec -T postgres psql -U cafeteria -d cafeteria -v ON_ERROR_STOP=1 -f /opt/cafeteria/db/backfill-loyalty-request-keys.sql
```

Adapta usuario y base si configuraste otros valores. Los archivos se montan desde
`svc-lealtad/db/init.sql` y `svc-lealtad/db/backfill-request-keys.sql`. El primer
comando crea las estructuras que falten y el segundo asocia las claves iniciales
de movimientos históricos. No elimina pedidos, movimientos ni
volúmenes. Las claves alternas que nunca se guardaron antes de esta versión no
pueden reconstruirse; quedan reservadas al volver a utilizarlas válidamente.

El backfill manual se prueba simulando un movimiento histórico sin asociación,
ejecutando el script dos veces y comprobando que la repetición conserva el mismo
movimiento y saldo.

Este procedimiento conserva compatibilidad con bases antiguas de desarrollo;
no hay una migración nueva de producción. El backfill está fuera del directorio
de ejecución automática. Ver [inicialización de PostgreSQL](database-initialization.md).

## Escenarios cubiertos

| Escenario | Resultado exigido |
|---|---|
| Cuatro compras con la misma clave y cuerpo | Un pedido nuevo, tres repeticiones y un movimiento. |
| Misma clave y cantidades distintas | Una solicitud gana y la otra recibe 409. |
| Cuatro compras distintas para un cliente | Cuatro pedidos; saldo igual a la suma de los puntos. |
| Acreditaciones repetidas con clave igual o distinta | Un movimiento; todas las claves aceptadas quedan reservadas. |
| Dos clientes compiten por una clave | El perdedor no conserva una cuenta ni puntos residuales. |
| Mismo pedido con importes distintos | Una acreditación; el resto recibe 409. |
| Una clave alterna para dos movimientos existentes | Una asociación gana y la otra recibe 409. |
| Cuatro envíos del checkout con la misma cookie | Un pedido y una acreditación. |
| Dos lotes del worker con el mismo pendiente | Un solo movimiento, incluso con reintentos manuales concurrentes. |

La prueba de los workers usa una barrera antes de sus llamadas HTTP: ambos lotes
leen el pendiente antes de liberarlos. Ejecuta la función real de recuperación
con repositorios PostgreSQL independientes y el cliente HTTP de lealtad. Las
conexiones no comparten una transacción ni un bloqueo de Python para el saldo.
Esto comprueba la carrera entre lotes; no pretende simular la infraestructura
de un clúster Kubernetes completo.

Las comprobaciones de integridad leen directamente `loyalty_accounts` y
`loyalty_movements`, además de comprobar las respuestas HTTP. Los escenarios se
ejecutan en serie porque algunas pruebas detienen dependencias del proyecto
Compose aislado; dentro de cada escenario sí se sincronizan las solicitudes.

## Ejecución y CI

```powershell
python -m pip install -r tests/requirements.txt
python scripts/run_e2e.py
```

El workflow `Integrated E2E` usa el mismo ejecutor en cambios de aplicación,
contratos, Compose, pruebas o del propio ejecutor. Conserva las versiones fijadas
de Actions, Python y dependencias. El ejecutor limpia el proyecto `cafeteria-e2e`
cuando termina, incluidos sus datos sintéticos.

## Evidencia — 21 de noviembre de 2026

- Antes de las correcciones, las dos regresiones fallaron: el checkout generó
  dos claves distintas y una clave alterna de lealtad pudo crear otro movimiento.
- Frontend y contrato común: **25 pruebas aprobadas**.
- Lealtad y contrato común: **24 pruebas aprobadas**.
- Suite E2E completa: **23 pruebas aprobadas en 60.03 segundos**; incluye once
  escenarios/casos parametrizados de concurrencia y migración.
- Los tres contratos OpenAPI son válidos y las cuatro imágenes se construyeron.
- Ruff y formato pasan para los servicios modificados.
- Los contenedores, la red y el volumen de datos sintéticos de `cafeteria-e2e`
  se eliminaron al finalizar.

El workflow E2E está preparado en este bloque; su ejecución en GitHub comenzará
al publicar los cambios. La evidencia anterior corresponde a la ejecución local
con contenedores reales.
