# Entrega del software al equipo

Esta es la entrada para que Miguel, Alicia (`aliceaislinn`) y Martín
(`mquinteror1000`) levanten, modifiquen y prueben la misma aplicación.
Los comandos se ejecutan desde la raíz de `cafeteria-app`, salvo indicación.
La ruta principal usa Windows, PowerShell y Docker Desktop con contenedores Linux,
el entorno utilizado en la validación local.

## Qué está disponible

| Parte | Estado de la copia de trabajo |
|---|---|
| Web y APIs | Menú de 20 productos, categorías, carrito, compra, recibo, historial y puntos. |
| Datos | PostgreSQL persistente; SQL inicial separado entre los tres backends. |
| Recuperación | Pedidos reintenta puntos pendientes al iniciar y cada 15 minutos; la web consulta el estado cada 15 segundos mientras estén pendientes. |
| Seguridad de la web | CSRF con biblioteca, sesiones firmadas, CSP, recursos locales, hosts y configuración de producción. |
| Observabilidad local | Métricas, dashboards, alertas, logs, trazas y envío opcional a Telegram. |
| Pruebas | Componentes, HTTP integral, Chromium y plataforma de observabilidad en entornos aislados. |
| Entrega pública | Pendiente: integración con infraestructura, HTTPS, Kubernetes, Tekton y Argo CD. |

El catálogo permite consultar y comprar; no hay panel de administración,
cuentas públicas ni procesamiento de pagos. El cliente se identifica mediante
su sesión: otra sesión o borrar sus cookies inicia un historial distinto.
El total del pedido no representa un cobro. El alcance completo está en la
[especificación](application-specification.md).

## 1. Preparar una copia

Necesitas Git, Docker Desktop iniciado con contenedores Linux y Docker Compose v2.
Python 3.13 se necesita para las herramientas y las pruebas del host; para usar
la web basta con Docker. `.python-version`, las imágenes y CI fijan 3.13.18;
los entornos Windows ya validados usan 3.13.1. Consulta las
[herramientas comunes](development-tooling.md) antes de cambiar versiones.

```powershell
git clone --branch main https://github.com/Migue98/cafeteria-app.git
Set-Location cafeteria-app
git rev-parse --short HEAD
git status --short
docker version
docker compose version
py -3.13 --version
```

Si ya tienes la carpeta, entra a ella y revisa el estado antes de actualizar;
conserva tus modificaciones locales. Al reportar un problema, incluye el commit
y si hay cambios sin commit: las pruebas de una copia modificada no certifican
automáticamente el `main` remoto.

