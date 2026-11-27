# Observabilidad local

Configuración utilizada por [`compose.monitoring.yaml`](../compose.monitoring.yaml)
y la extensión [`compose.telemetry.yaml`](../compose.telemetry.yaml).

```text
observability/
├── prometheus/prometheus.yml             # Scrape de los cuatro servicios
├── alloy/config.alloy                    # Docker stdout → Loki y OTLP → Tempo
├── loki/local.yaml                       # Logs, índice y WAL en disco
├── tempo/local.yaml                      # Trazas locales y WAL
└── grafana/
    ├── provisioning/datasources/          # Prometheus por UID estable
    ├── provisioning/dashboards/           # Carga automática desde archivos
    ├── telemetry-datasources.yaml         # Loki/Tempo y enlaces log ↔ traza
    ├── alerting/                          # Reglas y políticas local/Telegram
    └── dashboards/                        # Conexión, aplicación y negocio
```

La [guía de Prometheus y Grafana](../docs/local-monitoring.md) explica inicio,
credenciales locales, consultas, persistencia, pruebas y limpieza.
La [guía de logs y trazas](../docs/local-logs-traces.md) añade Alloy, Loki y Tempo,
las consultas en Explore y las pruebas de correlación, persistencia y navegador.
La [guía de dashboards y alertas](../docs/local-dashboards-alerts.md) describe
los paneles, los umbrales y la extensión opcional `compose.telegram.yaml`.
Esta carpeta contiene configuración de Compose; los manifiestos Kubernetes
se incorporarán en `cafeteria-gitops` al integrar la infraestructura.
