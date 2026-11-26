# Cafetería en línea — aplicación

Aplicación de referencia para el proyecto final de DevOps. El sistema permite
consultar un menú, armar un carrito, confirmar pedidos y acumular puntos de
lealtad. La prioridad del proyecto es demostrar un ciclo completo de desarrollo,
construcción, despliegue GitOps y observabilidad sobre Kubernetes.

> **Estado actual:** el frontend y los tres backends (`svc-menu`, `svc-pedidos`
> y `svc-lealtad`) cuentan con MVP ejecutable, pruebas y entorno
> contenedorizado con PostgreSQL.

## Repositorios

| Repositorio | Responsabilidad |
|---|---|
| [`cafeteria-app`](https://github.com/Migue98/cafeteria-app) | Código fuente, pruebas, Containerfiles y contratos OpenAPI. La carpeta de Tekton conserva la propuesta pendiente. |
| [`cafeteria-gitops`](https://github.com/Migue98/cafeteria-gitops) | Diseño del estado deseado de Kubernetes, overlays, Argo CD y observabilidad; se retomará al terminar la web. |

Tekton construirá imágenes inmutables identificadas por SHA y actualizará el
repositorio GitOps. Argo CD será el único componente autorizado para aplicar el
estado deseado al clúster.

## Equipo

| Integrante | GitHub |
|---|---|
| Miguel Alberto Bazán Silva | [`@Migue98`](https://github.com/Migue98) |
| González Nava Alicia Aislinn | [`@aliceaislinn`](https://github.com/aliceaislinn) |
| Quintero Rubio Martín | [`@mquinteror1000`](https://github.com/mquinteror1000) |

Las responsabilidades concretas se asignarán mediante Issues y Pull Requests;
la tabla no implica propiedad exclusiva sobre componentes.

## Arquitectura funcional

```mermaid
flowchart LR
    U[Usuario] --> F[frontend]
    F --> M[svc-menu]
    F --> P[svc-pedidos]
    P --> M
    P --> L[svc-lealtad]
    M --> DB[(PostgreSQL)]
    P --> DB
    L --> DB
```

| Componente | Responsabilidad |
|---|---|
| `frontend` | Menú Jinja/HTMX, carrito, confirmación del pedido, historial y puntos. |
| `svc-menu` | Productos, precios y disponibilidad. |
| `svc-pedidos` | Creación, persistencia y consulta de pedidos. |
| `svc-lealtad` | Movimientos y saldo de puntos por cliente. |
| PostgreSQL | Persistencia; no cuenta como microservicio. |

Los detalles están en la [arquitectura](docs/architecture.md) y la
[especificación funcional](docs/application-specification.md).

## Contratos HTTP

- OpenAPI 3.1 es la fuente de verdad de los tres backends.
- Las rutas de negocio usan `/api/v1`.
- Todos los servicios exponen `GET /health` y `GET /metrics`.
- El frontend protege los formularios con CSRF, sirve HTMX localmente y permite
  configurar cookies y hosts para producción. Consulta la
  [guía de seguridad web](docs/web-security.md) antes de exponer la aplicación.
- Los cuatro servicios emiten logs JSON y propagan el contexto de la petición;
  consulta la [guía de logs y correlación](docs/application-observability.md).
- Pedidos recupera automáticamente las acreditaciones pendientes cuando
  lealtad vuelve a estar disponible.
- Los importes se expresan en centavos enteros y moneda MXN.
- Los errores usan `application/problem+json`.
- La creación de pedidos y la acreditación de puntos requieren
  `Idempotency-Key`.

Los archivos fuente, convenciones y ejemplos están en
[`docs/openapi/`](docs/openapi/README.md).

## Estructura

```text
.
├── frontend/          # Interfaz web: app/routes, services, templates y static; tests/
├── svc-menu/          # Catálogo: app/, db/init.sql y tests/
├── svc-pedidos/       # Pedidos: app/routes y services, db/init.sql y tests/
├── svc-lealtad/       # Puntos: app/, db/init.sql y tests/
├── tests/
│   ├── smoke/         # Comprobación rápida del entorno local levantado
│   ├── e2e/           # Escenarios integrales con Compose aislado
│   └── observability/ # Contrato común de logs y correlación
├── scripts/           # Ejecución E2E, validación OpenAPI y generación de locks
├── .github/workflows/ # CI del frontend, backends y pruebas E2E
├── tekton/            # Documentación del pipeline previsto; sin recursos todavía
├── docs/              # Arquitectura, decisiones, OpenAPI y guías operativas
├── compose.yaml       # Frontend, tres backends y PostgreSQL para desarrollo local
└── compose.public.yaml # Ajustes para proxy HTTPS; no configura ni inicia el proxy
```

Cada backend contiene su aplicación, pruebas, dependencias, `Containerfile`,
`.dockerignore`, Compose individual y documentación operativa.

El frontend y pedidos separan `main.py` (configuración), `routes/` (HTTP) y
`services/` (operaciones). La [organización del código](docs/code-organization.md)
describe las dependencias, presentación, errores, métricas y persistencia.

Las pruebas de cada componente viven en su propio `tests/`. Las que abarcan
varios componentes viven en el `tests/` de la raíz. `scripts/` contiene los
comandos auxiliares: `run_e2e.py` prepara Compose y llama a pytest,
`validate_contracts.py` valida los contratos de `docs/openapi/` y
`compile_requirements.py` regenera los locks de dependencias.

Cada backend conserva su SQL de inicialización en `db/init.sql`. El Compose
raíz monta los tres archivos en una única instancia y base de PostgreSQL:
menú administra productos; pedidos, pedidos e ítems; lealtad, saldos,
movimientos y claves de acreditación. Consulta la
[integración local](docs/local-integration.md).

## Integración local

```bash
podman compose up --build --detach
python tests/smoke/check_compose.py
podman compose down
```

El Compose raíz levanta el frontend, PostgreSQL y los tres backends. Abre
`http://localhost:8000` para usar la aplicación. Consulta la
[guía de integración local](docs/local-integration.md) para ver puertos,
configuración, prueba completa y limpieza del volumen.

## Validación disponible

Requisito: Python 3.11 o posterior. El validador actual solo utiliza la
biblioteca estándar.

```bash
git clone https://github.com/Migue98/cafeteria-app.git
cd cafeteria-app
python scripts/validate_contracts.py
```

El comando debe finalizar con `Contratos válidos: 3`.

Para recorrer el frontend, los tres backends y PostgreSQL de extremo a extremo en un
Compose aislado:

```bash
python -m pip install -r tests/requirements.txt
python scripts/run_e2e.py
```

La suite cubre compra, precios, puntos, idempotencia, errores, métricas y
persistencia tras reiniciar PostgreSQL. Los detalles están en
[`tests/README.md`](tests/README.md).

Para validar un backend, por ejemplo menú:

```bash
cd svc-menu
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -p no:cacheprovider
ruff check app tests
ruff format --check app tests
```

## Forma de trabajo

1. Crear o elegir un Issue con alcance y criterio de aceptación.
2. Crear una rama corta desde `main`: `feat/...`, `fix/...`, `docs/...` o
   `ops/...`.
3. Actualizar primero el contrato OpenAPI si cambia una interfaz HTTP.
4. Ejecutar las validaciones relacionadas y abrir un Pull Request.
5. Solicitar al menos una revisión antes de integrar a `main`.

No se versionan tokens, contraseñas, kubeconfigs, llaves privadas ni archivos
`.env`. Consulta [CONTRIBUTING.md](CONTRIBUTING.md) antes de comenzar.

## Documentación

- [Índice de documentación](docs/README.md)
- [Plan de implementación](docs/implementation-plan.md)
- [Plan del software](docs/software-roadmap.md)
- [Integración local](docs/local-integration.md)
- [ADR-001: stack inicial](docs/decisions/ADR-001-stack.md)
- [ADR-002: contratos HTTP](docs/decisions/ADR-002-api-contracts.md)

## Siguiente hito

Revisar la separación de configuración, rutas y servicios y cerrar la
validación final de la web completa.
Kubernetes, Tekton y GitOps se retomarán al cerrar el desarrollo del software.
El orden y el estado de los bloques están en el
[plan del software](docs/software-roadmap.md).