Crea la configuración local sin sobrescribir una existente:

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
git check-ignore .env
```

El último comando debe mostrar `.env`. Los valores del ejemplo sirven para
desarrollo local. Cada integrante conserva sus propios secretos; Telegram es
opcional y sus dos campos pueden quedar vacíos. No copies el `.env` de otro
equipo ni lo subas a Git. Para una base ya inicializada, cambiar
`POSTGRES_PASSWORD` no cambia la contraseña guardada en PostgreSQL.

## 2. Levantar y comprobar la aplicación

```powershell
docker compose -f compose.yaml config --quiet
docker compose -f compose.yaml up --build --detach
docker compose -f compose.yaml ps
Invoke-RestMethod http://localhost:8000/health
```

Espera a que los cinco servicios aparezcan como `healthy`. La primera ejecución
descarga las imágenes y construye los cuatro componentes. PostgreSQL ejecuta
los tres esquemas `db/init.sql` y después `svc-menu/db/seed.sql` solo sobre un
volumen vacío; no hay que importarlos a mano. El seed no sobrescribe productos.
Consulta la [inicialización de BD](database-initialization.md) para bases existentes.

| Componente | URL del host | Uso |
|---|---|---|
| Frontend | http://localhost:8000 | Aplicación del usuario. |
| Menú | http://localhost:8001/docs | API del catálogo. |
| Pedidos | http://localhost:8002/docs | API de compras e historial. |
| Lealtad | http://localhost:8003/docs | API de saldo y movimientos. |
| PostgreSQL | Sin puerto publicado al host | Los servicios acceden por la red interna de Compose. |

En el navegador:

1. Abre la web, filtra una categoría y regresa a Todo.
2. Agrega un producto, cambia su cantidad y comprueba el total.
3. Confirma el pedido y abre Mis pedidos; deben aparecer el pedido y sus puntos.
4. Repite con un ancho móvil: Menú, Mis pedidos y Carrito deben seguir visibles.

Para la comprobación rápida por script:

```powershell
py -3.13 scripts/validate_contracts.py
py -3.13 tests/smoke/check_compose.py
```

El primero informa `Contratos válidos: 3`. El segundo crea un cliente y un
pedido de prueba en **tu base local**, verifica puntos e idempotencia y muestra
un resumen JSON. No detiene servicios ni limpia esos datos. Usa los puertos
predeterminados 8000–8003; si los cambiaste, usa el recorrido manual o el runner
aislado. La [integración local](local-integration.md) detalla tablas y servicios.

## 3. Elegir observabilidad

Elige una combinación y conserva los mismos `-f`, en el mismo orden, para
`config`, `up`, `ps`, `logs` y `down`. No necesitas Telegram para ver las reglas.

| Modo | Archivos, en orden | Qué añade |
|---|---|---|
| Aplicación | `compose.yaml` | Web, backends y PostgreSQL. |
| Métricas | Los anteriores + `compose.monitoring.yaml` | Prometheus, Grafana, tres dashboards y reglas. |
| Métricas, logs y trazas | Los anteriores + `compose.telemetry.yaml` | Alloy, Loki y Tempo; exportación OTLP. |
| Avisos reales | Métricas, con o sin telemetry, + `compose.telegram.yaml` al final | Notificaciones de Grafana al chat configurado. |

Para métricas, logs y trazas:

```powershell
docker compose -f compose.yaml -f compose.monitoring.yaml -f compose.telemetry.yaml config --quiet
docker compose -f compose.yaml -f compose.monitoring.yaml -f compose.telemetry.yaml up --build --detach
```

Abre [Grafana](http://localhost:3000) con `GRAFANA_ADMIN_USER` y
`GRAFANA_ADMIN_PASSWORD` de tu `.env`. La cuenta se crea al estrenar el volumen:
cambiar luego esas variables no cambia una cuenta existente; usa Grafana para
cambiar su contraseña. La carpeta **Cafetería local** contiene Conexión de
métricas, Cafetería · aplicación y Cafetería · negocio.

En [Prometheus](http://localhost:9090), `up{job="cafeteria"}` debe dar cuatro
series con valor 1. Haz una compra para generar tráfico; los paneles de tasas
necesitan datos recientes. En Explore de Grafana selecciona Loki y consulta
`{job="cafeteria"} | json | message="request_completed"`; abre los detalles
de una línea y Ver traza para llegar a Tempo. Los datos tardan unos segundos.

En este modo hay diez contenedores en ejecución y un auxiliar
`telemetry-storage-init` terminado con código 0: es el resultado esperado.
Alloy usa el socket Docker para recoger logs del proyecto local. Las interfaces
de observabilidad se ligan a localhost. Para detalles y límites, consulta
[métricas](local-monitoring.md), [logs y trazas](local-logs-traces.md) y
[dashboards y alertas](local-dashboards-alerts.md).

Para Telegram guarda `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` en tu `.env` y
añade la extensión al final:

```powershell
docker compose -f compose.yaml -f compose.monitoring.yaml -f compose.telemetry.yaml -f compose.telegram.yaml config --quiet
docker compose -f compose.yaml -f compose.monitoring.yaml -f compose.telemetry.yaml -f compose.telegram.yaml up --build --detach
```

La [guía de alertas](local-dashboards-alerts.md#notificaciones-locales-y-telegram)
explica cómo obtener el chat ID y comprobar el destino. Un Test del contacto
sí manda un mensaje real. La configuración sin Telegram mantiene visibles las
reglas y silencia notificaciones. Usa `config --quiet` para validar sin mostrar
credenciales resueltas.

## 4. Ejecutar las pruebas aisladas

Prepara un entorno separado para las pruebas que abarcan varios servicios:

```powershell
py -3.13 -m venv tests/.venv
.\tests\.venv\Scripts\python.exe -m pip install --require-hashes -r tests/requirements.txt
.\tests\.venv\Scripts\python.exe -m playwright install chromium
.\tests\.venv\Scripts\python.exe scripts/run_e2e.py
```

El runner valida contratos, construye `cafeteria-e2e`, ejecuta **31 casos HTTP
y 12 con Chromium** y elimina sus recursos y datos desechables al terminar.
Usa 18000–18003, separados del entorno normal. Algunos casos detienen servicios:
ejecútalos en serie mediante el runner, sin cambiar el proyecto a tu entorno
normal. `--suite http` o `--suite browser` selecciona una parte.
Capturas y trazas quedan en `test-results/browser/`; la
[guía del navegador](browser-testing.md) explica cómo abrirlas.

Con el mismo entorno, para cambios de observabilidad:

```powershell
# Métricas y dashboards: 6 casos.
.\tests\.venv\Scripts\python.exe scripts/run_monitoring_e2e.py
# Plataforma completa y alertas: 15 casos.
.\tests\.venv\Scripts\python.exe scripts/run_monitoring_e2e.py --telemetry --alerts
```

Cada ejecución prepara y limpia `cafeteria-monitoring-e2e`. Usa 28000–28003
para la app y puertos distintos para el monitoreo; comprueba la lista completa
en [`run_monitoring_e2e.py`](../scripts/run_monitoring_e2e.py). Sus alertas van a
un webhook interno de prueba: no carga la extensión de Telegram. Ejecuta ambos
modos uno después del otro. Más opciones en la [guía de pruebas](../tests/README.md).

## 5. Modificar un componente

Cada componente tiene un entorno y locks propios. Ejemplo desde la raíz:

```powershell
Push-Location frontend
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check app tests ../tests/observability
.\.venv\Scripts\python.exe -m ruff format --check app tests ../tests/observability
.\.venv\Scripts\python.exe -m pytest -c pyproject.toml tests ../tests/observability -p no:cacheprovider
Pop-Location
```

Sustituye `frontend` por `svc-menu`, `svc-pedidos` o `svc-lealtad` para trabajar
en otro componente. `main.py` conecta la aplicación; las rutas, lógica y
presentación se describen en la [organización del código](code-organization.md).
Los contenedores no montan el código con recarga: después de editar reconstruye
el componente con `up --build --detach --no-deps frontend`, usando tu combinación
Compose completa. Si cambia SQL inicial, prepara una migración para bases
existentes; reconstruir la imagen no migra el volumen.

| Cambio | Validación que corresponde |
|---|---|
| Python de un componente | Ruff, formato y pytest del componente con el contrato común. |
| Rutas, cuerpos o estados de una API | Actualizar primero OpenAPI y ejecutar el validador, pruebas del componente y E2E. |
| Formularios, plantillas, CSS o HTMX | Pruebas del frontend y runner HTTP + Chromium; revisar capturas. |
| Compose o dependencias de la aplicación | Validar la combinación Compose y ejecutar E2E. |
| Dashboards, alertas o colectores | Runner de monitoreo en el modo afectado. |
| Documentación | Enlaces, rutas y comandos contra la configuración vigente. |

Se mantienen [Issues, cambios acotados y revisión](../CONTRIBUTING.md). El repositorio
de [GitOps](https://github.com/Migue98/cafeteria-gitops) se retomará con
infraestructura; la aplicación y su plataforma local se desarrollan aquí.

## 6. Detener y resolver problemas

Para conservar datos, usa `down` con tu combinación completa. Ejemplo del modo
con logs y trazas:

```powershell
docker compose -f compose.yaml -f compose.monitoring.yaml -f compose.telemetry.yaml down
```

Incluye también `-f compose.telegram.yaml` si lo usaste. Al cambiar a un modo
más pequeño, baja primero la combinación anterior y luego inicia la nueva.
Conservar el mismo nombre de proyecto permite reutilizar sus volúmenes.
`down --volumes` elimina los datos de **todos los volúmenes de esa combinación**,
incluidos pedidos y usuarios de Grafana; no es necesario para detener el sistema.

| Síntoma | Comprobación o solución |
|---|---|
| Docker no responde | Iniciar Docker Desktop y comprobar `docker version`; usar contenedores Linux. |
| Puerto ocupado | Cerrar el proceso que lo ocupa o ajustar los puertos del `.env`; los de APIs son `MENU_PORT`, `ORDERS_PORT` y `LOYALTY_PORT`, además de `FRONTEND_PORT`. |
| Un servicio no está healthy | Usar `ps` y `logs --tail 80 nombre-del-servicio` con los mismos archivos Compose. Revisar primero PostgreSQL y las dependencias. |
| Web 400 por host o 403 por origen/cookie | Abrir `http://localhost:8000` en desarrollo y revisar `APP_ENV`, `ALLOWED_HOSTS`, `PUBLIC_ORIGIN` y `SESSION_HTTPS_ONLY`. Para hosts o HTTPS distintos, seguir la guía de seguridad. |
| Falta Chromium | Ejecutar `tests/.venv` con `-m playwright install chromium`, no el Python de otro entorno. |
| Grafana no acepta una contraseña nueva del `.env` | La cuenta persiste en su volumen; cambiarla en Grafana en vez de borrar todos los datos. |
| No hay gráficas o trazas | Comprobar el modo Compose, los cuatro targets de Prometheus, generar tráfico y esperar recolección. |
| Puntos pendientes | Esperar el worker de pedidos y el polling de la web; ver las guías de recuperación antes de volver a comprar. |

