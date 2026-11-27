"""Consultas reales de logs y trazas a través de las fuentes provisionadas de Grafana."""

import base64
import json
import os
import re
import time


def identifier(value: str) -> str:
    if not value:
        return ""
    if re.fullmatch(r"[0-9a-fA-F]{16}|[0-9a-fA-F]{32}", value):
        return value.lower()
    return base64.b64decode(value).hex()


def attributes(items: list[dict]) -> dict:
    return {item["key"]: next(iter(item["value"].values())) for item in items}


class TelemetryClient:
    def __init__(self, monitoring):
        self.monitoring = monitoring
        self.loki_url = os.getenv("E2E_LOKI_URL", "http://localhost:13100")
        self.tempo_url = os.getenv("E2E_TEMPO_URL", "http://localhost:13200")
        self.alloy_url = os.getenv("E2E_ALLOY_URL", "http://localhost:12346")

    def ready(self):
        for url, path in [
            (self.loki_url, "/ready"),
            (self.tempo_url, "/ready"),
            (self.alloy_url, "/-/ready"),
        ]:
            self.monitoring.until(
                lambda url=url, path=path: self.monitoring.api.text(f"{url}{path}").status == 200,
                timeout=180,
                description=f"receptor listo: {url}",
            )

    def logs(self, trace_id: str) -> list[dict]:
        response = self.monitoring.grafana(
            "/api/datasources/proxy/uid/cafeteria-loki/loki/api/v1/query_range",
            query={
                "query": f'{{job="cafeteria"}} |= "{trace_id}"',
                "start": str(int((time.time() - 900) * 1_000_000_000)),
                "end": str(time.time_ns()),
                "limit": 1000,
            },
        )
        assert response.status == 200, response.body
        assert response.body["status"] == "success", response.body
        rows = []
        for stream in response.body["data"]["result"]:
            for value in stream["values"]:
                rows.append(
                    {
                        "labels": stream["stream"],
                        "event": json.loads(value[1]),
                        "timestamp": value[0],
                    }
                )
        return rows

    def spans(self, trace_id: str) -> list[dict]:
        response = self.monitoring.grafana(
            f"/api/datasources/proxy/uid/cafeteria-tempo/api/traces/{trace_id}"
        )
        if response.status == 404:
            return []
        assert response.status == 200, response.body
        batches = response.body.get("batches", response.body.get("resourceSpans", []))
        spans = []
        for batch in batches:
            resource = attributes(batch["resource"].get("attributes", []))
            for scope in batch.get("scopeSpans", batch.get("instrumentationLibrarySpans", [])):
                for span in scope.get("spans", []):
                    spans.append(
                        {
                            **span,
                            "id": identifier(span["spanId"]),
                            "parent": identifier(span.get("parentSpanId", "")),
                            "trace": identifier(span["traceId"]),
                            "service": resource["service.name"],
                            "attributes": attributes(span.get("attributes", [])),
                        }
                    )
        return spans
