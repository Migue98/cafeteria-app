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

El SQL se reparte por responsabilidad, con tres archivos independientes:

| Archivo | Responsabilidad |
|---|---|
| [`svc-menu/db/init.sql`](../svc-menu/db/init.sql) | Catálogo y carga inicial de productos. |
| [`svc-pedidos/db/init.sql`](../svc-pedidos/db/init.sql) | Pedidos, ítems e idempotencia de compras. |
| [`svc-lealtad/db/init.sql`](../svc-lealtad/db/init.sql) | Saldos, movimientos y claves de acreditación. |

El Compose raíz monta esos archivos como `001-menu.sql`, `002-orders.sql` y
`003-loyalty.sql` en `/docker-entrypoint-initdb.d/`. Se ejecutan al inicializar
un volumen vacío de PostgreSQL. Los Compose individuales montan únicamente el
SQL de su servicio. Editar `init.sql` no actualiza automáticamente una base
existente; los cambios de esquema necesitan una migración explícita.

## Iniciar

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

```bash
python -m pip install -r tests/requirements.txt
python scripts/run_e2e.py
```

Además del recorrido anterior, la suite comprueba validaciones, productos
inexistentes y no disponibles, conflictos de idempotencia y persistencia tras
reiniciar PostgreSQL. Consulta [`tests/README.md`](../tests/README.md).

## Detener y limpiar

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
