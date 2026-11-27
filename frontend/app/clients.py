"""Clientes HTTP para los servicios de negocio."""

from __future__ import annotations

from typing import Any, Protocol

import httpx
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.trace import TracerProvider

from .config import Settings


class BackendError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 503, code: str = "BACKEND_ERROR"):
        self.status_code = status_code
        self.code = code
        super().__init__(message)


def _invalid_backend_response() -> BackendError:
    return BackendError(
        "Un servicio devolvió una respuesta inválida. Intenta de nuevo.",
        status_code=502,
        code="INVALID_BACKEND_RESPONSE",
    )


def _list_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise _invalid_backend_response()
    return items


class BackendGateway(Protocol):
    def list_products(self, *, request_id: str, traceparent: str) -> list[dict[str, Any]]: ...

    def create_order(
        self,
        *,
        customer_id: str,
        items: list[dict[str, int]],
        idempotency_key: str,
        request_id: str,
        traceparent: str,
    ) -> dict[str, Any]: ...

    def list_orders(
        self, *, customer_id: str, request_id: str, traceparent: str
    ) -> list[dict[str, Any]]: ...

    def get_order(self, *, order_id: str, request_id: str, traceparent: str) -> dict[str, Any]: ...

    def get_balance(
        self, *, customer_id: str, request_id: str, traceparent: str
    ) -> dict[str, Any]: ...

    def health(self, *, request_id: str, traceparent: str) -> dict[str, str]: ...

    def close(self) -> None: ...


class HttpBackendGateway:
    def __init__(
        self, settings: Settings, *, tracer_provider: TracerProvider | None = None
    ) -> None:
        self._settings = settings
        self._client = httpx.Client(timeout=settings.http_timeout_seconds)
        HTTPXClientInstrumentor.instrument_client(self._client, tracer_provider=tracer_provider)

    def _request(
        self,
        method: str,
        url: str,
        *,
        request_id: str,
        traceparent: str,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        request_headers = {
            "X-Request-ID": request_id,
            "traceparent": traceparent,
            **(headers or {}),
        }
        try:
            response = self._client.request(
                method, url, headers=request_headers, follow_redirects=False, **kwargs
            )
        except httpx.RequestError as exc:
            raise BackendError(
                "Un servicio no está disponible temporalmente. Intenta de nuevo.",
                code="DEPENDENCY_UNAVAILABLE",
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise _invalid_backend_response() from exc

        if not isinstance(payload, dict):
            raise _invalid_backend_response()

        if response.is_error:
            raise BackendError(
                payload.get("detail", "El servicio rechazó la solicitud."),
                status_code=response.status_code,
                code=payload.get("code", "BACKEND_ERROR"),
            )
        return payload

    def list_products(self, *, request_id: str, traceparent: str) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            f"{self._settings.menu_url}/api/v1/products",
            request_id=request_id,
            traceparent=traceparent,
            params={"available": "true", "limit": 100},
        )
        return _list_items(payload)

    def create_order(
        self,
        *,
        customer_id: str,
        items: list[dict[str, int]],
        idempotency_key: str,
        request_id: str,
        traceparent: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self._settings.orders_url}/api/v1/orders",
            request_id=request_id,
            traceparent=traceparent,
            headers={"Idempotency-Key": idempotency_key},
            json={"customer_id": customer_id, "items": items},
        )

    def list_orders(
        self, *, customer_id: str, request_id: str, traceparent: str
    ) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            f"{self._settings.orders_url}/api/v1/orders",
            request_id=request_id,
            traceparent=traceparent,
            params={"customer_id": customer_id, "limit": 100},
        )
        return _list_items(payload)

    def get_balance(self, *, customer_id: str, request_id: str, traceparent: str) -> dict[str, Any]:
        payload = self._request(
            "GET",
            f"{self._settings.loyalty_url}/api/v1/customers/{customer_id}/points",
            request_id=request_id,
            traceparent=traceparent,
        )
        balance = payload.get("balance")
        if type(balance) is not int or balance < 0:
            raise _invalid_backend_response()
        return payload

    def get_order(self, *, order_id: str, request_id: str, traceparent: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{self._settings.orders_url}/api/v1/orders/{order_id}",
            request_id=request_id,
            traceparent=traceparent,
        )

    def health(self, *, request_id: str, traceparent: str) -> dict[str, str]:
        dependencies: dict[str, str] = {}
        urls = {
            "menu": self._settings.menu_url,
            "orders": self._settings.orders_url,
            "loyalty": self._settings.loyalty_url,
        }
        for name, url in urls.items():
            try:
                payload = self._request(
                    "GET",
                    f"{url}/health",
                    request_id=request_id,
                    traceparent=traceparent,
                )
                status = payload.get("status")
                dependencies[name] = status if status in ("healthy", "degraded") else "down"
            except BackendError:
                dependencies[name] = "down"
        return dependencies

    def close(self) -> None:
        self._client.close()
