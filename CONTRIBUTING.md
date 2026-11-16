# Guía de contribución

## Antes de trabajar

- Revisa los Issues abiertos y evita duplicar trabajo.
- Si el cambio no tiene Issue, crea uno con objetivo, alcance y criterio de aceptación.
- No coloques credenciales ni datos privados en Issues, commits o Pull Requests.

## Ramas

Parte siempre de `main` actualizado y usa nombres descriptivos:

```text
feat/menu-health-endpoint
fix/order-total-validation
docs/update-api-example
ops/tekton-build-task
```

Evita ramas personales permanentes y Pull Requests con cambios no relacionados.

## Commits

Usa mensajes breves en imperativo. Se recomienda Conventional Commits:

```text
feat(menu): add product listing endpoint
fix(orders): reject unavailable products
docs(api): document idempotency behavior
test(loyalty): cover duplicate point requests
```

## Contratos y compatibilidad

OpenAPI es la fuente de verdad. Si un cambio modifica rutas, cuerpos, estados o errores:

1. Actualiza primero el archivo en `docs/openapi/`.
2. Añade o actualiza ejemplos y pruebas.
3. Ejecuta `python scripts/validate_contracts.py`.
4. Explica la compatibilidad del cambio en el Pull Request.

Los cambios incompatibles requieren una nueva versión de la API.

## Pull Requests

- Mantén un alcance pequeño y enlaza el Issue correspondiente.
- Describe qué cambió, cómo se validó y cualquier riesgo conocido.
- Solicita al menos una revisión de otro integrante.
- Resuelve conversaciones y comprobaciones antes de integrar.
- Usa squash merge cuando los commits intermedios no aporten historia útil.

## Criterios técnicos

- Python tipado, formato consistente y pruebas con `pytest`.
- `/health`, `/metrics`, logs JSON y trazas desde la primera versión de cada servicio.
- Imágenes ejecutadas como usuario no root y etiquetadas por SHA, nunca `latest` en producción.
- Ninguna contraseña, token, llave, kubeconfig o `.env` real en Git.

## Comunicación entre repositorios

Los cambios de aplicación se hacen aquí. Los cambios del estado deseado de
Kubernetes se hacen en
[`cafeteria-gitops`](https://github.com/Migue98/cafeteria-gitops). Un Pull
Request no debe mezclar ambas responsabilidades.
