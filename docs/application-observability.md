# Logs y correlación entre servicios

Los cuatro servicios emiten eventos JSON en stdout. Cada petición conserva el
`X-Request-ID` y el `trace_id` a través de los saltos HTTP. OpenTelemetry genera
los spans de servidor, cliente HTTP y PostgreSQL; los logs usan el contexto real
del SDK. Consulta la [guía de instrumentación y exportación](opentelemetry-tracing.md).

## Campos comunes

| Campo | Significado |
|---|---|
| `timestamp` | Fecha y hora UTC con zona horaria. |
| `level` | `INFO`, `WARNING` o `ERROR`. |
| `service` | `frontend`, `svc-menu`, `svc-pedidos` o `svc-lealtad`. |
| `message` | Evento estable, como `request_completed`. |
| `request_id` | UUID que permite correlacionar una petición y sus llamadas. |
| `trace_id` | Identificador hexadecimal de 32 caracteres de la traza. |
| `span_id` | Identificador hexadecimal de 16 caracteres del salto actual. |
| `parent_span_id` | Padre del span actual; en una petición remota corresponde al cliente HTTP que la inició. |

`request_completed` añade `method`, `path`, `route`, `status_code` y
`duration_ms`. Usa `INFO` para respuestas menores de 400, `WARNING` para 4xx y
`ERROR` para 5xx. Las rutas de métricas usan la plantilla del endpoint para
evitar una serie distinta por cada UUID.

Una excepción inesperada registra además `request_failed`, con el detalle en
los logs internos, y contabiliza la petición como 500. No se registran cuerpos
de peticiones, cookies ni cabeceras de autorización.

Los eventos de resumen del worker emitidos fuera del lote no corresponden a
una petición y llevan los campos de correlación en `null`. Cada lote inicia
una traza nueva, con un span hijo por intento; el intento registra `order_id`
y propaga su contexto a lealtad y a las consultas SQL.

## Encabezados

- `X-Request-ID`: si falta, el servicio genera un UUID; si es inválido, responde
  422 con un UUID nuevo y registra el rechazo.
- `traceparent`: se valida y propaga mediante OpenTelemetry y W3C Trace Context.
  Un encabezado válido conserva la traza y sus flags, con un span nuevo para
  el servicio. Si falta o es inválido se inicia una traza nueva. Las respuestas
  emiten el formato `00`. Un padre no muestreado conserva su identificador,
  pero sus spans no se exportan con el muestreo predeterminado.
- Las respuestas atendidas por el middleware devuelven ambos encabezados.
  Los errores de negocio incluyen el mismo `trace_id` en su Problem JSON.

Ejemplo de una compra:

```text
frontend SERVER       trace=T, span=A
└─ HTTP CLIENT        trace=T, span=B, parent=A
   └─ pedidos SERVER  trace=T, span=C, parent=B
      ├─ SQL CLIENT   trace=T, span=D, parent=C
      └─ HTTP CLIENT  trace=T, span=E, parent=C
         └─ lealtad SERVER trace=T, span=F, parent=E
```

Cada petición del navegador inicia su propio recorrido si no trae un contexto
válido. No se conserva una traza única para toda la sesión del cliente.

## Seguir una petición en local

Con el Compose normal levantado, desde PowerShell:

```powershell
$taskRequestId = [guid]::NewGuid().ToString()
$taskTraceId = [guid]::NewGuid().ToString('N')
$taskParentSpan = [guid]::NewGuid().ToString('N').Substring(0, 16)
$taskHeaders = @{
    'X-Request-ID' = $taskRequestId
    'traceparent' = "00-$taskTraceId-$taskParentSpan-01"
}
Invoke-RestMethod http://localhost:8000/health -Headers $taskHeaders
docker compose logs --no-color --no-log-prefix frontend svc-menu svc-pedidos svc-lealtad |
    Select-String -SimpleMatch $taskTraceId
```

`/health` recorre las dependencias y permite comprobar la correlación sin crear
un pedido. El mismo filtrado sirve para el `trace_id` de una compra o de un
error de negocio.

Uvicorn conserva sus mensajes operativos y de acceso en su formato habitual;
los eventos de la aplicación son las líneas JSON. El SDK ya permite exportar
spans por OTLP HTTP/protobuf o a stdout; por defecto conserva el contexto sin
exportación. Grafana ya consulta las métricas mediante el
[monitoreo local](local-monitoring.md). La
[extensión de logs y trazas](local-logs-traces.md) añade Alloy, Loki y Tempo y
permite abrir la traza desde un log y regresar a los logs del servicio.

## Desarrollo y verificación

Cada imagen mantiene su contexto de construcción independiente. Por eso cada
servicio contiene `app/observability.py` con el mismo comportamiento. La prueba
común compara los árboles sintácticos para impedir que esas copias diverjan.
Los cuatro componentes heredan las mismas reglas y formato del `ruff.toml` raíz.

Desde el directorio de cualquiera de los cuatro servicios, con sus dependencias
de desarrollo instaladas:

```powershell
.\.venv\Scripts\python.exe -m pytest -c pyproject.toml tests ../tests/observability -p no:cacheprovider
```

Las pruebas comunes cubren encabezados inválidos, spans reales, flags,
respuestas 404/422, fallos inesperados y aislamiento entre peticiones y
aplicaciones. También verifican el envío OTLP real y el vaciado al apagar el
proveedor. Los cuatro workflows de CI ejecutan este contrato.

La suite E2E crea una compra real y lee los logs y spans JSON exportados de los
cuatro contenedores para comprobar identificadores, clientes HTTP y consultas SQL:

```powershell
python -m pip install -r tests/requirements.txt
python scripts/run_e2e.py
```

Validación del 21 de noviembre de 2026:

| Entorno | Pruebas del servicio y contrato común |
|---|---:|
| Frontend | 18 aprobadas |
| Menú | 21 aprobadas |
| Pedidos | 27 aprobadas |
| Lealtad | 23 aprobadas |
| E2E con contenedores reales | 11 aprobadas en 15.52 segundos |

Ruff y formato pasan en los cuatro entornos; los tres contratos OpenAPI son
válidos. Se construyeron las cuatro imágenes. El ejecutor eliminó los
contenedores, la red y el volumen de datos de `cafeteria-e2e` al terminar; ese
volumen contenía únicamente los datos generados por las pruebas.
