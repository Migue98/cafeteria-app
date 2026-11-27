# Contratos OpenAPI

Estos archivos son la fuente de verdad de la comunicación entre frontend y backends:

- [`svc-menu.openapi.json`](svc-menu.openapi.json): catálogo y disponibilidad.
- [`svc-pedidos.openapi.json`](svc-pedidos.openapi.json): creación, consulta y recuperación de puntos de pedidos.
- [`svc-lealtad.openapi.json`](svc-lealtad.openapi.json): saldo y asignación idempotente de puntos.
- [`convenciones.md`](convenciones.md): reglas compartidas de versionado, importes, errores, trazas e idempotencia.
- [`examples/flujo-compra.http`](examples/flujo-compra.http): recorrido manual completo.

## Validación

Los contratos son JSON compatible con OpenAPI 3.1 y pueden abrirse en Swagger Editor. La validación local incluida comprueba sintaxis JSON, referencias internas y unicidad de `operationId`:

```powershell
python scripts/validate_contracts.py
```

## Regla de trabajo

El [contrato de salud para Kubernetes](../health-contract.md) fija el diseño del
paso 1 para los cuatro componentes. Los endpoints `/livez` y `/readyz` aún no
están implementados ni añadidos a estos JSON; el paso 2 actualizará primero
OpenAPI y su validador antes de implementar las rutas. `/health` sigue vigente.

1. Cambiar primero el contrato.
2. Añadir o ajustar pruebas de contrato.
3. Implementar el comportamiento.
4. Comprobar que la implementación coincide con OpenAPI.

Mientras la API esté en `/api/v1`, se permiten campos nuevos opcionales y endpoints nuevos. Renombrar o eliminar campos, alterar su tipo o cambiar semántica requiere una versión nueva.
