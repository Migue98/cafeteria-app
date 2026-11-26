from __future__ import annotations

import httpx
import pytest

from app.clients import BackendError, HttpBackendGateway
from app.config import load_settings

CONTEXT = {
    "request_id": "11111111-1111-4111-8111-111111111111",
    "traceparent": "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01",
}


@pytest.mark.parametrize(
    "payload", [[], None, {"balance": "7"}, {"balance": -1}, {"balance": True}, {}]
)
def test_invalid_balance_response_is_a_controlled_backend_error(monkeypatch, payload):
    gateway = HttpBackendGateway(load_settings())
    monkeypatch.setattr(
        gateway._client, "request", lambda *a, **kw: httpx.Response(200, json=payload)
    )
    try:
        with pytest.raises(BackendError) as failure:
            gateway.get_balance(
                customer_id="11111111-1111-4111-8111-111111111111", **CONTEXT
            )
        assert failure.value.status_code == 502
        assert failure.value.code == "INVALID_BACKEND_RESPONSE"
    finally:
        gateway.close()


def test_timeout_returns_public_error_without_internal_exception_detail(monkeypatch):
    gateway = HttpBackendGateway(load_settings())

    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("private-upstream-diagnostic")

    monkeypatch.setattr(gateway._client, "request", timeout)
    try:
        with pytest.raises(BackendError) as failure:
            gateway.list_products(**CONTEXT)
        assert failure.value.status_code == 503
        assert "private-upstream-diagnostic" not in str(failure.value)
    finally:
        gateway.close()


@pytest.mark.parametrize("payload", [{}, {"status": []}, {"status": "unexpected"}])
def test_invalid_health_status_marks_dependency_down(monkeypatch, payload):
    gateway = HttpBackendGateway(load_settings())
    monkeypatch.setattr(
        gateway._client, "request", lambda *a, **kw: httpx.Response(200, json=payload)
    )
    try:
        assert gateway.health(**CONTEXT) == {
            "menu": "down",
            "orders": "down",
            "loyalty": "down",
        }
    finally:
        gateway.close()


@pytest.mark.parametrize("method", ["list_products", "list_orders"])
@pytest.mark.parametrize("payload", [{}, {"items": [None]}])
def test_invalid_item_list_is_a_controlled_error(monkeypatch, method, payload):
    gateway = HttpBackendGateway(load_settings())
    monkeypatch.setattr(
        gateway._client, "request", lambda *a, **kw: httpx.Response(200, json=payload)
    )
    try:
        args = dict(CONTEXT)
        if method == "list_orders":
            args["customer_id"] = "11111111-1111-4111-8111-111111111111"
        with pytest.raises(BackendError) as failure:
            getattr(gateway, method)(**args)
        assert failure.value.status_code == 502
    finally:
        gateway.close()
