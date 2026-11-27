# Inicialización de PostgreSQL

Paso 3 ajustado el **27 de noviembre de 2026**: preparar la inicialización de
la BD, separar los ejemplos y comprobar persistencia. Todavía no existe una
base de producción que debamos transformar; no se incorpora un framework ni
se inventan migraciones de esquema.

## Archivos y orden

Cada backend conserva la propiedad de sus tablas. El Compose raíz usa una sola
base, con estos archivos montados de solo lectura:

| Archivo del repositorio | Ruta dentro de PostgreSQL | Función |
|---|---|---|
| `svc-menu/db/init.sql` | `/docker-entrypoint-initdb.d/001-menu.sql` | Esquema de productos. |
| `svc-pedidos/db/init.sql` | `/docker-entrypoint-initdb.d/002-orders.sql` | Esquema de pedidos e ítems. |
| `svc-lealtad/db/init.sql` | `/docker-entrypoint-initdb.d/003-loyalty.sql` | Esquema de cuentas, movimientos y claves. |
| `svc-menu/db/seed.sql` | `/docker-entrypoint-initdb.d/004-menu-seed.sql` | Los 20 productos de demostración. |
| `svc-lealtad/db/backfill-request-keys.sql` | `/opt/cafeteria/db/backfill-loyalty-request-keys.sql` | Reparación manual de claves históricas de lealtad. |

Los tres `init.sql` contienen DDL con `IF NOT EXISTS`, sin insertar datos de
negocio. Cada archivo usa una transacción. `seed.sql` tiene su propia transacción,
agrega solo productos faltantes y no actualiza precios, disponibilidad o nombres
existentes. Un conflicto por ID o SKU conserva la fila existente.

La carga toma un bloqueo de la tabla de productos y ajusta su secuencia sin
retrocederla, incluso si se eliminaron productos con IDs mayores. Para aplicarla
manualmente, usar una ventana sin escrituras del catálogo; no es una operación
por petición ni por réplica del backend.

## Primer arranque y siguientes despliegues

Desde la raíz del repositorio, con el `.env` local preparado:

```powershell
docker compose -f compose.yaml config --quiet
docker compose -f compose.yaml up --build --detach
```

En un **volumen vacío**, el entrypoint de PostgreSQL crea la base y ejecuta
`001` a `004` en orden. El resultado es un catálogo de 20 productos y tablas
de pedidos y lealtad vacías. Los Compose individuales usan el mismo reparto:
menú monta esquema y seed; pedidos añade ambos para su dependencia de menú;
lealtad monta solo su esquema y la reparación manual.

En un **volumen existente**, el entrypoint no vuelve a ejecutar esos archivos.
Reiniciar, reconstruir las imágenes o recrear contenedores conserva el volumen
y sus datos; tampoco carga de nuevo los ejemplos. Este comportamiento pertenece
a la [imagen oficial de PostgreSQL](https://hub.docker.com/_/postgres#initialization-scripts).

```powershell
# Detener y volver a iniciar conservando los datos.
docker compose -f compose.yaml down
docker compose -f compose.yaml up --detach
```

`down --volumes` elimina los datos y no forma parte del despliegue habitual.
El runner E2E sí lo utiliza, exclusivamente sobre su proyecto desechable.

Si falla la inicialización de un volumen nuevo, revisar el SQL y los logs antes
de arrancar la web. El entrypoint puede dejar una base parcialmente inicializada
y no retoma automáticamente los scripts al reiniciar. La transacción limita
los cambios de cada archivo; no existe una transacción común a los cuatro.

## Bases de desarrollo que ya existen

La separación de archivos no cambia ninguna tabla y no exige ejecutar SQL
sobre un volumen actual. Repetir los esquemas actuales conserva las filas, pero
`IF NOT EXISTS` **no agrega columnas ni valida que un esquema antiguo coincida**.
Cuando cambiemos tablas, definiremos una actualización explícita y su prueba de
conservación de datos; nunca se resolverá borrando el volumen automáticamente.

Solo si deseas completar productos de demostración faltantes, ejecuta:

```powershell
docker compose exec -T postgres psql -X -U cafeteria -d cafeteria -v ON_ERROR_STOP=1 -f /docker-entrypoint-initdb.d/004-menu-seed.sql
```

El comando usa el usuario y la base locales por defecto; adapta ambos si los
cambiaste. No repone un catálogo personalizado ni garantiza 20 filas si existen
conflictos con otros IDs/SKU: conserva los productos que ya tienes.

La reparación de claves de lealtad queda fuera del directorio automático y se
ejecuta únicamente para bases antiguas que la necesiten. Consulta el procedimiento
de [concurrencia e idempotencia](concurrency-and-idempotency.md#base-de-datos-existente).
No crea puntos nuevos ni modifica saldos.

## Integración posterior con Kubernetes

El paso 4 trasladará estos archivos al despliegue: esquema al inicializar el
almacenamiento vacío de PostgreSQL y catálogo de demostración como carga
explícita. Los cuatro backends no crearán tablas ni cargarán ejemplos al iniciar
cada réplica. La inicialización debe finalizar y el catálogo debe verificarse
antes de habilitar la entrega; `SELECT 1` de readiness no valida tablas.

## Pruebas

`tests/e2e/test_database_initialization.py` prueba PostgreSQL real:

1. Crea una BD vacía, aplica solo los esquemas y comprueba que las seis tablas
   no tengan filas; carga dos veces los ejemplos y exige exactamente 20 productos.
2. Reaplica esquemas y ejemplos sobre productos modificados, un pedido, sus ítems,
   saldo, movimiento y clave. Compara todas sus columnas y verifica que la
   secuencia no reutilice el ID de un producto eliminado.
3. Detiene y recrea todo el stack de ensayo conservando el volumen. Exige conservar
   un producto no disponible, el pedido, el saldo y su replay idempotente.

La prueba existente de claves históricas ejecuta dos veces el backfill manual.
El runner aísla el proyecto `cafeteria-e2e`, ejecuta HTTP y Chromium y limpia sus
recursos al terminar:

```powershell
python scripts/run_e2e.py
```

Usar el Python de `tests/.venv` con sus dependencias y Chromium instalados,
según [tests/README.md](../tests/README.md).

## Evidencia local

Validación del **27 de noviembre de 2026**, con imágenes reconstruidas y volumen
de ensayo vacío. Esta evidencia corresponde al código del repositorio y no
equivale a una validación en el clúster:

| Comprobación | Resultado |
|---|---|
| Compose raíz y tres Compose individuales | `config --quiet` aprobado. |
| Ruff y formato de pruebas integrales y helpers incluidos en CI | Aprobados. |
| Tres contratos OpenAPI | Válidos. |
| Suite HTTP, incluidos los tres casos nuevos de inicialización y el backfill | 40 aprobadas en 251.13 s. |
| Suite Chromium | 12 aprobadas en 84.43 s; un aviso de deprecación del plugin de pruebas. |
| Limpieza del runner | Contenedores, red y volumen de `cafeteria-e2e` eliminados. |

La prueba de repetición comparó íntegramente las seis tablas antes y después;
la recreación comprobó también la compra por API y la ausencia de duplicados.
La validación se ejecutó únicamente en el entorno aislado; Kubernetes y el
despliegue de infraestructura corresponden al siguiente paso.
