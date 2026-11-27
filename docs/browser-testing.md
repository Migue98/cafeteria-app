# Pruebas con navegador real

El paso 2 del cierre del software automatiza el uso de la web con Chromium y
JavaScript habilitado. Se usa Playwright 1.65.2 con su plugin oficial
`pytest-playwright` 0.10.0 y pytest 9.2.0. Las versiones y hashes están fijados
en `tests/requirements.txt`; Chromium se instala mediante esa misma versión
de Playwright. No se incluye un navegador en las imágenes de la aplicación.

## Escenarios

| Caso | Qué comprueba |
|---|---|
| Compra en escritorio, 1280 × 800 | Menú, agregar, aumentar, disminuir, eliminar, carrito vacío, total, compra, recibo e historial. |
| Compra a 390 × 844 | El mismo recorrido con un ancho móvil y desplazamiento real hasta los controles. |
| Puntos pendientes en recibo | Comprar con lealtad detenido, restaurarlo y observar la actualización automática. |
| Puntos pendientes en historial | Conservar el pedido y mostrar saldo no disponible durante la caída; actualizar estado y saldo al recuperarse. |

Los clics del carrito deben producir peticiones HTMX con token CSRF y sin una
nueva navegación. Las defensas CSRF y CSP continúan activas. Los casos de
recuperación dejan que el JavaScript ejecute el temporizador real de 15 segundos:
no recargan la página, inyectan peticiones ni acortan ese temporizador.
Al acreditarse los puntos, debe desaparecer `hx-trigger`.

Cada caso crea una sesión independiente. Se contrastan los resultados visibles
con la API de pedidos, el saldo de lealtad y los movimientos guardados en
PostgreSQL. Cada cliente debe tener un pedido y una sola acreditación.
Los errores de JavaScript, consola, HTTP y solicitudes fallidas provocan un fallo.

La revisión visual del paso 3 amplía la suite a doce casos: añade cinco anchos
(320, 390, 768, 1280 y 1440 px), navegación por teclado, filtros, indicadores
de carga, errores del carrito y reintento del checkout. Los casos de puntos
pendientes también se revisan a 320 px. La evidencia y los ajustes se describen
en la [revisión de usabilidad](visual-usability-review.md).
Esta suite se ejecuta en Chromium; Firefox y WebKit quedan fuera de esta validación.

## Ejecutar

Sigue la [preparación del entorno de pruebas](../tests/README.md#ejecución).
Desde la raíz, con el Python de `tests/.venv` activo:

```powershell
python scripts/run_e2e.py
python scripts/run_e2e.py --suite browser
```

El runner valida los contratos, construye y levanta `cafeteria-e2e`, usa los
puertos `18000` a `18003` y elimina los recursos de ese proyecto al terminar,
incluso si pytest falla. El worker de pruebas reintenta puntos cada dos
segundos; la interfaz conserva el intervalo de 15 segundos de la aplicación.
El Compose normal y su volumen permanecen separados.

`--suite http` conserva el recorrido HTTP existente sin iniciar un navegador.
No ejecutes varios runners a la vez ni uses `pytest-xdist`: los escenarios de
fallas detienen servicios del mismo entorno aislado.

## Depurar y revisar evidencias

Ante un fallo, pytest conserva una traza y una captura de página completa en
`test-results/browser/<caso>/`. La traza permite revisar acciones, DOM, consola
y peticiones con el visor local:

```powershell
python -m playwright show-trace "test-results/browser/<caso>/trace.zip"
```

Para conservar el entorno y repetir un caso con Chromium visible:

```powershell
$env:KEEP_E2E_STACK = "1"
python scripts/run_e2e.py --suite browser
python -m pytest -c pytest.ini tests/browser -m browser --browser chromium --headed -k receipt
Remove-Item Env:KEEP_E2E_STACK
docker compose -p cafeteria-e2e down --volumes --remove-orphans
```

Si cambiaste puertos o motor, conserva también las variables `E2E_*` indicadas
en el runner. La limpieza anterior usa los valores predeterminados de Docker.
Las capturas y trazas contienen datos y cookies del entorno de prueba y no se
versionan. En CI se publican durante siete días solo cuando hay evidencias
disponibles. El artefacto se llama `browser-evidence` e
incluye las capturas positivas de `usability/` y los diagnósticos de fallos.

## Organización e integración continua

Los casos viven en `tests/browser/`; `scripts/run_e2e.py` prepara el entorno y
selecciona suites. `tests/conftest.py` comparte las fixtures de servicios y la
consulta de PostgreSQL. `tests/support.py` contiene los clientes HTTP de apoyo;
el fixture HTTP llamado `browser` queda limitado a `tests/e2e/`, separado del
navegador real de Playwright.

`Integrated E2E` instala las dependencias desde el lock, instala Chromium con
sus dependencias del sistema, comprueba Ruff y formato y ejecuta el runner
completo. No se deshabilitan pruebas ni se sustituyen servicios en CI.

Los workflows también permiten **Run workflow** (`workflow_dispatch`) sobre
`main`. Para las caídas de pedidos, la restauración utiliza
`compose up --detach --no-deps --no-recreate`: arranca el contenedor interrumpido
y conserva los demás. Las comprobaciones HTTP esperan después a los cuatro
servicios. Esto evita que un `compose start` fallido deje pedidos apagado y
provoque errores en cascada en los casos siguientes; la salida de restauración
queda visible en el log de CI.

Referencias: [Playwright para pytest](https://playwright.dev/python/docs/test-runners),
[aserciones y esperas](https://playwright.dev/python/docs/test-assertions) y
[visor de trazas](https://playwright.dev/python/docs/trace-viewer-intro).

## Validación local — 26 de noviembre de 2026

Se ejecutó `python scripts/run_e2e.py` completo con Python 3.13.1 en Windows,
Docker Desktop y los locks instalados con verificación de hashes. Las imágenes
conservan Python 3.13.18. Las cuatro pruebas de navegador usaron Chromium
159.0.8154.6, revisión 1255 de Playwright.

| Comprobación | Resultado |
|---|---|
| Contratos OpenAPI | 3 válidos. |
| HTTP integral | 31 casos aprobados en 149.22 segundos. |
| Chromium, con JavaScript y HTMX | 4 casos aprobados en 56.28 segundos. |
| Frontend y observabilidad común | 79 casos aprobados. |
| Menú y observabilidad común | 21 casos aprobados. |
| Pedidos y observabilidad común | 40 casos aprobados. |
| Lealtad y observabilidad común | 24 casos aprobados. |
| Ruff, formato y dependencias del entorno de pruebas | Correctos, sin conflictos de dependencias. |
| Workflow E2E | YAML válido; preparado localmente, sin ejecución remota en este paso. |

Los recorridos no registraron errores de JavaScript, consola, HTTP ni red.
La recuperación de puntos conservó un solo pedido, un solo movimiento y el
saldo esperado en PostgreSQL. El runner eliminó sus contenedores, red y volumen
al terminar; la aplicación normal permaneció apagada.

pytest emitió una advertencia de deprecación sobre la fixture `base_url` del
plugin Playwright. No se ocultó ni impidió ejecutar los casos; los componentes
mantienen la advertencia previamente conocida de Starlette con HTTPX.
