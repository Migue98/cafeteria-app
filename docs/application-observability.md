# Logs y correlación entre servicios

Los cuatro servicios emiten eventos JSON en stdout. Cada petición conserva el
`X-Request-ID` y el `trace_id` a través de los saltos HTTP; cada servicio genera
su propio `span_id` y registra el anterior en `parent_span_id`.

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
| `parent_span_id` | Span recibido del servicio que hizo la llamada. |

`request_completed` añade `method`, `path`, `route`, `status_code` y
`duration_ms`. Usa `INFO` para respuestas menores de 400, `WARNING` para 4xx y
`ERROR` para 5xx. Las rutas de métricas usan la plantilla del endpoint para
evitar una serie distinta por cada UUID.

Una excepción inesperada registra además `request_failed`, con el detalle en
los logs internos, y contabiliza la petición como 500. No se registran cuerpos
de peticiones, cookies ni cabeceras de autorización.

Los eventos de resumen del worker no corresponden a una petición y llevan los
campos de correlación en `null`. Cada intento de recuperación de puntos sí
genera una traza nueva, registra `order_id` y propaga su contexto a lealtad.

## Encabezados

- `X-Request-ID`: si falta, el servicio genera un UUID; si es inválido, responde
  422 con un UUID nuevo y registra el rechazo.
- `traceparent`: se admite el formato W3C de versión `00`. Un encabezado válido
  conserva la traza y sus flags, pero genera un span nuevo para el servicio.
  Si falta, está mal formado o contiene identificadores de solo ceros, se inicia
  una traza nueva. Las versiones distintas de `00` también inician otra traza.
- Las respuestas atendidas por el middleware devuelven ambos encabezados.
  Los errores de negocio incluyen el mismo `trace_id` en su Problem JSON.

Ejemplo de una compra:

```text
frontend       trace=T, span=A
└─ svc-pedidos trace=T, span=B, parent=A
   ├─ svc-menu    trace=T, span=C, parent=B
   └─ svc-lealtad trace=T, span=D, parent=B
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
los eventos de la aplicación son las líneas JSON. Esta implementación permite
correlacionar logs; todavía no exporta spans a Tempo ni incorpora un SDK de
OpenTelemetry. Esa integración corresponde al bloque de observabilidad del
despliegue.

## Desarrollo y verificación

Cada imagen mantiene su contexto de construcción independiente. Por eso cada
servicio contiene `app/observability.py` con el mismo comportamiento. La prueba
común compara los árboles sintácticos para impedir que esas copias diverjan;
el formato puede diferir según la configuración de Ruff de cada servicio.

Desde el directorio de cualquiera de los cuatro servicios, con sus dependencias
de desarrollo instaladas:

```powershell
.\.venv\Scripts\python.exe -m pytest tests ../tests/observability -p no:cacheprovider
```

Las pruebas comunes cubren encabezados inválidos, spans nuevos, flags,
respuestas 404/422, fallos inesperados y aislamiento entre peticiones
concurrentes. Los cuatro workflows de CI ejecutan este contrato.

La suite E2E crea una compra real y lee los logs JSON de los cuatro contenedores
para comprobar `request_id`, `trace_id` y los enlaces entre spans:

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
