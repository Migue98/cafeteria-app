"""App → PostgreSQL → Prometheus → Grafana y persistencia al recrear contenedores."""

import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from playwright.sync_api import Page, expect

from .conftest import SERVICES, Monitoring

pytestmark = pytest.mark.monitoring


def test_prometheus_scrapes_the_four_services_and_grafana_provisions_the_source(
    monitoring: Monitoring,
):
    targets = monitoring.api.json("GET", f"{monitoring.prometheus_url}/api/v1/targets")
    assert targets.status == 200
    active = targets.body["data"]["activeTargets"]
    assert len(active) == 4
    assert {target["labels"]["service"] for target in active} == SERVICES
    assert all(target["health"] == "up" and not target["lastError"] for target in active)
    assert all(target["scrapeUrl"].endswith("/metrics") for target in active)

    requests = monitoring.query('sum by (service) (http_requests_total{job="cafeteria"})')
    assert {row["metric"]["service"] for row in requests} == SERVICES
    assert all(float(row["value"][1]) > 0 for row in requests)
    source = monitoring.grafana("/api/datasources/uid/cafeteria-prometheus")
    assert source.status == 200
    assert source.body["url"] == "http://prometheus:9090"
    assert source.body["isDefault"] is True
    assert source.body["readOnly"] is True
    assert (
        monitoring.grafana("/api/datasources/uid/cafeteria-prometheus/health").body["status"]
        == "OK"
    )
    unauthenticated = monitoring.api.json(
        "GET", f"{monitoring.grafana_url}/api/datasources/uid/cafeteria-prometheus"
    )
    assert unauthenticated.status == 401


def test_a_real_purchase_is_visible_through_the_grafana_prometheus_connection(
    monitoring: Monitoring,
):
    orders = (
        'sum(cafe_orders_total{job="cafeteria",service="svc-pedidos",'
        'status="confirmed"}) or vector(0)'
    )
    points = 'sum(cafe_loyalty_points_total{job="cafeteria",service="svc-lealtad"}) or vector(0)'
    before_orders = float(monitoring.query(orders, grafana=True)[0]["value"][1])
    before_points = float(monitoring.query(points, grafana=True)[0]["value"][1])
    customer = str(uuid4())
    created = monitoring.api.json(
        "POST",
        f"{monitoring.api.orders_url}/api/v1/orders",
        headers={"Idempotency-Key": f"monitoring-{uuid4()}"},
        payload={"customer_id": customer, "items": [{"product_id": 1, "quantity": 2}]},
    )
    assert created.status == 201
    assert created.body["loyalty_status"] == "awarded"
    assert created.body["total_cents"] == 7000
    assert created.body["points_earned"] == 7
    monitoring.until(
        lambda: (
            float(monitoring.query(orders, grafana=True)[0]["value"][1]) == before_orders + 1
            and float(monitoring.query(points, grafana=True)[0]["value"][1]) == before_points + 7
        ),
        description="pedido y puntos visibles desde Grafana",
    )
    history = monitoring.api.json(
        "GET", f"{monitoring.api.orders_url}/api/v1/orders", query={"customer_id": customer}
    )
    assert history.status == 200 and history.body["total"] == 1


def test_history_and_grafana_data_survive_recreating_both_containers(
    monitoring: Monitoring, compose_command: list[str]
):
    expression = 'up{job="cafeteria",service="frontend"}'
    timestamp = monitoring.query(f"timestamp({expression})")[0]["value"][1]
    before = monitoring.query(expression, at=timestamp)
    assert before[0]["value"][1] == "1"
    marker = f"persistent-monitoring-{uuid4()}"
    annotation = monitoring.grafana(
        "/api/annotations", method="POST", payload={"text": marker, "tags": ["monitoring-e2e"]}
    )
    assert annotation.status == 200
    annotation_id = annotation.body["id"]

    def container_ids():
        result = subprocess.run(
            [*compose_command, "ps", "-q", "prometheus", "grafana"],
            check=True,
            capture_output=True,
            text=True,
        )
        return set(result.stdout.split())

    previous_ids = container_ids()
    assert len(previous_ids) == 2
    subprocess.run(
        [
            *compose_command,
            "up",
            "--detach",
            "--no-deps",
            "--force-recreate",
            "prometheus",
            "grafana",
        ],
        check=True,
    )
    monitoring.wait_ready()
    monitoring.wait_targets()
    assert len(container_ids()) == 2
    assert container_ids().isdisjoint(previous_ids)
    assert monitoring.query(expression, at=timestamp) == before
    annotations = monitoring.grafana("/api/annotations", query={"tags": "monitoring-e2e"})
    assert annotations.status == 200
    assert any(row["id"] == annotation_id and row["text"] == marker for row in annotations.body)
    assert monitoring.grafana("/api/datasources/uid/cafeteria-prometheus").status == 200


def test_grafana_login_and_dashboard_display_the_real_metrics(page: Page, monitoring: Monitoring):
    dashboard = monitoring.grafana("/api/dashboards/uid/cafeteria-metrics-connection")
    assert dashboard.status == 200
    assert dashboard.body["meta"]["provisioned"] is True
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{monitoring.grafana_url}/login")
    page.get_by_label("Email or username").fill(monitoring.user)
    page.get_by_label("Password", exact=True).fill(monitoring.password)
    page.get_by_role("button", name="Log in", exact=True).click()
    page.wait_for_url(lambda url: "/login" not in url, wait_until="load", timeout=30_000)
    page.goto(f"{monitoring.grafana_url}{dashboard.body['meta']['url']}")
    expect(page.get_by_text("Servicios con métricas", exact=True)).to_be_visible(timeout=30_000)
    expect(page.get_by_text("4 / 4", exact=True)).to_be_visible(timeout=30_000)
    for service in SERVICES:
        expect(page.get_by_text(service, exact=True)).to_be_visible()
    assert not errors, errors
    output = Path("test-results/monitoring/grafana-connected.png")
    output.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=output, full_page=True)
