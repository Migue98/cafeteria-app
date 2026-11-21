# Documentación de la aplicación

| Documento | Contenido |
|---|---|
| [Arquitectura](architecture.md) | Componentes, flujo CI/CD y principios técnicos. |
| [Especificación](application-specification.md) | Funciones, microservicios, persistencia y alcance. |
| [Plan de implementación](implementation-plan.md) | Fases y orden de trabajo. |
| [Inventario de dependencias](dependency-inventory.md) | Versiones declaradas e instaladas antes del bloqueo reproducible. |
| [Validación de locks](dependency-lock-validation.md) | Evidencia de instalaciones limpias, pruebas y builds reproducibles. |
| [Validación de entradas inmutables](immutable-input-validation.md) | Evidencia de imágenes, runtime y referencias externas fijadas. |
| [Integración local](local-integration.md) | Compose raíz y prueba completa de los backends. |
| [Pruebas E2E](../tests/README.md) | Ejecución aislada, alcance y opciones de la suite integral. |
| [Contratos OpenAPI](openapi/README.md) | APIs, convenciones y ejemplos ejecutables. |
| [ADR-001](decisions/ADR-001-stack.md) | Elección del stack. |
| [ADR-002](decisions/ADR-002-api-contracts.md) | Decisiones de contratos HTTP. |
| [ADR-003](decisions/ADR-003-reproducible-dependencies.md) | Estrategia de versiones directas y locks reproducibles. |
| [ADR-004](decisions/ADR-004-immutable-build-inputs.md) | Imágenes, herramientas y Actions fijadas por digest o SHA. |

La infraestructura desplegable y la observabilidad se documentan en
[`cafeteria-gitops`](https://github.com/Migue98/cafeteria-gitops).
