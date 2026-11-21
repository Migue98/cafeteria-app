"""Contrato ejecutado con el entorno independiente de cada servicio."""

from __future__ import annotations

import ast
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from app.main import create_app
from app.observability import TraceContext, get_logger, install_observability
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry, Counter, Histogram

TRACE_ID = "1234567890abcdef1234567890abcdef"
PARENT = "1234567890abcdef"
INCOMING = f"00-{TRACE_ID}-{PARENT}-00"


def events(caplog):
    return [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.getMessage().startswith("{")
    ]


def test_application_correlates_not_found_and_invalid_request_id(caplog):
    client = TestClient(create_app())
    request_id = str(uuid4())
    missing = client.get(
        "/not-a-route", headers={"X-Request-ID": request_id, "traceparent": INCOMING}
    )
    invalid = client.get(
        "/health", headers={"X-Request-ID": "invalid", "traceparent": INCOMING}
    )

    assert missing.status_code == 404
    assert invalid.status_code == 422
    assert missing.headers["X-Request-ID"] == request_id
    UUID(invalid.headers["X-Request-ID"])
    assert invalid.json()["trace_id"] == TRACE_ID
    completed = [
        event for event in events(caplog) if event["message"] == "request_completed"
    ]
    assert [event["status_code"] for event in completed] == [404, 422]
    for response, event in zip([missing, invalid], completed, strict=True):
        assert response.headers["traceparent"] == f"00-{TRACE_ID}-{event['span_id']}-00"
        assert event["span_id"] != PARENT
        assert event["trace_id"] == TRACE_ID
        assert event["parent_span_id"] == PARENT
        assert event["request_id"] == response.headers["X-Request-ID"]
        assert event["level"] == "WARNING"
        assert event["duration_ms"] >= 0
        assert (
            datetime.fromisoformat(event["timestamp"]).utcoffset().total_seconds() == 0
        )


@pytest.mark.parametrize(
    "incoming",
    [
        "",
        "invalid",
        f"00-{'0' * 32}-{PARENT}-01",
        f"00-{TRACE_ID}-{'0' * 16}-01",
        f"ff-{TRACE_ID}-{PARENT}-01",
        f"00-{TRACE_ID.upper()}-{PARENT}-01",
    ],
)
def test_invalid_traceparent_starts_a_new_trace(incoming):
    context = TraceContext.from_header(incoming)
    assert len(context.trace_id) == 32 and int(context.trace_id, 16)
    assert len(context.span_id) == 16 and int(context.span_id, 16)
    assert context.trace_id != TRACE_ID
    assert context.parent_span_id is None


def test_unhandled_failure_is_logged_and_counted(caplog):
    app = FastAPI()
    registry = CollectorRegistry()
    requests = Counter(
        "test_requests",
        "Requests",
        ["service", "method", "route", "status_code"],
        registry=registry,
    )
    duration = Histogram(
        "test_duration", "Duration", ["service", "method", "route"], registry=registry
    )
    install_observability(
        app,
        logger=get_logger("test-observability"),
        requests=requests,
        duration=duration,
        invalid_response=lambda _: JSONResponse({}, status_code=422),
    )

    @app.get("/broken")
    def broken():
        raise RuntimeError("test failure")

    response = TestClient(app, raise_server_exceptions=False).get("/broken")
    assert response.status_code == 500
    captured = events(caplog)
    failed = next(event for event in captured if event["message"] == "request_failed")
    completed = next(
        event for event in captured if event["message"] == "request_completed"
    )
    assert "test failure" in failed["exception"]
    assert failed["trace_id"] == completed["trace_id"]
    assert completed["status_code"] == 500
    assert completed["level"] == "ERROR"
    assert (
        registry.get_sample_value(
            "test_requests_total",
            {
                "service": "test-observability",
                "method": "GET",
                "route": "/broken",
                "status_code": "500",
            },
        )
        == 1
    )


def test_concurrent_requests_keep_their_context(caplog):
    client = TestClient(create_app())
    ids = [uuid4().hex for _ in range(8)]

    def invoke(trace_id):
        response = client.get(
            "/not-a-route", headers={"traceparent": f"00-{trace_id}-{PARENT}-01"}
        )
        assert response.headers["traceparent"].split("-")[1] == trace_id

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(invoke, ids))
    assert {event["trace_id"] for event in events(caplog)} == set(ids)


def test_observability_modules_have_the_same_behavior():
    root = Path(__file__).resolve().parents[2]
    modules = [
        ast.dump(
            ast.parse(
                (root / service / "app/observability.py").read_text(encoding="utf-8")
            )
        )
        for service in ("frontend", "svc-menu", "svc-pedidos", "svc-lealtad")
    ]
    assert len(set(modules)) == 1
