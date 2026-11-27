# Frontend

Interfaz server-side de la cafetería construida con FastAPI, Jinja y HTMX. El
navegador habla únicamente con este servicio; el frontend consume por HTTP a
`svc-menu`, `svc-pedidos` y `svc-lealtad` mediante sus nombres DNS.

## Flujo disponible

1. Consulta y filtrado del menú.
2. Carrito persistido en una cookie firmada y compatible con varias réplicas.
3. Confirmación idempotente del pedido.
4. Recibo con total y puntos obtenidos.
5. Historial de pedidos y saldo actual.

Si lealtad está caído, el historial conserva los pedidos y muestra **Saldo no
disponible**. El recibo y el historial consultan el estado cada 15 segundos
mientras haya puntos pendientes y dejan de hacerlo al acreditarse. Las consultas
no repiten la compra ni ejecutan la acreditación. Consulta la
[guía de recuperación](../docs/frontend-loyalty-recovery.md).

Los formularios funcionan con navegación HTML normal. HTMX mejora las
operaciones del carrito sin convertir la aplicación en una SPA.

La interfaz mantiene menú, historial y carrito visibles en móvil, controles
táctiles de 44 px, navegación por teclado y avisos de error junto a la operación.
HTMX y su extensión oficial `response-targets` se sirven localmente;
`app/static/storefront.js` conserva el foco y muestra fechas en la zona del
navegador. Consulta la [revisión de usabilidad](../docs/visual-usability-review.md)
para las capturas y los recorridos en cinco anchos.

## Organización del código

`GET /livez` comprueba el proceso y `GET /readyz` depende únicamente de menú;
`GET /health` conserva el diagnóstico de los tres backends. Consulta el
[contrato de salud](../docs/health-contract.md) para respuestas y límites.

`app/main.py` construye la aplicación y conecta seguridad, recursos y rutas.
`app/routes/` agrupa las URLs por menú, carrito, pedidos y operación;
`app/services/` contiene las reglas del carrito y la coordinación con los
backends. `app/presentation.py` concentra Jinja y las respuestas HTML;
`app/dependencies.py` resuelve los clientes y plantillas con `Depends` de
FastAPI. Consulta la [guía de organización](../docs/code-organization.md).

El carrito prepara la clave idempotente antes de confirmar. Dos envíos con la
misma cookie reutilizan esa clave; una compra posterior obtiene otra. Las
[pruebas de concurrencia](../docs/concurrency-and-idempotency.md) verifican que
un doble envío no cree dos pedidos.

## Desarrollo

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Por defecto espera los backends en los puertos `8001`, `8002` y `8003` de
`localhost`. Para levantar el sistema completo usa el `compose.yaml` de la
raíz y abre <http://localhost:8000>.

## Validación

```powershell
.\.venv\Scripts\python.exe -m pytest -c pyproject.toml tests ../tests/observability -p no:cacheprovider
.\.venv\Scripts\python.exe -m ruff check app tests ../tests/observability
.\.venv\Scripts\python.exe -m ruff format --check app tests ../tests/observability
```

`pyproject.toml` configura pytest y hereda las reglas comunes de `../ruff.toml`:
Python 3.13, líneas de 100 caracteres y el mismo conjunto de reglas de los
backends. Las versiones de pytest y Ruff siguen fijadas en los locks.
En Linux se puede crear el entorno con `python3.13 -m venv .venv`.
Consulta la [guía de herramientas](../docs/development-tooling.md).

Los formularios requieren un token generado y validado por
`fastapi-csrf-protect==1.0.7`, con una cookie CSRF firmada y ligada a la sesión.
Abrir primero `/`
permite obtenerlo; no se deben enviar POST sin cookie ni token. HTMX se sirve
localmente y la CSP bloquea scripts externos/inline.

Producción requiere `APP_ENV=production`, origen HTTPS, hosts explícitos y un
secreto de sesión aleatorio compartido por las réplicas. Las cookies son
`Secure` y `HttpOnly`. Consulta la [guía de seguridad web](../docs/web-security.md)
y la plantilla `compose.public.yaml` antes de publicar.
