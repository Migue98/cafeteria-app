# Instrumentación con OpenTelemetry

Este bloque implementa trazas reales en los cuatro servicios de la cafetería.
El SDK genera los identificadores y los instrumentadores enlazan peticiones
entrantes, llamadas HTTP y consultas PostgreSQL. Los logs JSON y los errores
de la aplicación usan ese mismo contexto.

Este paso deja implementada y probada la exportación hacia un receptor OTLP.
Prometheus y Grafana están disponibles en el [monitoreo local](local-monitoring.md).
Alloy, Loki y Tempo ya están disponibles en la
[extensión de logs y trazas](local-logs-traces.md).

## Bibliotecas y alcance

| Dependencia directa | Versión | Uso |
|---|---|---|
| `opentelemetry-api` y `opentelemetry-sdk` | 1.45.2 | Contexto, spans, muestreo, recursos y procesamiento por lotes. |
| `opentelemetry-exporter-otlp-proto-http` | 1.45.2 | Exportación OTLP HTTP/protobuf. |
| `opentelemetry-instrumentation-fastapi` | 0.66b2 | Span servidor por petición en los cuatro componentes. |
| `opentelemetry-instrumentation-httpx` | 0.66b2 | Llamadas de frontend y pedidos a otros servicios. |
| `opentelemetry-instrumentation-psycopg` | 0.66b2 | Consultas SQL en menú, pedidos y lealtad. |

Las versiones corresponden a una misma línea de OpenTelemetry y están fijadas
en los `.in` y en locks con hashes. Las instrumentaciones usan la numeración
beta publicada por OpenTelemetry. Se alinearon también los locks de desarrollo:
`packaging` queda en 26.4 en ejecución y desarrollo de los cuatro componentes.

La propagación se delega a OpenTelemetry. `TraceContext` es una vista del span
actual para logs y respuestas; ya no analiza encabezados ni genera UUID para
trazas. `X-Request-ID` conserva su contrato anterior y se propaga por separado.

## Recorrido de una compra

```text
frontend · SERVER /checkout
└─ HTTP CLIENT → svc-pedidos · SERVER /api/v1/orders
   ├─ HTTP CLIENT → svc-menu · SERVER /api/v1/products/{product_id}
   │  └─ PostgreSQL · CLIENT SELECT
   ├─ PostgreSQL · CLIENT SELECT / INSERT
   └─ HTTP CLIENT → svc-lealtad · SERVER /api/v1/points/earn
      └─ PostgreSQL · CLIENT SELECT / INSERT / UPDATE
```

Todos esos spans comparten `trace_id`, tienen identificadores propios y
registran su tiempo de inicio y fin. El padre del span servidor remoto es
el span cliente HTTP que lo llamó. Las consultas son spans del driver dentro
del servicio que las ejecuta, no spans emitidos desde el servidor PostgreSQL.

Los reintentos automáticos abren una traza por lote (`loyalty.retry_batch`) y
un span hijo por pedido (`loyalty.retry`). Las llamadas HTTP y SQL se enlazan
al intento activo. Los intentos fallidos registran excepción y estado de error.

## Aislamiento y ciclo de vida

Cada aplicación posee su `TracerProvider`, con `service.name` fijo al componente
y `service.version` tomado de `APP_VERSION`. Se instrumentan instancias de
HTTPX y conexiones de Psycopg, sin sustituir proveedores globales del proceso.
Esto permite construir varias aplicaciones en las pruebas sin mezclar sus
exportadores ni recursos.

El contexto llega a las rutas síncronas y a los hilos del worker. Al apagar la
aplicación se termina el lote activo del worker, se cierran los clientes HTTP
propios y se apaga el proveedor, que vacía los lotes de spans pendientes.
La exportación usa `BatchSpanProcessor`, fuera del camino de la petición.

Las métricas existentes permanecen en `prometheus_client` y `/metrics`.
La instrumentación FastAPI usa un proveedor de métricas sin exportación para
no crear una segunda colección de métricas HTTP en este bloque.

La configuración del proyecto no habilita captura de cabeceras HTTP, cuerpos
de solicitudes ni parámetros SQL. Las trazas contienen rutas y sentencias
SQL; el receptor pertenece a la red de administración, como el resto de la
observabilidad prevista.

## Configuración

| Variable | Valor predeterminado del Compose | Comportamiento |
|---|---|---|
| `OTEL_TRACES_EXPORTER` | `none` | `none`, `console`, `otlp` o `console,otlp`. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://alloy:4318` | URL base del receptor; el SDK añade `/v1/traces`. |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` | Protocolo del exportador incluido; gRPC necesita otro exportador. |
| `OTEL_EXPORTER_OTLP_TIMEOUT` | `10` | Tiempo límite de exportación, en segundos. |
| `OTEL_BSP_SCHEDULE_DELAY` | `5000` | Intervalo del procesador por lotes, en milisegundos. |
| `OTEL_TRACES_SAMPLER` | `parentbased_always_on` | Muestrea trazas raíz y respeta la decisión del padre remoto. |

