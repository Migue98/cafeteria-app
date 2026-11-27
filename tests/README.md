# Pruebas compartidas e integrales

Si es tu primera copia del proyecto, empieza por la
[guía de entrega al equipo](../docs/team-handoff.md) para configurar el entorno.

## Organización

| Ubicación | Contenido |
|---|---|
| [`smoke/check_compose.py`](smoke/check_compose.py) | Comprobación rápida manual del Compose local ya levantado. |
| [`e2e/`](e2e/) | Escenarios pytest de compra, concurrencia, fallas y seguridad sobre servicios reales. |
| [`browser/`](browser/) | Chromium real con Playwright: clics, carrito, checkout, historial y temporizadores de HTMX. |
| [`monitoring/`](monitoring/) | Prometheus, Grafana y, opcionalmente, Alloy/Loki/Tempo: métricas, logs, trazas, persistencia y Chromium. |
| [`conftest.py`](conftest.py) y [`support.py`](support.py) | Fixtures de Compose, clientes HTTP y consulta de datos compartidos. |
| [`observability/`](observability/) | Contrato de logs y propagación de trazas, ejecutado con cada componente. |
| `frontend/tests/` y `svc-*/tests/` | Pruebas específicas de cada componente, dentro de su carpeta. |

Los comandos auxiliares viven en `scripts/`: el ejecutor `run_e2e.py` prepara
el entorno y llama a pytest; `validate_contracts.py` revisa OpenAPI; y
`compile_requirements.py` genera locks. Los escenarios de prueba permanecen
en las carpetas `tests/`.

## Comprobación rápida local

Con el Compose normal ya levantado en los puertos `8000` a `8003`, desde la raíz:

```powershell
python tests/smoke/check_compose.py
```

Esta comprobación usa la biblioteca estándar de Python y crea un pedido con un
cliente e identificador nuevos en la base local. No levanta ni limpia Compose.
Se ejecuta explícitamente como script; los escenarios de pytest están en `e2e/` y `browser/`.

## Suite E2E

Las suites HTTP y de navegador verifican el frontend, los tres servicios y
PostgreSQL reales dentro de Compose. No usan dobles ni repositorios en memoria.
Los casos de `e2e/` usan HTTP con cookies; los de `browser/` ejecutan JavaScript
en Chromium mediante el plugin oficial `pytest-playwright`.

## Alcance

- salud y correlación mediante `X-Request-ID`;
- correlación de una compra entre los logs y spans OpenTelemetry exportados
  por los cuatro servicios, con clientes HTTP y consultas PostgreSQL;
- catálogo, precios y disponibilidad reales;
- compra completa `menú → pedido → puntos`;
- compra desde la interfaz HTML y consulta posterior del historial;
- consulta posterior del pedido y saldo;
- idempotencia sin duplicar pedidos ni puntos;
- compras y acreditaciones simultáneas, doble envío del checkout, claves alternas
  reservadas, migración idempotente y saldo contrastado con PostgreSQL;
- recuperación automática de puntos después de restaurar `svc-lealtad`;
- historial accesible sin lealtad y actualización de los fragmentos de puntos,
  sin repetir pedidos ni acreditaciones;
- errores de validación y conflictos;
- métricas HTTP y de negocio;
- persistencia después de reiniciar PostgreSQL;
- fallas reales de menú, pedidos y PostgreSQL; timeouts de lectura al pausar
  menú o lealtad; recuperación conservando carrito, pedidos y saldo;
- protección CSRF activa en formularios y HTMX, rechazo de otros orígenes y
  hosts, CSP y carga de HTMX sin CDN.
- clics reales para agregar, aumentar, disminuir y eliminar productos, compra
  y consulta del historial en anchos de escritorio y móvil;
- actualización automática de recibo e historial mediante HTMX tras recuperar
  lealtad, sin recargar la página ni duplicar pedidos o puntos;
- ausencia de errores de JavaScript, consola y red durante estos recorridos.

## Ejecución

Desde la raíz del repositorio:

```powershell
py -3.13 -m venv tests/.venv
.\tests\.venv\Scripts\python.exe -m pip install --require-hashes -r tests/requirements.txt
.\tests\.venv\Scripts\python.exe -m playwright install chromium
.\tests\.venv\Scripts\python.exe scripts/run_e2e.py
```

En Linux, usa `python3.13 -m venv tests/.venv` y `tests/.venv/bin/python`.
La instalación de Chromium en Linux necesita
`python -m playwright install --with-deps chromium`; CI lo ejecuta automáticamente.

El ejecutor valida primero los contratos OpenAPI, levanta el proyecto aislado
`cafeteria-e2e` en los puertos `18000` a `18003`, ejecuta HTTP y luego Chromium,
y finalmente elimina sus contenedores, red y volumen. No toca el Compose local
normal. Ejecuta los comandos siguientes con el Python de `tests/.venv` activo:

```powershell
# Recorrido completo: 31 casos HTTP y 12 casos de navegador.
python scripts/run_e2e.py
# Ejecutar solo una de las suites con el mismo aislamiento y limpieza.
python scripts/run_e2e.py --suite http
python scripts/run_e2e.py --suite browser
```

