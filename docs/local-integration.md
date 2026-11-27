# Integración local de la aplicación

El [`compose.yaml`](../compose.yaml) de la raíz levanta el frontend, una sola
instancia de PostgreSQL y los tres backends como imágenes independientes:

```text
 navegador ──→ frontend ──┬──→ svc-menu ─────────┐
                          ├──→ svc-pedidos ──────┼──→ PostgreSQL
                          │         ├→ svc-menu  │
                          │         └→ svc-lealtad
                          └──→ svc-lealtad ──────┘
```

La base compartida simplifica el desarrollo local, pero cada servicio conserva
propiedad lógica sobre sus tablas. Los servicios se comunican mediante HTTP y
no consultan directamente las tablas de otro servicio.

El SQL se reparte por responsabilidad y separa el esquema de los ejemplos:

| Archivo | Responsabilidad |
|---|---|
| [`svc-menu/db/init.sql`](../svc-menu/db/init.sql) | Esquema del catálogo. |
| [`svc-menu/db/seed.sql`](../svc-menu/db/seed.sql) | Carga de los 20 productos de ejemplo sin reemplazar existentes. |
| [`svc-pedidos/db/init.sql`](../svc-pedidos/db/init.sql) | Pedidos, ítems e idempotencia de compras. |
| [`svc-lealtad/db/init.sql`](../svc-lealtad/db/init.sql) | Saldos, movimientos y claves de acreditación. |

El Compose raíz monta los esquemas como `001-menu.sql`, `002-orders.sql` y
`003-loyalty.sql`, seguidos de `004-menu-seed.sql` en
`/docker-entrypoint-initdb.d/`. Se ejecutan solo al inicializar un volumen vacío.
Los Compose individuales incluyen los archivos de su servicio y sus dependencias.
Editar `init.sql` no actualiza automáticamente una base existente. La
[guía de inicialización](database-initialization.md) describe reinicios,
conservación de datos y la reparación manual para bases antiguas de lealtad.

## Iniciar

Para una copia nueva, usa la [guía de entrega al equipo](team-handoff.md), que
incluye requisitos, creación del `.env` y comandos completos de pruebas.

Con Podman:

```bash
podman compose up --build --detach
```

Con Docker:

```bash
docker compose up --build --detach
```

Compose espera a PostgreSQL y a los healthchecks antes de marcar disponibles
las dependencias. Las APIs quedan en:

| Servicio | URL | OpenAPI |
|---|---|---|
| Frontend | `http://localhost:8000` | `http://localhost:8000/docs` |
| Menú | `http://localhost:8001` | `http://localhost:8001/docs` |
| Pedidos | `http://localhost:8002` | `http://localhost:8002/docs` |
| Lealtad | `http://localhost:8003` | `http://localhost:8003/docs` |

## Probar el recorrido completo

El smoke test usa únicamente la biblioteca estándar de Python:

```bash
python tests/smoke/check_compose.py
```

La prueba verifica:

1. Salud de los cuatro servicios y PostgreSQL.
2. Renderizado del menú y carrito en el frontend.
3. Catálogo con al menos 20 productos.
4. Creación de un pedido usando precios de `svc-menu`.
5. Acreditación de puntos mediante `svc-lealtad`.
6. Replay idempotente sin duplicar el pedido.
7. Consulta del pedido, listado del cliente y saldo.
8. Métricas Prometheus de los cuatro servicios.

El smoke test es una comprobación rápida sobre el entorno ya levantado. La
suite E2E automatizada crea su propio proyecto Compose y volumen aislados:

Prepara `tests/.venv`, instala los locks y Chromium y ejecuta
`scripts/run_e2e.py` con ese entorno. Los comandos completos están en
[`tests/README.md`](../tests/README.md#ejecución).

Además del recorrido anterior, la suite comprueba validaciones, productos
inexistentes y no disponibles, conflictos de idempotencia y persistencia tras
reiniciar PostgreSQL. Consulta [`tests/README.md`](../tests/README.md).

## Detener y limpiar

El [Compose opcional de monitoreo](local-monitoring.md) añade Prometheus y
Grafana con sus propios volúmenes. Conserva todos los archivos y su orden al
iniciar y detener: también `compose.telemetry.yaml` y `compose.telegram.yaml`
si los utilizaste. La [guía de entrega](team-handoff.md#3-elegir-observabilidad)
resume las combinaciones.

Conservar los datos locales:

```bash
podman compose down
```

Eliminar también el volumen de PostgreSQL y recrear los esquemas en el próximo
inicio:

```bash
podman compose down --volumes
```

En Docker se sustituyen los comandos `podman compose` por `docker compose`.

Las credenciales predeterminadas son exclusivamente locales. Para cambiarlas,
copia [`.env.example`](../.env.example) como `.env`; `.env` está ignorado por
Git.
