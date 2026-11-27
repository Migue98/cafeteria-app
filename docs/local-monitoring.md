# Prometheus y Grafana en local

El paso 2 añade monitoreo de métricas a los cuatro servicios mediante una
extensión opcional de Compose. Prometheus recoge `/metrics` y Grafana consulta
ese servidor por la red interna. La fuente de datos y una vista de conexión
se configuran automáticamente desde los archivos de `observability/`.

| Componente | Versión | Imagen |
|---|---|---|
| Prometheus | 3.16.0 | `prom/prometheus`, fijada por digest en el Compose. |
| Grafana OSS | 13.3.2 | `grafana/grafana`, fijada por digest en el Compose. |

El Compose normal sigue teniendo cinco servicios. Al añadir la extensión se
levantan siete. El [paso 4](local-dashboards-alerts.md) añade dashboards de
aplicación y negocio y reglas de Grafana; Telegram se activa por separado.
Alloy, Loki y Tempo ya están disponibles con la
[extensión del paso 3](local-logs-traces.md), que añade un tercer archivo Compose.

## Iniciar

Desde la raíz del repositorio:

```powershell
docker compose -f compose.yaml -f compose.monitoring.yaml up --build --detach
```

| Interfaz | URL predeterminada |
|---|---|
| Cafetería | http://localhost:8000 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |

Las interfaces nuevas se ligan a `127.0.0.1`. Grafana requiere iniciar sesión
y no permite registro público ni acceso anónimo. Los valores locales iniciales
son usuario `admin` y contraseña `local-grafana-change-me`; se pueden sustituir
con `GRAFANA_ADMIN_USER` y `GRAFANA_ADMIN_PASSWORD` en `.env`. El ejemplo está en
[`.env.example`](../.env.example). Estos valores son exclusivos del desarrollo.

Grafana crea la cuenta inicial al estrenar su base. Cambiar la variable de
contraseña después no modifica una cuenta ya guardada: cámbiala desde Grafana.
`PROMETHEUS_PORT` y `GRAFANA_PORT` permiten elegir otros puertos.

La vista **Conexión de métricas** muestra el número de targets UP y el estado
de scrape de cada servicio. `UP` significa que Prometheus pudo leer `/metrics`;
la disponibilidad de dependencias se consulta mediante `/health`.

## Cómo se conectan

```text
frontend:8000/metrics ────┐
svc-menu:8001/metrics ────┤
svc-pedidos:8002/metrics ─┼─ Prometheus:9090 ← Grafana:3000
svc-lealtad:8003/metrics ─┘
```

Prometheus consulta cada cinco segundos, con timeout de tres segundos. Los
targets reciben `job="cafeteria"` y una etiqueta `service` consistente con los
servicios. Se conservan las etiquetas de las métricas de aplicación mediante
`honor_labels`, sin crear duplicados `exported_service`.

La fuente de Grafana tiene UID `cafeteria-prometheus` y URL
`http://prometheus:9090`; no utiliza `localhost` para llegar al otro contenedor.
Es la fuente predeterminada, se provisiona al iniciar y se mantiene en Git.
La vista de conexión también se provisiona y sus cambios se hacen en el JSON.
El proveedor revisa los archivos cada 30 segundos para funcionar con los
montajes de Docker Desktop. No se descargan plugins adicionales al iniciar.

La extensión añade `frontend` a los hosts permitidos del frontend para aceptar
el scrape por su nombre DNS interno. La validación de hosts permanece activa;
el Compose normal conserva su configuración original.

## Consultar datos reales

En Prometheus, abre la página de consultas y ejecuta:

```promql
up{job="cafeteria"}
```

Deben aparecer `frontend`, `svc-menu`, `svc-pedidos` y `svc-lealtad` con valor 1.
Las mismas expresiones funcionan en **Explore** de Grafana seleccionando
**Prometheus**. Por ejemplo:

```promql
sum by (service) (http_requests_total{job="cafeteria"})
sum(cafe_orders_total{job="cafeteria",status="confirmed"})
sum(cafe_loyalty_points_total{job="cafeteria"})
```

Haz una compra en la cafetería y espera al siguiente scrape para observar el
nuevo pedido y los puntos. Los contadores pueden reiniciarse cuando se
recrea un proceso de aplicación; para tasas se usa `rate()` sobre el historial.

## Persistencia y límites

| Volumen Compose | Ruta en el contenedor | Contenido |
|---|---|---|
| `cafeteria-prometheus-data` | `/prometheus` | Series temporales y WAL de Prometheus. |
| `cafeteria-grafana-data` | `/var/lib/grafana` | Base SQLite, usuarios, preferencias y datos creados en Grafana. |

Compose antepone el nombre del proyecto a cada volumen. Los archivos de scrape
y provisioning se montan en modo lectura. Los dos contenedores tienen un límite
de 512 MiB de RAM cada uno. Prometheus conserva hasta siete días o el límite
de retención de 1 GB; su uso total de disco incluye también WAL y bloques activos.

Detener y conservar los datos:

```powershell
docker compose -f compose.yaml -f compose.monitoring.yaml down
```

