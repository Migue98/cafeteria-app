# Plan de trabajo — Cafetería en línea

Actualizado el **27 de noviembre de 2026**, después de las clases 2, 3 y 4.
Objetivo de entrega: **4 de diciembre de 2026**. Este plan fija el orden vigente;
[software-roadmap.md](software-roadmap.md) conserva el avance del desarrollo.
Es una actualización de planeación: los recursos Kubernetes y Tekton siguen por implementar.

## Punto de partida y responsabilidades

La aplicación y la plataforma Compose están implementadas y publicadas hasta
`1eec563`: cuatro componentes, PostgreSQL, seguridad, reintentos de puntos,
OpenTelemetry, pruebas HTTP/Chromium y observabilidad local. Los seis workflows
de Actions aprobaron ese commit. Esto es evidencia del desarrollo previo;
el CI/CD evaluable debe funcionar con **Tekton y Argo CD**.

El equipo asignará responsables para tres frentes: Desarrollo/CI, Plataforma/CD
y SRE/Observabilidad. El compañero de infraestructura confirma su plataforma;
no se asume que falten VMs ni se cambia su topología desde este plan. Cada
integrante debe poder explicar el recorrido completo.

## Cómo incorporamos las clases

| Material docente | Aplicación al proyecto | Adaptación necesaria |
|---|---|---|
| Clase 2: NFS, PV/PVC, StorageClass, StatefulSet y DaemonSet | Datos de PostgreSQL y almacenamiento de observabilidad y workspaces de Tekton. | Usar el NFS y las rutas reales acordadas; conservar los datos al recrear pods. |
| Clase 3: Prometheus/Grafana, node-exporter, kube-state-metrics, Loki y Tempo | Dashboards de infraestructura, aplicación y negocio; persistencia y correlación. | La consigna exige kube-prometheus-stack, ServiceMonitor y PrometheusRule. Para Cafetería, el recolector es Alloy; los ejemplos de Promtail son referencia de clase. |
| Clase 4: Task, Pipeline, PipelineRun, workspace NFS, resultado IMAGE_DIGEST y Application | Tekton valida, construye y publica cuatro imágenes; Argo CD sincroniza el repo GitOps. | La demo del profesor construye una página desde un repo. Nuestra entrega usa dos repos, cuatro Containerfiles y actualización automática de las cuatro imágenes. |

La consigna final prevalece cuando la demo simplifica un requisito: pruebas,
webhook, tags SHA, persistencia, seis alertas y despliegue por Git son parte de
la entrega. Los archivos docentes se preservan como fuentes, separados del código activo.

## Orden de ejecución y criterios de salida

| Paso | Trabajo | Responsable por frente | Evidencia para darlo por terminado |
|---|---|---|---|
| 1 | Acordar el contrato con infraestructura. | Plataforma/CD + CI + SRE | Versiones/arquitecturas, tres nodos Ready, CNI, Ingress, NFS/StorageClass y capacidad documentados; builder y ejecución E2E decididos. |
| 2 | Crear un PipelineRun manual de validación en Tekton. | Desarrollo/CI | Checkout del SHA exacto, contratos, Ruff y pytest de los cuatro componentes aprobados; workspace PVC propio y credenciales fuera de Git. |
| 3 | Completar las pruebas y construcción en Tekton. | Desarrollo/CI + Plataforma/CD | API y Chromium ejecutados por Tekton en un entorno de ensayo aislado; fallas/recuperación verificadas; cuatro builds y resultados URL/digest. Un fallo impide publicar la entrega. |
| 4 | Preparar las bases y el overlay mínimo de GitOps. | Plataforma/CD + Desarrollo | Kustomize renderiza cuatro Deployments/Services, ConfigMaps, referencias a Secrets, Ingress y PostgreSQL StatefulSet; probes y recursos definidos. |
| 5 | Conectar publicación, actualización GitOps y Argo CD. | Desarrollo/CI + Plataforma/CD | Cuatro imágenes SHA en Docker Hub, referencias fijadas por digest en un commit de GitOps y Applications Synced/Healthy; persistencia de un pedido al recrear PostgreSQL. |
| 6 | Automatizar el disparo por webhook. | Desarrollo/CI + Plataforma/CD | Evento firmado de main crea PipelineRun para ese SHA; un cambio visible llega a la web sin aplicar manualmente manifiestos de tienda. |
| 7 | Integrar observabilidad de Kubernetes y alertas. | SRE + Plataforma/CD | Cuatro ServiceMonitors UP, tres dashboards, seis alertas PrometheusRule y avisos firing/resolved desde Alertmanager a Telegram; log de error enlazado a su traza. |
| 8 | Ensayar y cerrar evidencias. | Los tres integrantes | Compra persistida, cambio por Git, self-heal y falla observable demostrados; README, versiones, pitch y video de respaldo listos. |

