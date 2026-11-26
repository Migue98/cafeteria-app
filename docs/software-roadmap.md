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
| 10 | Separación de rutas y lógica de negocio de `main.py` | Implementado y validado localmente en frontend y pedidos; pendiente de revisión. |
| 11 | Validación final del software web | Después de la refactorización, conservando los flujos y las garantías existentes. |
| 12 | Integración con infraestructura, Kubernetes y GitOps | Se retomará al terminar el desarrollo de la web. |

El bloque 8 contempla protección CSRF de formularios, servir HTMX localmente,
cabeceras de seguridad y configuración de sesión/cookies para producción.
La publicación requerirá coordinar HTTPS y los secretos con infraestructura.
No se añaden pagos reales ni registro público de cuentas al alcance escolar.

Las guías de cada bloque y sus evidencias están en el [índice](README.md). La
topología de Kubernetes, las direcciones, el almacenamiento y la exposición del
mini PC se definirán con el responsable de infraestructura cuando corresponda.
