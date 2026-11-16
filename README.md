# Cafetería — aplicación

Código, contratos, pruebas y automatización de construcción de la cafetería en
línea del proyecto final de DevOps.

El estado deseado de Kubernetes se mantiene separado en
[`Migue98/cafeteria-gitops`](https://github.com/Migue98/cafeteria-gitops). Esta
separación permite que Tekton publique imágenes y actualice GitOps, mientras
Argo CD conserva la responsabilidad exclusiva de desplegar al clúster.

## Estructura

- [`frontend/`](frontend/README.md).
- [`svc-menu/`](svc-menu/README.md).
- [`svc-pedidos/`](svc-pedidos/README.md).
- [`svc-lealtad/`](svc-lealtad/README.md).
- [`tests/`](tests/README.md), para pruebas integrales y contratos.
- [`tekton/`](tekton/README.md), para Tasks, Pipeline y Triggers.
- [`docs/openapi/`](docs/openapi/README.md), contratos versionados de los backends.

Cada servicio tendrá `src/`, `tests/`, `requirements.txt`, `Containerfile`, `.dockerignore` y README cuando comience la implementación.

## Convenciones

- Python tipado y FastAPI.
- Pruebas con pytest.
- Formato y validación automatizados antes de construir.
- Imágenes con usuario no root y tag SHA.
- `/health`, `/metrics`, logs JSON y OpenTelemetry desde la primera versión.

Antes de implementar un endpoint se modifica y valida su contrato OpenAPI. Los cambios incompatibles requieren una nueva versión de la API.

## Validar los contratos

```bash
python scripts/validate_contracts.py
```