Consulta también [seguridad web](web-security.md),
[reintentos de puntos](automatic-loyalty-retry.md) y
[recuperación de la interfaz](frontend-loyalty-recovery.md) para esos diagnósticos.

Los logs pueden contener identificadores de pedidos y clientes; comparte solo
el fragmento necesario. No publiques `.env`, salidas de `config` sin `--quiet`
ni tokens en capturas o Issues.

En Linux, crea los entornos con `python3.13 -m venv ...`, sustituye
`Scripts/python.exe` por `bin/python` e instala Chromium con
`python -m playwright install --with-deps chromium` usando el entorno de tests.
`cp -n .env.example .env` conserva un `.env` existente. La alternativa Podman
se documenta en las guías, pero la plataforma local completa se validó con Docker.

## Evidencia y pendientes de entrega

La validación del software del 26–27 de noviembre de 2026 registró 3 contratos
válidos, 93 pruebas de frontend/observabilidad común, 31 HTTP y 12 de Chromium
aprobadas. La [revisión de usabilidad](visual-usability-review.md) conserva los
tiempos y el alcance. La evidencia de los 15 escenarios de la plataforma está
en [dashboards y alertas](local-dashboards-alerts.md); corresponde a su propia
ejecución previa. Son resultados locales, no una certificación de CI remoto.

