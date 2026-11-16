# Plan de implementación

## Fase 0 — Confirmaciones

- Confirmar Proyecto 1 con el equipo o profesor.
- Inventariar recursos del mini PC.
- Definir cuentas de GitHub, Docker Hub y grupo de Telegram.
- Reservar nombres, direcciones y dominio `nip.io`.

## Fase 1 — Plataforma base

- Crear y preparar VMs.
- Instalar el clúster de tres nodos.
- Instalar CNI, MetalLB, Ingress y NFS CSI.
- Validar nodos `Ready`, red entre pods y PVC dinámico.

## Fase 2 — MVP de aplicación

- Implementar contratos `/health` y `/metrics`.
- Implementar menú, pedidos, lealtad y frontend.
- Crear esquema y carga de 20 productos.
- Ejecutar pruebas locales y construir imágenes.

## Fase 3 — Kubernetes y datos

- Crear manifiestos base y overlays.
- Configurar StatefulSet y PVC de PostgreSQL.
- Configurar probes, réplicas y recursos.
- Probar persistencia al eliminar el pod de la base de datos.

## Fase 4 — CI/CD

- Publicar los dos repositorios definitivos.
- Crear Tasks, Pipeline, TriggerTemplate y EventListener.
- Publicar imágenes `SHA` en Docker Hub.
- Configurar Argo CD con sync automático, prune y selfHeal.

## Fase 5 — Observabilidad

- Instalar kube-prometheus-stack, Alloy, Loki y Tempo.
- Crear ServiceMonitors, dashboards, reglas y Telegram.
- Correlacionar un error con logs y trazas.

## Fase 6 — Evidencias y presentación

- Ejecutar las tres demostraciones obligatorias.
- Capturar PipelineRun, Argo CD, targets y alertas.
- Exportar dashboards y presentación.
- Grabar video de respaldo de máximo cinco minutos.
- Ensayar el pitch y las preguntas técnicas.

Los puntos extra —app-of-apps, HPA, Sealed Secrets y staging/production— se abordan solo después de completar el núcleo de 100 puntos.
