"""Trazas del SDK, correlación, aislamiento y envío OTLP HTTP/protobuf real."""

import json

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode
from prometheus_client import CollectorRegistry, Counter, Histogram

from app.observability import create_telemetry, get_logger, install_observability, log_event

from .test_context import INCOMING, PARENT, TRACE_ID, events


def instrumented_app(runtime):
    app = FastAPI()
    registry = CollectorRegistry()
    install_observability(
        app,
        logger=get_logger("test-observability"),
        requests=Counter(
            "test_requests",
            "Requests",
            ["service", "method", "route", "status_code"],
            registry=registry,
        ),
        duration=Histogram(
            "test_duration",
            "Duration",
            ["service", "method", "route"],
            registry=registry,
        ),
        invalid_response=lambda _: JSONResponse({}, status_code=422),
        telemetry=runtime,
    )

    @app.get("/work")
    def work():
        with runtime.tracer.start_as_current_span("business.work"):
            log_event(get_logger("test-observability"), "business_completed")
        return {"ok": True}

    @app.get("/broken")
    def broken():
        raise RuntimeError("controlled trace failure")

    return app


def test_sdk_spans_match_response_logs_and_sync_thread_context(telemetry, caplog):
    runtime, exporter = telemetry
    response = TestClient(instrumented_app(runtime)).get(
        "/work", headers={"traceparent": INCOMING[:-2] + "01"}
    )
    spans = exporter.get_finished_spans()
    server = next(span for span in spans if span.kind == SpanKind.SERVER)
    work = next(span for span in spans if span.name == "business.work")
    assert len(spans) == 2
    assert server.context.trace_id == work.context.trace_id == int(TRACE_ID, 16)
    assert server.parent.span_id == int(PARENT, 16)
    assert work.parent.span_id == server.context.span_id
    assert server.end_time > server.start_time
    assert server.resource.attributes["service.name"] == "test-observability"
    assert response.headers["traceparent"] == f"00-{TRACE_ID}-{server.context.span_id:016x}-01"
    completed = next(event for event in events(caplog) if event["message"] == "request_completed")
    business = next(event for event in events(caplog) if event["message"] == "business_completed")
    assert completed["span_id"] == f"{server.context.span_id:016x}"
    assert business["span_id"] == f"{work.context.span_id:016x}"
    assert business["trace_id"] == completed["trace_id"] == TRACE_ID
    assert not trace.get_current_span().get_span_context().is_valid


def test_unsampled_remote_parent_is_propagated_without_exporting(telemetry):
    runtime, exporter = telemetry
    response = TestClient(instrumented_app(runtime)).get("/work", headers={"traceparent": INCOMING})
    assert response.status_code == 200
    assert response.headers["traceparent"].split("-")[1] == TRACE_ID
    assert response.headers["traceparent"].endswith("-00")
    assert exporter.get_finished_spans() == ()


def test_unhandled_exception_is_an_error_span_with_the_same_log_id(telemetry, caplog):
    runtime, exporter = telemetry
    response = TestClient(instrumented_app(runtime), raise_server_exceptions=False).get("/broken")
    assert response.status_code == 500
    (server,) = exporter.get_finished_spans()
    assert server.kind == SpanKind.SERVER
    assert server.status.status_code == StatusCode.ERROR
    assert any(event.name == "exception" for event in server.events)
    failed = next(event for event in events(caplog) if event["message"] == "request_failed")
    assert failed["trace_id"] == f"{server.context.trace_id:032x}"
    assert failed["span_id"] == f"{server.context.span_id:016x}"


@pytest.mark.parametrize(
    "specific_endpoint", [False, True], ids=["base-endpoint", "traces-endpoint"]
)
def test_actual_otlp_protobuf_export_and_shutdown_flush(
    monkeypatch, otlp_receiver, specific_endpoint
):
    url, received = otlp_receiver
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "otlp")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"{url}/collector/")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_HEADERS", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_HEADERS", raising=False)
    if specific_endpoint:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", f"{url}/custom-traces")
    runtime = create_telemetry("otlp-integration", "test-version")
    with TestClient(instrumented_app(runtime)) as client:
        assert client.get("/work").status_code == 200
    path, content_type, body = received.get(timeout=5)
    assert path == ("/custom-traces" if specific_endpoint else "/collector/v1/traces")
    assert content_type == "application/x-protobuf"
    request = ExportTraceServiceRequest.FromString(body)
    (resource,) = request.resource_spans
    attributes = {
        attribute.key: attribute.value.string_value for attribute in resource.resource.attributes
    }
    assert attributes["service.name"] == "otlp-integration"
    assert attributes["service.version"] == "test-version"
    assert {span.name for scope in resource.scope_spans for span in scope.spans} == {
        "GET /work",
        "business.work",
    }


def test_console_export_is_one_json_object_per_span(monkeypatch, capsys):
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "console")
    runtime = create_telemetry("console-integration")
    with runtime.tracer.start_as_current_span("console-check"):
        pass
    runtime.shutdown()
    exported = json.loads(capsys.readouterr().out.strip())
    assert exported["name"] == "console-check"
    assert exported["resource"]["attributes"]["service.name"] == "console-integration"


@pytest.mark.parametrize("exporters", ["unknown", "none,otlp"])
def test_invalid_exporter_configuration_fails_at_startup(monkeypatch, exporters):
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", exporters)
    with pytest.raises(ValueError, match="OTEL_TRACES_EXPORTER"):
        create_telemetry("invalid")


def test_export_can_be_disabled_without_losing_trace_context(monkeypatch):
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "none")
    runtime = create_telemetry("no-export")
    with TestClient(instrumented_app(runtime)) as client:
        response = client.get("/work")
    _, trace_id, span_id, _ = response.headers["traceparent"].split("-")
    assert int(trace_id, 16) and int(span_id, 16)


def test_protocol_must_match_the_installed_exporter(monkeypatch):
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "otlp")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", "grpc")
    with pytest.raises(ValueError, match="http/protobuf"):
        create_telemetry("invalid-protocol")


def test_application_providers_are_independent_and_do_not_replace_global_state(monkeypatch):
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "none")
    original_provider = trace.get_tracer_provider()
    first = create_telemetry("first-service")
    second = create_telemetry("second-service")
    first_exporter = InMemorySpanExporter()
    second_exporter = InMemorySpanExporter()
    first.provider.add_span_processor(SimpleSpanProcessor(first_exporter))
    second.provider.add_span_processor(SimpleSpanProcessor(second_exporter))
    with TestClient(instrumented_app(second)) as second_client:
        with TestClient(instrumented_app(first)) as first_client:
            assert first_client.get("/work").status_code == 200
        assert second_client.get("/work").status_code == 200
    assert trace.get_tracer_provider() is original_provider
    first_spans = first_exporter.get_finished_spans()
    second_spans = second_exporter.get_finished_spans()
    assert len(first_spans) == len(second_spans) == 2
    assert {span.resource.attributes["service.name"] for span in first_spans} == {"first-service"}
    assert {span.resource.attributes["service.name"] for span in second_spans} == {"second-service"}
    assert first_spans[0].context.trace_id != second_spans[0].context.trace_id
