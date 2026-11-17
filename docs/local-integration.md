# Integración local de los backends

El [`compose.yaml`](../compose.yaml) de la raíz levanta una sola instancia de
PostgreSQL y los tres backends como imágenes independientes:

```text
svc-pedidos ──→ svc-menu ─────┐
      │                       │
      └──────→ svc-lealtad ───┼──→ PostgreSQL
                              │
svc-pedidos ──────────────────┘
```

La base compartida simplifica el desarrollo local, pero cada servicio conserva
propiedad lógica sobre sus tablas. Los servicios se comunican mediante HTTP y
no consultan directamente las tablas de otro servicio.

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
| Menú | `http://localhost:8001` | `http://localhost:8001/docs` |
| Pedidos | `http://localhost:8002` | `http://localhost:8002/docs` |
| Lealtad | `http://localhost:8003` | `http://localhost:8003/docs` |

## Probar el recorrido completo

El smoke test usa únicamente la biblioteca estándar de Python:

```bash
python scripts/smoke_compose.py
```

La prueba verifica:

1. Salud de los tres servicios y PostgreSQL.
2. Catálogo con al menos 20 productos.
3. Creación de un pedido usando precios de `svc-menu`.
4. Acreditación de puntos mediante `svc-lealtad`.
5. Replay idempotente sin duplicar el pedido.
6. Consulta del pedido, listado del cliente y saldo.
7. Métricas Prometheus de los tres servicios.

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
