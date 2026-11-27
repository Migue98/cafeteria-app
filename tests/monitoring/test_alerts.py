"""Caídas reales → evaluación Grafana → webhooks firing/resolved, sin Telegram."""

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.monitoring
RULES = {
    "cafeteria-service-down": "Servicio inaccesible",
    "cafeteria-http-errors": "Errores HTTP frecuentes",
    "cafeteria-points-pending": "Puntos pendientes",
}


class Alerting:
    def __init__(self, monitoring):
        self.monitoring = monitoring
        self.receiver_url = os.environ["E2E_ALERT_RECEIVER_URL"]

    def checkpoint(self):
        response = self.monitoring.api.json("GET", f"{self.receiver_url}/events")
        assert response.status == 200
        return len(response.body)

    def notification(self, uid, status, *, service, after=0):
        def delivered():
            response = self.monitoring.api.json("GET", f"{self.receiver_url}/events")
            assert response.status == 200
            for event in response.body[after:]:
                for alert in event.get("alerts", []):
                    if (
                        alert["labels"].get("alertname") == RULES[uid]
                        and alert["labels"].get("service") == service
                        and alert["status"] == status
                    ):
                        assert alert["labels"]["project"] == "cafeteria"
                        assert alert["annotations"]["summary"]
                        return alert
            return False

        return self.monitoring.until(
            delivered, timeout=150, description=f"notificación {uid}: {status} ({service})"
        )


@pytest.fixture(scope="module")
def alerting(monitoring):
    assert os.getenv("E2E_ALERTS") == "1", "Usa run_monitoring_e2e.py --alerts"
    client = Alerting(monitoring)
    yield client
    response = monitoring.api.json("GET", f"{client.receiver_url}/events")
    assert response.status == 200
    output = Path("test-results/monitoring/alert-notifications.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(response.body, ensure_ascii=False, indent=2), encoding="utf-8")


def test_rules_are_provisioned_and_visible_in_grafana(page: Page, monitoring, alerting):
    response = monitoring.grafana("/api/v1/provisioning/alert-rules")
    assert response.status == 200
    rules = {rule["uid"]: rule for rule in response.body}
    assert set(rules) == set(RULES)
    for uid, rule in rules.items():
        assert rule["title"] == RULES[uid]
        assert rule["provenance"] == "file"
        assert rule["for"] == "20s"
        assert rule["data"][0]["datasourceUid"] == "cafeteria-prometheus"
        assert rule["annotations"]["__dashboardUid__"].startswith("cafeteria-")
    policy = monitoring.grafana("/api/v1/provisioning/policies")
    assert policy.status == 200
    assert policy.body["receiver"] == "cafeteria-test-webhook"
    contacts = monitoring.grafana("/api/v1/provisioning/contact-points")
    assert contacts.status == 200
    assert not any(contact["type"] == "telegram" for contact in contacts.body)

    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.set_viewport_size({"width": 1600, "height": 1100})
    page.goto(f"{monitoring.grafana_url}/login")
    page.get_by_label("Email or username").fill(monitoring.user)
    page.get_by_label("Password", exact=True).fill(monitoring.password)
    page.get_by_role("button", name="Log in", exact=True).click()
    page.wait_for_url(lambda url: "/login" not in url, wait_until="load", timeout=30_000)
    page.goto(f"{monitoring.grafana_url}/alerting/list")
    page.get_by_test_id("data-testid radio-button-option list").check()
    for title in RULES.values():
        expect(page.get_by_text(title, exact=True).first).to_be_visible(timeout=30_000)
    output = Path("test-results/monitoring/grafana-alert-rules.png")
    output.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=output, full_page=True)
    assert not errors, errors


def test_service_down_sends_firing_and_resolved(alerting, monitoring, compose_command):
    checkpoint = alerting.checkpoint()
    try:
        subprocess.run([*compose_command, "stop", "svc-menu"], check=True)
        fired = alerting.notification(
            "cafeteria-service-down", "firing", service="svc-menu", after=checkpoint
        )
        assert "svc-menu" in fired["annotations"]["summary"]
    finally:
        subprocess.run([*compose_command, "start", "svc-menu"], check=True)
        monitoring.api.wait_until_healthy()
    resolved = alerting.notification(
        "cafeteria-service-down", "resolved", service="svc-menu", after=checkpoint
    )
    assert fired["startsAt"] == resolved["startsAt"]
    assert resolved["endsAt"] > resolved["startsAt"]


def test_http_error_burst_sends_firing_and_resolved(alerting, monitoring, compose_command):
    api = monitoring.api
    checkpoint = alerting.checkpoint()

    def fail_order(_index):
        return api.json(
            "POST",
            f"{api.orders_url}/api/v1/orders",
            headers={"Idempotency-Key": f"alert-error-{uuid4()}"},
            payload={"customer_id": str(uuid4()), "items": [{"product_id": 1, "quantity": 1}]},
            timeout=15,
        )

    try:
        subprocess.run([*compose_command, "stop", "svc-menu"], check=True)
        for _round in range(3):
            with ThreadPoolExecutor(max_workers=4) as pool:
                responses = list(pool.map(fail_order, range(8)))
            assert all(response.status == 503 for response in responses)
        fired = alerting.notification(
            "cafeteria-http-errors", "firing", service="svc-pedidos", after=checkpoint
        )
        assert "10%" in fired["annotations"]["summary"]
    finally:
        subprocess.run([*compose_command, "start", "svc-menu"], check=True)
        api.wait_until_healthy()
    resolved = alerting.notification(
        "cafeteria-http-errors", "resolved", service="svc-pedidos", after=checkpoint
    )
    assert fired["startsAt"] == resolved["startsAt"]


def test_pending_points_alert_resolves_after_the_automatic_retry(
    alerting, monitoring, compose_command
):
    api = monitoring.api
    customer = str(uuid4())
    checkpoint = alerting.checkpoint()
    try:
        subprocess.run([*compose_command, "stop", "svc-lealtad"], check=True)
        order = api.json(
            "POST",
            f"{api.orders_url}/api/v1/orders",
            headers={"Idempotency-Key": f"alert-pending-{uuid4()}"},
            payload={"customer_id": customer, "items": [{"product_id": 1, "quantity": 2}]},
            timeout=15,
        )
        assert order.status == 201 and order.body["loyalty_status"] == "pending"
        fired = alerting.notification(
            "cafeteria-points-pending", "firing", service="svc-pedidos", after=checkpoint
        )
        assert (
            float(
                monitoring.query('sum(cafe_loyalty_pending_orders{job="cafeteria"})')[0]["value"][1]
            )
            >= 1
        )
    finally:
        subprocess.run([*compose_command, "start", "svc-lealtad"], check=True)
        api.wait_until_healthy()

    def recovered():
        response = api.json("GET", f"{api.orders_url}/api/v1/orders/{order.body['id']}")
        assert response.status == 200
        return response.body["loyalty_status"] == "awarded"

    monitoring.until(recovered, description="puntos recuperados automáticamente")
    balance = api.json("GET", f"{api.loyalty_url}/api/v1/customers/{customer}/points")
    assert balance.status == 200 and balance.body["balance"] == 7
    resolved = alerting.notification(
        "cafeteria-points-pending", "resolved", service="svc-pedidos", after=checkpoint
    )
    assert fired["startsAt"] == resolved["startsAt"]
    assert (
        monitoring.query('sum(cafe_loyalty_pending_orders{job="cafeteria"})')[0]["value"][1] == "0"
    )
