# Documentación de la aplicación

| Documento | Contenido |
|---|---|
| [Entrega y reproducción para el equipo](team-handoff.md) | Punto de entrada: requisitos, arranque, modos de observabilidad, pruebas, desarrollo y solución de problemas. |
| [Arquitectura](architecture.md) | Componentes, flujo CI/CD y principios técnicos. |
| [Organización del código](code-organization.md) | Configuración, rutas, servicios, dependencias, errores y persistencia del frontend y pedidos. |
| [Herramientas de desarrollo](development-tooling.md) | Python 3.13, pytest y Ruff comunes, entornos locales y comandos de CI. |
| [Pruebas con navegador real](browser-testing.md) | Chromium, clics y temporizadores de HTMX, entorno aislado y trazas de fallos. |
| [Revisión visual y de usabilidad](visual-usability-review.md) | Escritorio y móvil, navegación, teclado, carga, errores y evidencia de las correcciones. |
| [Plan de CI/CD con Tekton](tekton-ci-cd.md) | Pipeline por etapas, pruebas, publicación, webhook y contrato con GitOps. |
| [Especificación](application-specification.md) | Funciones, microservicios, persistencia y alcance. |
| [Plan de implementación](implementation-plan.md) | Fases y orden de trabajo. |
| [Plan del software](software-roadmap.md) | Bloques completados y orden pendiente antes de integrar infraestructura. |
| [Inventario de dependencias](dependency-inventory.md) | Versiones declaradas e instaladas antes del bloqueo reproducible. |
| [Validación de locks](dependency-lock-validation.md) | Evidencia de instalaciones limpias, pruebas y builds reproducibles. |
| [Validación de entradas inmutables](immutable-input-validation.md) | Evidencia de imágenes, runtime y referencias externas fijadas. |
| [Integración local](local-integration.md) | Compose del frontend y backends, SQL por servicio y comprobación rápida. |
| [Reintento automático de lealtad](automatic-loyalty-retry.md) | Recuperación, idempotencia, configuración y métricas. |
| [Logs y correlación](application-observability.md) | Formato JSON común, propagación de contexto y guía para seguir una petición. |
| [Instrumentación OpenTelemetry](opentelemetry-tracing.md) | Spans de FastAPI, HTTPX y PostgreSQL, exportación OTLP y pruebas de correlación. |
| [Prometheus y Grafana locales](local-monitoring.md) | Compose opcional, métricas reales, provisioning, datos persistentes y pruebas. |
| [Logs y trazas en Grafana local](local-logs-traces.md) | Alloy, Loki y Tempo, consultas, navegación log ↔ traza y pruebas de persistencia. |
| [Dashboards y alertas locales](local-dashboards-alerts.md) | Aplicación y negocio, reglas de Grafana, Telegram opcional y pruebas de alerta/recuperación. |
| [Recuperación de puntos en la interfaz](frontend-loyalty-recovery.md) | Historial disponible durante fallas y actualización de puntos pendientes. |
| [Concurrencia e idempotencia](concurrency-and-idempotency.md) | Compras simultáneas, claves alternas, garantías transaccionales y migración. |
| [Fallas y recuperación](failure-recovery.md) | Caídas, timeouts, respuestas inválidas y recuperación sin duplicados. |
| [Seguridad web](web-security.md) | CSRF, CSP, sesiones, hosts, HTMX local y requisitos de publicación. |
| [Pruebas compartidas e integrales](../tests/README.md) | Organización de smoke, E2E y observabilidad; ejecución aislada y alcance. |
| [Contratos OpenAPI](openapi/README.md) | APIs, convenciones y ejemplos ejecutables. |
| [ADR-001](decisions/ADR-001-stack.md) | Elección del stack. |
| [ADR-002](decisions/ADR-002-api-contracts.md) | Decisiones de contratos HTTP. |
| [ADR-003](decisions/ADR-003-reproducible-dependencies.md) | Estrategia de versiones directas y locks reproducibles. |
| [ADR-004](decisions/ADR-004-immutable-build-inputs.md) | Imágenes, herramientas y Actions fijadas por digest o SHA. |

La plataforma local se configura en este repositorio. La infraestructura
desplegable de Kubernetes se documenta en
[`cafeteria-gitops`](https://github.com/Migue98/cafeteria-gitops).
