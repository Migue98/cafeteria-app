# ADR-001 — Stack inicial de la cafetería

- **Estado:** aceptado para planeación.
- **Fecha:** 11 de noviembre de 2026.

## Contexto

El proyecto se evalúa principalmente por Kubernetes, automatización y observabilidad. La aplicación debe ser suficientemente completa para generar tráfico, datos, métricas, fallos y trazas, pero no debe consumir el tiempo destinado a la plataforma.

## Decisión

- FastAPI en los cuatro servicios.
- Jinja y HTMX para el frontend.
- PostgreSQL como única instancia, con propiedad lógica de tablas por servicio durante el MVP.
- REST síncrono entre servicios.
- Kustomize para manifiestos de aplicación.
- Buildah en Tekton y Docker Hub como registry.
- Argo CD con sync automático, prune y selfHeal.
- kube-prometheus-stack, Grafana Alloy, Loki y Tempo.
- Calico, MetalLB, ingress-nginx y NFS CSI en el clúster.

## Consecuencias positivas

- Un solo lenguaje y conjunto de herramientas.
- Instrumentación homogénea con OpenTelemetry.
- Menos complejidad de frontend y mayor tiempo para la infraestructura.
- La arquitectura coincide directamente con la rúbrica.

## Riesgos

- Una única instancia de PostgreSQL sigue siendo un punto único de falla.
- REST síncrono acopla la creación de pedidos con servicios dependientes.
- El stack de observabilidad y CI/CD requiere bastante memoria.
- Docker Hub y GitHub introducen dependencias externas durante la demo.

## Mitigaciones

- Persistencia NFS, probes y procedimiento de recuperación documentado.
- El pedido se conserva aunque falle la asignación de puntos.
- Recursos y réplicas ajustados después de medir el mini PC.
- Video de respaldo y evidencias capturadas antes de la presentación.