Los pasos 3 y 4 pueden avanzar en paralelo una vez confirmado el paso 1.
El diseño de observabilidad puede avanzar junto a GitOps; su aceptación necesita
la aplicación desplegada. Staging, app-of-apps, HPA y Sealed Secrets quedan
como extras después de completar el mínimo.

## 1. Contrato con infraestructura

Registrar versiones y arquitecturas del clúster y compatibilidad de Pipelines,
Triggers, Argo CD y kube-prometheus-stack antes de seleccionar imágenes o APIs.
El material incluye Tekton `v1` y `v1beta1`: no se mezclarán sin verificar qué
admite la instalación. Fijar las versiones elegidas y los digests del builder.

Confirmar namespaces `tienda`, `monitoring`, `tekton-pipelines` y `argocd`,
StorageClass y modos de acceso, NFS y sus permisos, recursos para CI, hosts de
Ingress, HTTPS, acceso administrativo y endpoint/túnel del EventListener.
La selección de Buildah o la adaptación del ejemplo Kaniko depende de esa
compatibilidad y política del clúster; no se copiarán cuentas ni tags de la demo.
Los cambios de infraestructura se coordinarán y aprobarán con su responsable.

## 2–3. CI dentro de Tekton

Primero clonar y validar manualmente; después ampliar a integración y builds.
Los comandos de pytest, Ruff y contratos ya existen y se reutilizan. Las 31
pruebas HTTP y 12 de Chromium son la referencia funcional actual.

El runner actual controla Docker Compose. Instalar solamente la CLI en una Task
no basta. Antes de cerrar el paso 1 se elegirá y documentará una de estas rutas:

- Adaptar las fixtures a Kubernetes en un namespace de ensayo aislado, con
  PostgreSQL/PVC propios y mecanismos de falla/recuperación controlados.
- Conservar Compose en un motor aislado para CI, si infraestructura permite
  ese entorno y sus permisos. No montar el socket del host por defecto.

En ambas rutas **Tekton ejecuta y recoge las pruebas**; Actions queda como
apoyo al desarrollo y no es una dependencia para aprobar o desplegar. Preparar
los artefactos candidatos de ensayo sin promoverlos a la entrega; el mecanismo
para cargarlos en ese entorno se acuerda con la ruta elegida. Las pruebas de
seguridad, idempotencia y recuperación conservan sus criterios aunque cambie
la forma de provocar las fallas. El entorno se limpia en `finally`, con
conservación acotada de diagnósticos al fallar y sin tocar datos de `tienda`.

Los cuatro builds usan sus contextos y `Containerfile`, con tag igual al SHA
completo y resultado digest. La publicación de entrega y la actualización GitOps
solo continúan al aprobar las validaciones; una construcción parcial no promueve
una combinación incompleta. Ver [plan de Tekton](tekton-ci-cd.md).

## 4–6. CD, datos y automatización

Antes de fijar las probes de los manifiestos, seguir el
[contrato de salud](health-contract.md), definido como paso 1 de preparación
del software. El paso 2 implementará `/livez` y `/readyz`; el diagnóstico
`/health` conserva su contrato actual. La definición ya está documentada y
las nuevas rutas aún no están implementadas.

En `cafeteria-gitops`: `base/`, `overlays/production/`, `apps/` y `monitoring/`.
Frontend y pedidos tendrán al menos dos réplicas; todos los contenedores,
requests/limits. Verificar la semántica de `/health` antes de elegir las probes:
una dependencia caída no debe producir reinicios en cascada por liveness.

