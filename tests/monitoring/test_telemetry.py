"""Recorrido real stdout → Alloy → Loki y SDK → Alloy → Tempo, con correlación."""

import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

import pytest
from playwright.sync_api import Page, expect

from ..support import BrowserSession
from .conftest import SERVICES
from .telemetry_support import TelemetryClient

pytestmark = pytest.mark.monitoring


@pytest.fixture(scope="module")
def telemetry(monitoring):
    assert os.getenv("E2E_TELEMETRY") == "1", "Usa run_monitoring_e2e.py --telemetry"
    client = TelemetryClient(monitoring)
    client.ready()
    return client


@pytest.fixture(scope="module")
def examples(telemetry, api, compose_command):
    browser = BrowserSession()
    browser.request("POST", f"{api.frontend_url}/cart/items/1")
    success_id = str(uuid4())
    receipt = browser.request(
        "POST", f"{api.frontend_url}/checkout", headers={"X-Request-ID": success_id}
    )
    assert receipt.status == 200
    order_id = re.search(r'data-order-id="([0-9a-f-]+)"', receipt.body)[1]
    success_trace = receipt.headers["traceparent"].split("-")[1]
    browser.request("POST", f"{api.frontend_url}/cart/items/1")
    failure_id = str(uuid4())
    try:
        subprocess.run([*compose_command, "stop", "svc-menu"], check=True)
        failed = browser.request(
            "POST", f"{api.frontend_url}/checkout", headers={"X-Request-ID": failure_id}
        )
        assert failed.status == 503
    finally:
        subprocess.run([*compose_command, "start", "svc-menu"], check=True)
        api.wait_until_healthy()
    return {
        "success": success_trace,
        "failure": failed.headers["traceparent"].split("-")[1],
        "success_request": success_id,
        "failure_request": failure_id,
        "order_id": order_id,
    }


def test_sources_are_provisioned_with_links_in_both_directions(telemetry):
    monitoring = telemetry.monitoring
    loki = monitoring.grafana("/api/datasources/uid/cafeteria-loki")
    tempo = monitoring.grafana("/api/datasources/uid/cafeteria-tempo")
    assert loki.status == tempo.status == 200
    assert loki.body["readOnly"] and tempo.body["readOnly"]
    (field,) = loki.body["jsonData"]["derivedFields"]
    assert field["datasourceUid"] == "cafeteria-tempo"
    assert field["url"] == "${__value.raw}"
    assert re.search(field["matcherRegex"], json.dumps({"trace_id": "a" * 32}))[1] == "a" * 32
    back = tempo.body["jsonData"]["tracesToLogsV2"]
    assert back["datasourceUid"] == "cafeteria-loki"
    assert "${__span.traceId}" in back["query"]


def test_purchase_logs_match_the_exported_http_and_postgresql_trace(telemetry, examples):
    trace_id = examples["success"]

    def collected():
        rows = telemetry.logs(trace_id)
        assert {row["event"]["service"] for row in rows} == SERVICES, rows
        return rows

    rows = telemetry.monitoring.until(collected, description="logs de la compra en Loki")
    assert all(row["event"]["request_id"] == examples["success_request"] for row in rows)
    assert all(
        row["labels"]["compose_project"] == os.environ["E2E_COMPOSE_PROJECT"] for row in rows
    )
    labels = telemetry.monitoring.grafana(
        "/api/datasources/proxy/uid/cafeteria-loki/loki/api/v1/labels"
    )
    assert labels.status == 200
    assert not {"trace_id", "request_id", "span_id"}.intersection(labels.body["data"])

    def traced():
        spans = telemetry.spans(trace_id)
        assert {span["service"] for span in spans} == SERVICES, spans
        sql = [
            span
            for span in spans
            if span["attributes"].get("db.system", span["attributes"].get("db.system.name"))
            == "postgresql"
        ]
        assert {span["service"] for span in sql} == SERVICES - {"frontend"}, spans
        return spans

    spans = telemetry.monitoring.until(traced, description="traza distribuida en Tempo")
    by_id = {span["id"]: span for span in spans}
    assert all(span["trace"] == trace_id for span in spans)
    for row in rows:
        event = row["event"]
        assert event["span_id"] in by_id
        assert by_id[event["span_id"]]["service"] == event["service"]
    roots = [span for span in spans if not span["parent"]]
    assert len(roots) == 1 and roots[0]["service"] == "frontend"
    assert all(span["parent"] in by_id for span in spans if span["parent"])
    assert all(int(span["endTimeUnixNano"]) > int(span["startTimeUnixNano"]) for span in spans)


