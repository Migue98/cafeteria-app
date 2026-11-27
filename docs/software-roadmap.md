# Plan del software

La infraestructura se coordina por separado con el compañero responsable. Este
orden recoge los bloques de desarrollo acordados para cerrar la aplicación
antes de integrarla al despliegue público.

| Orden | Bloque | Estado |
|---|---|---|
| 1 | Contratos, servicios, base de datos, Compose y frontend | Implementado e integrado. |
| 2 | Dependencias, imágenes y herramientas reproducibles | Integrado en `44e36d3`. |
| 3 | Reintento automático de puntos pendientes | Integrado en `ca6c0c7`. |
| 4 | Logs comunes y correlación entre servicios | Integrado en `9b9d7e7`. |
| 5 | Historial degradado y actualización de puntos en la interfaz | Integrado en `40d9bf6`. |
| 6 | Concurrencia e idempotencia; suite E2E en CI | Integrado en `53b8814`; cinco workflows de GitHub aprobados. |
| 7 | Fallas, timeouts y recuperación de dependencias | Implementado, validado localmente e integrado en `main`. |
| 8 | Seguridad del software para publicación | Implementado, validado e integrado en `204329a`; el despliegue público sigue pendiente. |
| 9 | Organización de carpetas y documentación | Integrado en `ff37cd4`; los esqueletos antiguos de la materia se retiraron en `1361737`. |
| 10 | Separación de rutas y lógica de negocio de `main.py` | Integrado en `ef9c9d3`, con pruebas locales y E2E aprobadas. |
| 11 | Validación final del software web y observabilidad local | Implementado, validado y documentado; falta reproducción en los otros equipos. El estado remoto se comprueba en Actions para el commit compartido. |
| 12 | Integración con infraestructura, Kubernetes y GitOps | Se retomará al terminar el desarrollo de la web. |

## Cierre del software por pasos

| Paso | Trabajo | Estado |
|---|---|---|
| 1 | Herramientas comunes: Python 3.13, pyproject por componente, Ruff y pytest | Implementado y validado localmente en los cuatro componentes; pendiente de revisión. |
| 2 | Pruebas automatizadas en un navegador real, con JavaScript y HTMX | Implementado y validado localmente: 31 casos HTTP y 12 de Chromium tras la revisión visual; CI configurado, pendiente de revisión. |
| 3 | Revisión visual y de usabilidad en escritorio y móvil | Implementado y validado localmente en cinco anchos, con teclado, carga, errores y recuperación; pendiente de revisión. |
| 4 | Documentación de entrega y reproducción para el equipo | Guía preparada y comprobada contra los comandos y la configuración local; falta revisión del equipo y reproducción en sus máquinas. |

La [revisión de usabilidad](visual-usability-review.md) recoge los hallazgos,
correcciones y resultados del paso 3. La [guía de entrega](team-handoff.md)
cierra el paso 4 con los requisitos, comandos, diagnóstico y evidencia. Para
compartir la versión, se publica el conjunto en `main` y se exige comprobar los
workflows del mismo SHA. Sigue reproducirlo en las otras máquinas; después se
retoman infraestructura y CI/CD.

## Revisión y publicación del cierre

El 27 de noviembre de 2026 se revisó el conjunto acumulado de herramientas,
OpenTelemetry, plataforma local, Chromium, usabilidad y documentación. Las
pruebas por componente se ejecutaron de nuevo antes de publicar:

| Componente, incluido el contrato común de observabilidad | Resultado |
|---|---:|
| Frontend | 93 aprobadas. |
| Menú | 32 aprobadas. |
| Pedidos | 54 aprobadas. |
| Lealtad | 35 aprobadas. |

Ruff, formato y `pip check` aprobaron los cuatro entornos y el entorno de pruebas
integrales. La revisión de los archivos publicables no detectó secretos y
confirmó que `.env`, entornos Python y evidencias locales quedan fuera de Git.
Los 31 casos HTTP y 12 de Chromium ya se habían ejecutado sobre este software
en la [revisión visual](visual-usability-review.md); el CI vuelve a construir y
probar la versión publicada en Ubuntu.

La [página de Actions](https://github.com/Migue98/cafeteria-app/actions) permite
comprobar los cuatro workflows de componentes, **Integrated E2E** y
**Local monitoring** (métricas y plataforma completa). Deben corresponder al SHA
compartido y terminar con `success`; una ejecución de otro commit no valida
esta entrega. Los resultados locales anteriores permanecen como evidencia de
sus respectivos pasos.

## Observabilidad local antes de la revisión visual

Este bloque se incorpora antes de retomar el paso 3 de cierre de la web.
Completar logs y métricas no equivale a tener la plataforma de observabilidad.

| Paso | Trabajo | Estado |
|---|---|---|
| 1 | SDK OpenTelemetry, instrumentación FastAPI/HTTPX/Psycopg y exportación OTLP | Implementado y validado localmente: 211 pruebas de componentes y 35 integrales; pendiente de revisión. |
| 2 | Prometheus y Grafana en Compose opcional, con datos persistentes | Implementado y validado localmente: cuatro pruebas de métricas, compra, persistencia y Chromium; pendiente de revisión. |
| 3 | Alloy, Loki y Tempo; navegación entre logs y trazas en Grafana | Implementado y validado localmente: nueve pruebas de métricas, logs, trazas, persistencia y Chromium; pendiente de revisión. |
| 4 | Dashboards de aplicación y negocio, alertas locales y Telegram | Implementado y validado localmente: quince pruebas del modo completo, seis del básico y envío real de Telegram aprobado desde Grafana; pendiente de revisión. |

La [guía de OpenTelemetry](opentelemetry-tracing.md) describe lo que ya se puede
exportar y la evidencia del paso 1. La [guía de monitoreo local](local-monitoring.md)
documenta Prometheus y Grafana y la evidencia del paso 2. La
[guía de logs y trazas](local-logs-traces.md) describe la recolección con Alloy,
Loki y Tempo y la navegación en Grafana del paso 3. La
[guía de dashboards y alertas](local-dashboards-alerts.md) documenta el paso 4,
sus condiciones de evaluación y el envío opcional a Telegram.
Los dashboards de infraestructura y alertas
de nodos, pods y disco se cerrarán con Kubernetes. Después de la observabilidad
local y del cierre documentado de la web, siguen la revisión del equipo,
el despliegue y CI/CD.

El bloque 8 contempla protección CSRF de formularios, servir HTMX localmente,
cabeceras de seguridad y configuración de sesión/cookies para producción.
La publicación requerirá coordinar HTTPS y los secretos con infraestructura.
No se añaden pagos reales ni registro público de cuentas al alcance escolar.

Las guías de cada bloque y sus evidencias están en el [índice](README.md). La
topología de Kubernetes, las direcciones, el almacenamiento y la exposición del
mini PC se definirán con el responsable de infraestructura cuando corresponda.