Para volver a la aplicación sin monitoreo conservando los volúmenes:

```powershell
docker compose -f compose.yaml -f compose.monitoring.yaml down
docker compose up --detach
```

Añadir `--volumes` al `down` de la combinación elimina también la base de datos
de la cafetería de ese proyecto. El runner de pruebas utiliza un proyecto
independiente y solo elimina sus datos desechables.

## Pruebas automatizadas

Usa el entorno de [`tests/README.md`](../tests/README.md), con Chromium instalado:

```powershell
.\tests\.venv\Scripts\python.exe scripts/run_monitoring_e2e.py
```

El runner valida el Compose y el archivo Prometheus con `promtool`, construye
los servicios y ejecuta seis casos sobre Prometheus y Grafana reales:

1. Cuatro targets UP, métricas HTTP por servicio, fuente provisionada y autenticación.
2. Compra persistida cuyos pedidos y puntos se consultan a través de Grafana.
3. Recreación de Prometheus y Grafana conservando una muestra histórica y una
   anotación guardada antes del cambio de contenedores.
4. Inicio de sesión y visualización de los cuatro servicios en Chromium.
5. Consultas de los dashboards de aplicación y negocio válidas contra Prometheus
   y política local de notificaciones silenciada.
6. Visualización de los dos dashboards nuevos en Chromium.

El proyecto se llama `cafeteria-monitoring-e2e`. Usa puertos `28000`–`28003`,
`19090` y `13000`, y contraseñas aleatorias desechables. Los puertos se pueden
cambiar mediante `MONITORING_E2E_FRONTEND_PORT`, `MONITORING_E2E_MENU_PORT`,
`MONITORING_E2E_ORDERS_PORT`, `MONITORING_E2E_LOYALTY_PORT`,
`MONITORING_E2E_PROMETHEUS_PORT` y `MONITORING_E2E_GRAFANA_PORT`.

Se limpian sus siete contenedores, red y tres volúmenes al terminar, incluso
si falla una prueba. `KEEP_MONITORING_STACK=1` permite conservarlos para
inspección; antes de repetir el runner, baja ese proyecto con ambos archivos
y `--volumes`, pues cada ejecución genera nuevas credenciales de prueba.
La captura positiva y las trazas de fallos quedan en `test-results/monitoring/`,
excluido de Git. El workflow **Local monitoring** ejecuta el mismo runner y
publica esos artefactos durante siete días. Su matriz comprueba por separado
este modo y el modo completo `--telemetry --alerts`. Tras el paso 4, el runner
ejecuta seis casos en el modo básico y quince en el completo. Los dos modos
comparten proyecto y puertos; ejecútalos de forma secuencial en local.

Las consultas de prueba utilizan las APIs `/api` de Grafana que siguen
disponibles en la versión fijada. Grafana 13 las marca como heredadas; al
actualizar la imagen se revisarán las equivalencias de sus nuevas APIs.

Referencias: [Prometheus en Docker](https://prometheus.io/docs/prometheus/latest/installation/),
[configuración de scrape](https://prometheus.io/docs/prometheus/latest/configuration/configuration/),
[Grafana en Docker](https://grafana.com/docs/grafana/latest/setup-grafana/installation/docker/),
[provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/) y
[API de fuentes de datos](https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/api-legacy/data_source/).

## Evidencia local — 26 de noviembre de 2026

| Comprobación | Resultado |
|---|---|
| Configuración Prometheus | `promtool check config` aprobó el archivo real montado. |
| Integración | Cuatro pruebas aprobadas en 70.26 segundos. |
| Scrape | Los cuatro targets aparecieron UP y expusieron métricas HTTP con su etiqueta de servicio. |
| Grafana | Fuente Prometheus predeterminada, provisionada y funcional; API protegida ante acceso anónimo. |
| Compra | Un pedido de $70 y siete puntos se guardaron y sus contadores se consultaron a través de Grafana. |
| Persistencia | Después de recrear ambos contenedores, se recuperaron una muestra histórica exacta y una anotación de Grafana. |
| Navegador | Chromium inició sesión y mostró 4 / 4 y los cuatro servicios UP, sin errores de JavaScript. |
| Herramientas | Ruff, formato, enlaces locales y sintaxis YAML del workflow correctos. |

La captura revisada visualmente quedó en
`test-results/monitoring/grafana-connected.png`, fuera de Git. El runner eliminó
sus siete contenedores, red y tres volúmenes; la aplicación normal permaneció
apagada. El workflow está preparado localmente y su ejecución remota se realizará
al publicar los cambios. La advertencia conocida de la fixture `base_url` de
Playwright sigue presente y no causó fallos.

Después de incorporar Alloy, Loki y Tempo se repitió este modo de solo métricas:
las cuatro pruebas volvieron a pasar en 72.65 segundos. El modo completo aprobó
nueve pruebas; la evidencia está en la [guía del paso 3](local-logs-traces.md).

Con el paso 4, el modo básico incorpora dashboards y la política local de
notificaciones: aprobó seis pruebas en 123.97 segundos. El modo completo con
alertas aprobó quince; consulta su [evidencia](local-dashboards-alerts.md).
