"""Dashboards provisionados consultan las métricas reales y se abren en Chromium."""

import math
import os
from pathlib import Path
from uuid import uuid4

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.monitoring
UIDS = ("cafeteria-application", "cafeteria-business")


@pytest.fixture(scope="module")
def dashboards(monitoring):
    order = monitoring.api.json(
        "POST",
        f"{monitoring.api.orders_url}/api/v1/orders",
        headers={"Idempotency-Key": f"dashboard-{uuid4()}"},
        payload={"customer_id": str(uuid4()), "items": [{"product_id": 1, "quantity": 2}]},
    )
    assert order.status == 201 and order.body["points_earned"] == 7
    monitoring.until(
        lambda: (
            float(
                monitoring.query('sum(cafe_orders_total{job="cafeteria",status="confirmed"})')[0][
                    "value"
                ][1]
            )
            >= 1
        ),
        description="compra visible para los dashboards",
    )
    sources = {}
    for uid in UIDS:
        response = monitoring.grafana(f"/api/dashboards/uid/{uid}")
        assert response.status == 200
        assert response.body["meta"]["provisioned"] is True
        assert response.body["dashboard"]["editable"] is False
        sources[uid] = response.body
    return sources


def test_dashboard_queries_are_valid_against_real_prometheus(monitoring, dashboards):
    if os.getenv("E2E_ALERTS") != "1":
        policy = monitoring.grafana("/api/v1/provisioning/policies")
        assert policy.status == 200
        route = policy.body["routes"][0]
        assert policy.body["receiver"] == "cafeteria-local-only"
        assert not route.get("object_matchers") and not route.get("matchers")
        assert route["mute_time_intervals"] == ["cafeteria-local-only"]
    for dashboard in dashboards.values():
        for panel in dashboard["dashboard"]["panels"]:
            for target in panel["targets"]:
                assert target["datasource"]["uid"] == "cafeteria-prometheus"
                expression = target["expr"].replace("$__rate_interval", "1m")
                expression = expression.replace("$__range", "15m")
                result = monitoring.query(expression, grafana=True)
                assert isinstance(result, list), panel["title"]
                # Sin tráfico, las latencias pueden ser NaN: no se convierten en ceros ficticios.
                if panel["type"] == "stat":
                    assert result, panel["title"]
                    assert all(math.isfinite(float(row["value"][1])) for row in result)
    stats = dashboards["cafeteria-business"]["dashboard"]["panels"][:3]
    values = [
        float(monitoring.query(panel["targets"][0]["expr"], grafana=True)[0]["value"][1])
        for panel in stats
    ]
    assert values[0] >= 1 and values[1] >= 70 and values[2] >= 7


def test_technical_and_business_dashboards_render_in_chromium(page: Page, monitoring, dashboards):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.set_viewport_size({"width": 1600, "height": 1500})
    page.goto(f"{monitoring.grafana_url}/login")
    page.get_by_label("Email or username").fill(monitoring.user)
    page.get_by_label("Password", exact=True).fill(monitoring.password)
    page.get_by_role("button", name="Log in", exact=True).click()
    page.wait_for_url(lambda url: "/login" not in url, wait_until="load", timeout=30_000)
    output = Path("test-results/monitoring")
    output.mkdir(parents=True, exist_ok=True)
    for uid, dashboard in dashboards.items():
        page.goto(f"{monitoring.grafana_url}{dashboard['meta']['url']}")
        for panel in dashboard["dashboard"]["panels"]:
            expect(page.get_by_text(panel["title"], exact=True)).to_be_visible(timeout=30_000)
        expect(page.get_by_text("Query error", exact=True)).to_have_count(0)
        page.screenshot(path=output / f"{uid}.png", full_page=True)
    assert not errors, errors