`none` conserva el contexto de trazas y los identificadores de los logs, sin
enviar spans a un receptor. `console` escribe un objeto JSON por span en stdout.
Las líneas de spans se distinguen de los eventos de aplicación por su campo
`context`; los eventos propios conservan `message` y `trace_id` en la raíz.

`otlp` requiere un receptor real accesible desde el contenedor. La dirección
`alloy:4318` está disponible al añadir `compose.telemetry.yaml` junto con
`compose.monitoring.yaml`; esa extensión habilita `otlp` automáticamente.
Si usas otro receptor, cambia la URL antes de habilitar ese modo. Un endpoint
local de Windows debe ser accesible desde Docker mediante la dirección del host
correspondiente.

Al iniciar Python directamente, el exportador también acepta las variables
estándar de señal, como `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, que especifica
la URL final sin añadir `/v1/traces`. Los dos modos de endpoint se prueban
contra un receptor HTTP local. El Compose pasa la URL base de la tabla.

## Probar en local

Instala los locks actualizados en el entorno de cada componente:

```powershell
python -m pip install --require-hashes -r requirements.txt -r requirements-dev.txt
python -m pytest -c pyproject.toml tests ../tests/observability -p no:cacheprovider
```

Para ver spans del Compose normal, desde la raíz:

```powershell
$env:OTEL_TRACES_EXPORTER = "console"
docker compose up --build --detach
# Haz una compra en http://localhost:8000.
docker compose logs --follow frontend svc-pedidos svc-menu svc-lealtad
```

Al terminar, detén el seguimiento de logs y vuelve al modo sin exportación:

```powershell
Remove-Item Env:OTEL_TRACES_EXPORTER
docker compose down
```

Si cambias el modo en `.env`, vuelve a crear los contenedores para que reciban
la nueva configuración. El Compose de pruebas es independiente del normal.

## Verificación automatizada

- El contrato compartido compara spans del SDK con logs y cabeceras de respuesta.
- Comprueba padre remoto, decisiones de muestreo, errores y contexto en rutas
  síncronas; aplicaciones independientes conservan sus proveedores y recursos.
- Un receptor HTTP de prueba recibe y decodifica protobuf OTLP real, tanto con
  URL base como con URL específica. Se comprueba el vaciado al apagar la app.
- Los reintentos de puntos prueban spans de lote e intento, resultados exitosos
  y fallidos, y la espera del hilo activo antes del cierre de recursos.
- El E2E reconstruye las cuatro imágenes y usa exportación `console` con lotes
  de 100 ms. Contrasta los spans exportados con los logs y exige los enlaces
  SERVER → CLIENT HTTP → SERVER y los spans SQL de los tres backends.
- Los recorridos existentes de fallas, concurrencia, seguridad y Chromium se
  siguen ejecutando sobre los servicios reales.

Las pruebas OTLP usan un receptor de prueba y las E2E inspeccionan spans
exportados a stdout. La suite adicional de
[logs y trazas](local-logs-traces.md#pruebas-automatizadas) comprueba la recepción
en Tempo, los logs en Loki y la navegación log ↔ traza en Grafana real.

Referencias: [SDK de trazas](https://opentelemetry-python.readthedocs.io/en/latest/sdk/trace.html),
[FastAPI](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html),
[HTTPX](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/httpx/httpx.html),
[Psycopg](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/psycopg/psycopg.html).

## Evidencia local — 26 de noviembre de 2026

| Comprobación | Resultado |
|---|---|
| Frontend y contrato compartido | 90 pruebas aprobadas. |
| Menú y contrato compartido | 32 pruebas aprobadas. |
| Pedidos y contrato compartido | 54 pruebas aprobadas. |
| Lealtad y contrato compartido | 35 pruebas aprobadas. |
| E2E HTTP sobre los cuatro servicios y PostgreSQL | 31 pruebas aprobadas en 159.37 segundos. |
| E2E Chromium con JavaScript y HTMX | 4 pruebas aprobadas en 56.23 segundos. |
| OTLP HTTP/protobuf | Recepción y decodificación reales en las pruebas de los cuatro entornos. |
| Compra distribuida | Spans exportados de los cuatro servicios, clientes HTTP y SQL de los tres backends; identificadores coincidentes con logs. |
| Herramientas | Ruff y formato correctos; `pip check` sin conflictos en los cuatro entornos. |
| Construcción | Las cuatro imágenes se reconstruyeron con instalación por hashes. |

Se usó Python 3.13.1 en los entornos locales y 3.13.18 en las imágenes.
El runner eliminó los contenedores, red y volumen de `cafeteria-e2e` al terminar.
La aplicación normal permaneció apagada. Los workflows siguen ejecutando el
contrato compartido; esta evidencia es local, sin ejecución remota en este paso.
Continúan las advertencias conocidas de Starlette/HTTPX y de la fixture
`base_url` de Playwright; no se ocultaron ni causaron fallos.
