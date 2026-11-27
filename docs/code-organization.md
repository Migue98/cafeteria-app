# Organización del código

El frontend y `svc-pedidos` separan la configuración, las rutas HTTP y los casos
de uso. `main.py` conserva `create_app(...)` y `app = create_app()`: el comando
de Uvicorn continúa siendo `uvicorn app.main:app` desde cada componente.

## Responsabilidades

| Ubicación | Responsabilidad |
|---|---|
| `app/main.py` | Construir FastAPI, configurar recursos, middleware y ciclo de vida, e incluir el router. |
| `app/routes/` | Declarar URLs, validar parámetros HTTP y devolver respuestas. Usa `APIRouter` de FastAPI. |
| `app/dependencies.py` | Resolver recursos de la instancia de la aplicación con `Depends`. |
| `app/services/` | Ejecutar reglas y operaciones con datos, clientes y repositorios, sin recibir `Request` ni devolver `Response`. |
| `app/exceptions.py` | Expresar errores de negocio; la capa HTTP decide su representación pública. |
| `app/error_handlers.py` | Registrar manejadores de errores y producir respuestas HTTP. |
| `app/metrics.py` | Registrar una sola vez las métricas HTTP y de negocio del proceso. |
| `app/clients.py` | Encapsular comunicación HTTP con los otros servicios. |
| `app/repository.py` | Encapsular persistencia SQL de pedidos; el frontend no tiene repositorio SQL. |

Los recursos configurados se guardan en `application.state`. Las dependencias
resuelven esos recursos a partir de `request.app`; no capturan la primera app
que importe un router. Cada instancia puede usar sus propios clientes, secretos
y dobles de prueba. Las clases de servicio se construyen por petición y no
conservan datos de clientes entre peticiones.

## Frontend

```text
frontend/app/
├── main.py
├── dependencies.py
├── error_handlers.py
├── exceptions.py
├── metrics.py
├── presentation.py
├── routes/
│   ├── catalog.py          # Menú
│   ├── cart.py             # Agregar, disminuir y retirar productos
│   ├── orders.py           # Checkout, historial y fragmentos de puntos
│   └── operations.py       # Salud y métricas
├── services/
│   ├── cart.py             # Sesión, identidad, cantidades y clave de compra
│   └── storefront.py       # Catálogo, compra, historial y saldo
├── clients.py
├── config.py
├── observability.py
├── security.py
├── static/
└── templates/
```

`presentation.py` configura Jinja y sus filtros, renderiza páginas y decide
entre fragmentos HTMX y redirecciones de navegación normal. Las reglas del
carrito trabajan con una sesión mutable; reciben el diccionario firmado que
proporciona Starlette, sin depender de un objeto HTTP.

`StorefrontService` coordina el gateway de los backends. Conserva el identificador
del cliente, la clave idempotente de la compra, la degradación del saldo y el
control de acceso al fragmento de puntos de cada pedido.

CSRF, sesiones, hosts permitidos y cabeceras se siguen conectando en `main.py`.
Los errores genéricos públicos y de validación de `X-Request-ID` viven en
`error_handlers.py`; los errores de catálogo y carrito se representan en las
rutas con el mismo HTML y estados que antes.

## Pedidos

```text
svc-pedidos/app/
├── main.py
├── dependencies.py
├── error_handlers.py
├── exceptions.py
├── metrics.py
├── routes/
│   ├── orders.py           # Crear, listar, consultar y reintentar puntos
│   └── operations.py       # Salud y métricas
├── services/
│   ├── orders.py           # Precios, totales, idempotencia y acreditación
│   └── health.py           # Dependencias críticas y estado degradado
├── clients.py
├── config.py
├── loyalty_retry.py
├── models.py
├── observability.py
└── repository.py
```

`OrderService` obtiene los precios del menú, guarda el pedido, intenta acreditar
puntos y conserva la recuperación del ganador cuando dos compras usan la misma
clave simultáneamente. Un replay devuelve el modelo con `replayed=true`; la
ruta decide responder HTTP 200 en lugar de 201. Los errores de negocio se
traducen a `application/problem+json` en `error_handlers.py`.

El worker automático conserva su implementación en `loyalty_retry.py`.
`main.py` continúa iniciándolo y cancelándolo mediante el ciclo de vida de
FastAPI. `repository.py`, los SQL de inicialización y las interfaces de los
clientes mantienen su organización.

## Alcance y validación

Esta reorganización se concentra en los dos `main.py` más grandes. Menú y
lealtad mantienen su estructura actual. Cada componente conserva su contexto
de construcción independiente; la refactorización usa las bibliotecas que ya
estaban fijadas, sin añadir dependencias.

Los esquemas OpenAPI generados del frontend y pedidos se compararon con una
captura anterior a la extracción y resultaron idénticos. Se conservan rutas,
parámetros, modelos, códigos de operación y configuración de seguridad.

Para validar cada componente, desde su carpeta:

```powershell
python -m pytest -c pyproject.toml tests ../tests/observability -p no:cacheprovider
ruff check app tests ../tests/observability
ruff format --check app tests ../tests/observability
```

La suite existente cubre compras, errores, idempotencia, recuperación y seguridad.
La validación con contenedores se ejecuta desde la raíz con
`python scripts/run_e2e.py`; su alcance se describe en
[`tests/README.md`](../tests/README.md).

## Evidencia — 26 de noviembre de 2026

| Comprobación | Resultado |
|---|---|
| Frontend y contrato común de observabilidad | 79 pruebas aprobadas. |
| Pedidos y contrato común de observabilidad | 40 pruebas aprobadas. |
| E2E con contenedores reales | 31 pruebas aprobadas en 151.62 segundos. |
| Ruff y formato de los componentes afectados | Correctos. |
| Contratos OpenAPI de los tres backends | Válidos. |
| Esquemas HTTP generados antes y después de la reorganización | Idénticos en frontend y pedidos. |

Los archivos de pruebas existentes permanecieron sin modificaciones.
El E2E reconstruyó las imágenes y verificó compra, concurrencia, idempotencia,
fallas, recuperación, trazas y seguridad con los servicios reales. Al terminar,
retiró los contenedores, la red y el volumen temporal de `cafeteria-e2e`.

`frontend/app/main.py` pasó de 510 a 84 líneas y
`svc-pedidos/app/main.py`, de 471 a 80. La lógica extraída vive en los módulos
descritos arriba. La validación corresponde al entorno local con Compose;
Kubernetes y GitOps continúan en una fase posterior.