PostgreSQL usa StatefulSet y `volumeClaimTemplates`; inicialización idempotente
con los tres SQL y mínimo 20 productos, más una estrategia explícita para cambios
de esquema en bases existentes. El workspace de CI y los datos de tienda usan
volúmenes diferentes. No versionar datos de usuarios ni Secrets reales.

Tekton actualiza juntas las cuatro imágenes del overlay, con SHA y digest,
valida Kustomize y hace push sin force; protege contra promover ejecuciones
antiguas que terminen después de una más nueva. Argo CD aplica los recursos de
la tienda con sync automático, prune y selfHeal. Definir el bootstrap de
plataforma por separado; los permisos de pruebas se limitan al entorno de CI.
La cuenta del pipeline no necesita aplicar recursos en `tienda`.

Comenzar con PipelineRun manual; luego agregar GitHub EventListener,
TriggerBinding, TriggerTemplate, validación de firma y filtro de repo/main.
Documentar el endpoint HTTPS/túnel y la prueba del disparo. Confirmar HTTPS,
cookies, hosts permitidos y límites de tráfico sobre el despliegue real.

## 7. Observabilidad exigida

Los manifiestos planos de la clase sirven para entender los componentes.
La entrega utilizará kube-prometheus-stack con versiones fijadas, un
ServiceMonitor por microservicio y almacenamiento persistente para Prometheus,
Grafana, Loki y Tempo. Alloy recogerá logs JSON y recibirá/exportará OTLP.

Las reglas serán PrometheusRule y los avisos saldrán de **Alertmanager** con
`send_resolved: true`, token en Secret y mensaje con alerta, severidad, namespace
y servicio. El Grafana Alerting del Compose conserva su propósito local;
sus reglas y su contacto de Telegram no equivalen a esta configuración.

| Alerta mínima | Criterio de la entrega |
|---|---|
| Servicio caído | `up == 0`. |
| Pod inestable | Reinicios repetidos; umbral documentado en el clúster. |
| Nodo no disponible | Nodo NotReady. |
| Disco casi lleno | Nodo o servidor NFS por encima del 80 %. Asegurar métricas del NFS. |
| Errores HTTP | Más del 5 % de 5xx durante cinco minutos, con denominador y ausencia de tráfico tratados. |
| Negocio | Cero pedidos durante diez minutos en horario de servicio; definir horario y zona con el equipo. |

Puntos pendientes puede conservarse como alerta adicional. Exportar dashboards
JSON de infraestructura, aplicación y negocio, y demostrar compra con datos
reales, salto log→traza y comparación del stack con otro equipo.

## 8. Evidencias y siguiente acción

Guardar SHA de código y GitOps, PipelineRun/TaskRuns, URLs/digests de imágenes,
Synced/Healthy, prueba de self-heal (cambiar réplicas o borrar Deployment),
pedido conservado tras recrear PostgreSQL, targets y notificaciones resueltas.
Las capturas y logs se revisan para excluir tokens. Ensayar 20 minutos de pitch
y cinco de preguntas, con video de respaldo de hasta cinco minutos.

**Siguiente acción:** documentar con el compañero el contrato del paso 1 y
preparar el PipelineRun manual del paso 2. La fecha objetivo del 4 de diciembre
marca la prioridad; los pasos aún no tienen duración garantizada porque falta
confirmar disponibilidad y estado del clúster.

Fuentes docentes: [consigna final](https://gitlab.com/mabs98/tsic2-2027-1/-/blob/main/material/05-proyecto-final/proyecto-final-devops-2026.html),
[clase 2](https://drive.google.com/file/d/1kFlgE3ebghtuap-jbmO6GfdIvt7KwoQQ/view),
[monitoreo final](https://drive.google.com/file/d/1HzsfaGt2j-wogAlnFOk2B93ZxJgGXDQ4/view),
[GitOps](https://drive.google.com/file/d/1dBwjaGbRgWMkLOwxcjgYCCO9rji12vXD/view),
[demo](https://drive.google.com/file/d/1lDLBHwZuA5G_Fuvc5JaLHQ2AWL0BnJBV/view).
