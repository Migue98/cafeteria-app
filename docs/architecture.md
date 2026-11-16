# Arquitectura propuesta

```mermaid
flowchart TB
    DEV[Desarrollador] -->|git push| APP[GitHub: cafeteria-app]
    APP -->|webhook| TEKTON[Tekton Triggers y Pipelines]
    TEKTON -->|test y build| HUB[Docker Hub: tag SHA]
    TEKTON -->|actualiza tag| GITOPS[GitHub: cafeteria-gitops]
    GITOPS --> ARGO[Argo CD]
    ARGO -->|sync, prune, selfHeal| K8S

    subgraph K8S[Clúster Kubernetes]
      INGRESS[Ingress]
      FRONT[frontend]
      MENU[svc-menu]
      ORDERS[svc-pedidos]
      LOYALTY[svc-lealtad]
      PG[(PostgreSQL + PVC NFS)]
      INGRESS --> FRONT
      FRONT --> MENU
      FRONT --> ORDERS
      ORDERS --> MENU
      ORDERS --> LOYALTY
      MENU --> PG
      ORDERS --> PG
      LOYALTY --> PG
    end

    subgraph OBS[Namespace monitoring]
      PROM[Prometheus]
      GRAF[Grafana]
      ALERT[Alertmanager]
      ALLOY[Grafana Alloy]
      LOKI[Loki]
      TEMPO[Tempo]
      PROM --> GRAF
      PROM --> ALERT
      ALLOY --> LOKI
      ALLOY --> TEMPO
    end

    K8S -->|/metrics| PROM
    K8S -->|logs JSON y OTLP| ALLOY
    ALERT --> TELEGRAM[Telegram]
```

## Principios

- La ruta de producción es Git: Tekton construye y modifica GitOps; Argo CD despliega.
- Las imágenes son inmutables por SHA y no se utiliza `latest`.
- Los servicios no dependen de direcciones IP fijas; usan DNS de Kubernetes.
- Los datos persistentes viven en PVC, no dentro de la capa escribible del contenedor.
- Métricas, logs y trazas comparten `service`, `namespace` y `trace_id` para permitir correlación.
- Los componentes administrativos no se exponen directamente a Internet.

## Comunicación de la aplicación

La primera versión utilizará REST síncrono. `svc-pedidos` consulta el menú, persiste el pedido y solicita la asignación de puntos. Si la asignación de puntos falla, el pedido debe conservarse y registrar el error para permitir recuperación; no se implementará una transacción distribuida en el MVP.