Las trazas y capturas de casos fallidos se guardan en `test-results/browser/`,
excluido de Git. Las capturas positivas de cinco anchos, teclado y estados de
error/puntos pendientes se guardan en `test-results/browser/usability/`.
Consulta la [guía de Playwright](../docs/browser-testing.md)
para abrir una traza y depurar con el navegador visible.

Para conservar el entorno cuando falle una prueba:

```powershell
$env:KEEP_E2E_STACK = "1"
python scripts/run_e2e.py
```

Para usar Podman:

```powershell
$env:CONTAINER_ENGINE = "podman"
python scripts/run_e2e.py
```

## Contrato común de observabilidad

Los cuatro workflows ejecutan `tests/observability` con el entorno de cada
servicio. Desde el directorio del servicio, con sus dependencias instaladas:

```powershell
python -m pytest -c pyproject.toml tests ../tests/observability -p no:cacheprovider
```

Esta suite comprueba trazas, logs de errores, aislamiento concurrente y paridad
de la implementación común, además de enviar y decodificar protobuf OTLP
contra un receptor HTTP de prueba. Consulta la
[guía de logs y correlación](../docs/application-observability.md) y
[OpenTelemetry](../docs/opentelemetry-tracing.md).

El runner E2E habilita `OTEL_TRACES_EXPORTER=console` y lotes de 100 ms para
comprobar los spans reales de la compra en los contenedores. El Compose normal
conserva por defecto el contexto sin exportación. La prueba no necesita Tempo.

## Concurrencia y ejecución continua

`tests/e2e/test_concurrency.py` sincroniza las solicitudes y comprueba pedidos,
movimientos y saldo persistidos. La [guía de concurrencia](../docs/concurrency-and-idempotency.md)
describe los casos y la migración de claves de lealtad.

El workflow `Integrated E2E` instala Chromium y ejecuta el mismo flujo Compose
en pushes a `main` y Pull Requests que afecten a la aplicación. Publica las
trazas de fallos y capturas de usabilidad en el artefacto `browser-evidence`
durante siete días.
Las pruebas se mantienen en serie a
nivel de escenario: no uses `pytest-xdist` sobre este proyecto compartido.

## Monitoreo local opcional

`python scripts/run_monitoring_e2e.py` prepara el proyecto aislado
`cafeteria-monitoring-e2e` con `compose.yaml` y `compose.monitoring.yaml`.
Valida Prometheus con `promtool` y ejecuta cuatro escenarios de métricas,
Grafana, persistencia tras recrear contenedores y navegador real, además de dos
casos de consultas y visualización de los dashboards. La
[guía de monitoreo](../docs/local-monitoring.md) detalla puertos y evidencias.

La suite de monitoreo se selecciona explícitamente mediante su runner;
`run_e2e.py` mantiene las 31 pruebas HTTP y doce de navegador de la app.
El workflow `Local monitoring` ejecuta las nuevas pruebas por separado.

```powershell
# Métricas y dashboards: seis casos.
python scripts/run_monitoring_e2e.py
# Métricas, dashboards, logs y trazas: once casos.
python scripts/run_monitoring_e2e.py --telemetry
# Todos los anteriores y reglas/notificaciones: quince casos.
python scripts/run_monitoring_e2e.py --telemetry --alerts
```

El segundo modo añade `compose.telemetry.yaml`, valida las configuraciones con
las herramientas nativas de Alloy, Loki y Tempo y comprueba una compra y una
falla de menú con logs y spans correlacionados. También recrea el colector y
los almacenamientos y navega log → traza → logs en Grafana con Chromium.
La [guía de logs y trazas](../docs/local-logs-traces.md) detalla el recorrido,
puertos, alcance del socket Docker y evidencia.

Ambos modos usan el mismo proyecto y puertos: ejecútalos en serie en el equipo.
Los escenarios detienen y recrean servicios; no uses `pytest-xdist`.
Se generan credenciales nuevas y se eliminan sus datos desechables al terminar.
El modo completo limpia seis volúmenes. Si conservas el entorno con
`KEEP_MONITORING_STACK=1`, bájalo con los archivos correspondientes y
`--volumes` antes de repetir. El workflow usa jobs independientes para los dos
modos y conserva capturas y trazas de fallos durante siete días.

La [guía de dashboards y alertas](../docs/local-dashboards-alerts.md) describe
el modo `--alerts`: añade cuatro casos, un receptor webhook interno y esperas
de evaluación reducidas. Provoca caídas de menú y lealtad y verifica avisos
de alerta y recuperación del mismo incidente. No conecta Telegram ni requiere
credenciales externas. Se puede ejecutar sin trazas con `--alerts` (diez casos).

## Seguridad web

El cliente de navegador HTTP abre primero el menú, conserva la cookie de sesión
y extrae el token CSRF que se incluye en los formularios. No se desactiva la
protección para ejecutar pruebas. Las peticiones crudas de los casos negativos
omiten o falsifican el token/origen deliberadamente.

`frontend/tests/test_security.py` cubre también la configuración de producción,
cookies `Secure`/`HttpOnly`, cabeceras en errores, aislamiento entre sesiones,
límite de cuerpo y el hash del HTMX vendorizado. La suite E2E comprueba el flujo
real con las mismas defensas. Consulta [Seguridad web](../docs/web-security.md).