def test_dependency_failure_has_an_error_log_linked_to_an_error_span(telemetry, examples):
    trace_id = examples["failure"]

    def failed_log():
        rows = [row for row in telemetry.logs(trace_id) if row["event"].get("level") == "ERROR"]
        assert rows
        return rows

    rows = telemetry.monitoring.until(failed_log, description="log ERROR de la falla")

    def failed_trace():
        spans = telemetry.spans(trace_id)
        assert any(
            span.get("status", {}).get("code") in [2, "STATUS_CODE_ERROR"] for span in spans
        ), spans
        return spans

    spans = telemetry.monitoring.until(failed_trace, description="span de error en Tempo")
    by_id = {span["id"]: span for span in spans}
    for row in rows:
        assert row["event"]["request_id"] == examples["failure_request"]
        assert row["event"]["span_id"] in by_id
    assert any(row["event"].get("status_code") == 503 for row in rows)


def test_logs_and_traces_survive_recreating_storage_and_collector(
    telemetry, examples, compose_command
):
    trace_id = examples["success"]
    expected_span_ids = {span["id"] for span in telemetry.spans(trace_id)}
    assert expected_span_ids and telemetry.logs(trace_id)
    subprocess.run(
        [
            *compose_command,
            "up",
            "--detach",
            "--no-deps",
            "--force-recreate",
            "loki",
            "tempo",
            "alloy",
        ],
        check=True,
    )
    telemetry.ready()

    def restored():
        spans = telemetry.spans(trace_id)
        assert {span["id"] for span in spans} == expected_span_ids, spans
        rows = telemetry.logs(trace_id)
        assert {row["event"]["service"] for row in rows} == SERVICES, rows
        return True

    telemetry.monitoring.until(restored, timeout=180, description="logs y spans persistidos")


def test_grafana_navigates_from_an_error_log_to_its_trace_and_back(page: Page, telemetry, examples):
    monitoring = telemetry.monitoring
    trace_id = examples["failure"]
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.set_viewport_size({"width": 1800, "height": 1100})
    page.goto(f"{monitoring.grafana_url}/login")
    page.get_by_label("Email or username").fill(monitoring.user)
    page.get_by_label("Password", exact=True).fill(monitoring.password)
    page.get_by_role("button", name="Log in", exact=True).click()
    page.wait_for_url(lambda url: "/login" not in url, wait_until="load", timeout=30_000)
    state = {
        "A": {
            "datasource": "cafeteria-loki",
            "queries": [
                {
                    "refId": "A",
                    "datasource": {"type": "loki", "uid": "cafeteria-loki"},
                    "expr": f'{{job="cafeteria"}} |= "{trace_id}"',
                    "queryType": "range",
                    "editorMode": "code",
                }
            ],
            "range": {"from": "now-15m", "to": "now"},
        }
    }
    query = urlencode({"schemaVersion": 1, "panes": json.dumps(state), "orgId": 1})
    page.goto(f"{monitoring.grafana_url}/explore?{query}")
    page.get_by_test_id("data-testid Log line menu button").first.click(timeout=30_000)
    page.get_by_text("Show log details", exact=True).click()
    page.get_by_text("Ver traza", exact=True).click()
    expect(page.get_by_text("Service & Operation", exact=False).first).to_be_visible(timeout=30_000)
    page.get_by_test_id("SpanBar--label").first.click()
    back = page.get_by_role("link", name="Logs for this trace", exact=True)
    expect(back).to_be_visible()
    output = Path("test-results/monitoring")
    output.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=output / "grafana-log-to-trace.png", full_page=True)

    def is_correlated_logs(response):
        if "/api/ds/query" not in response.url or response.request.method != "POST":
            return False
        queries = response.request.post_data_json.get("queries", [])
        return any(
            target.get("datasource", {}).get("uid") == "cafeteria-loki"
            and target.get("expr", "").startswith('{job="cafeteria"')
            and f'trace_id="{trace_id}"' in target["expr"]
            and 'service="frontend"' in target["expr"]
            for target in queries
        )

    with page.expect_response(is_correlated_logs, timeout=30_000) as returned:
        back.click()
    assert returned.value.status == 200
    data = json.dumps(returned.value.json())
    assert trace_id in data and examples["failure_request"] in data
    expect(page.get_by_text(re.compile(r"^1 line displayed")).last).to_be_visible(timeout=30_000)
    page.screenshot(path=output / "grafana-trace-to-logs.png", full_page=True)
    assert not errors, errors
