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

Los formularios funcionan con navegación HTML normal. HTMX mejora las
operaciones del carrito sin convertir la aplicación en una SPA.

## Desarrollo

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Por defecto espera los backends en los puertos `8001`, `8002` y `8003` de
`localhost`. Para levantar el sistema completo usa el `compose.yaml` de la
raíz y abre <http://localhost:8000>.

## Validación

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\ruff.exe format --check app tests
```

`SESSION_SECRET` debe suministrarse mediante un Secret fuera del entorno local.