El 27 de noviembre de 2026 se comprobó esta documentación: sintaxis de los
21 bloques PowerShell, 111 enlaces locales y sus anclas, rutas de los cuatro
componentes, contratos y opciones reales de los runners. Las cinco combinaciones
locales de Compose y la plantilla pública pasaron `config --quiet` con valores
de ejemplo y credenciales sintéticas; también se verificaron sus montajes.
Los cuatro `/health` y `/docs`, Grafana y los cuatro targets de la consulta
documentada de Prometheus respondieron correctamente. Esta revisión documental
no volvió a ejecutar las suites de aplicación ni modificó servicios o datos.

Para completar la entrega compartida:

- Elegir el commit compartido en `main` y comprobar que sus workflows terminaron
  con `success` en [GitHub Actions](https://github.com/Migue98/cafeteria-app/actions).
- Alicia y Martín reproducen esta guía desde ese mismo commit en sus propios equipos.
- Registrar sistema operativo, commit, comandos y resultados; reportar diferencias
  mediante un Issue sin secretos.
- Coordinar después los datos de infraestructura, despliegue HTTPS y pipeline
  del [plan del software](software-roadmap.md). La
  [plantilla pública](../compose.public.yaml) requiere Compose 2.24.4+ y un proxy
  HTTPS configurado por separado; no publica la aplicación por sí sola.
