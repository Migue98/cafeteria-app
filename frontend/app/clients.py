"""Clientes HTTP para los servicios de negocio."""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from .config import Settings


class BackendError(RuntimeError):
    def __init__(
        self, message: str, *, status_code: int = 503, code: str = "BACKEND_ERROR"
    ):
        self.status_code = status_code
        self.code = code
        super().__init__(message)


class BackendGateway(Protocol):
    def list_products(self, *, request_id: str) -> list[dict[str, Any]]: ...

    def create_order(
        self,
        *,
        customer_id: str,
        items: list[dict[str, int]],
        idempotency_key: str,
        request_id: str,
    ) -> dict[str, Any]: ...

    def list_orders(
        self, *, customer_id: str, request_id: str
    ) -> list[dict[str, Any]]: ...

    def get_balance(self, *, customer_id: str, request_id: str) -> dict[str, Any]: ...

    def health(self, *, request_id: str) -> dict[str, str]: ...

    def close(self) -> None: ...


class HttpBackendGateway:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.Client(timeout=settings.http_timeout_seconds)

    def _request(
        self,
        method: str,
        url: str,
        *,
        request_id: str,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        request_headers = {"X-Request-ID": request_id, **(headers or {})}
        try:
            response = self._client.request(
                method, url, headers=request_headers, follow_redirects=False, **kwargs
            )
        except httpx.RequestError as exc:
            raise BackendError(f"No fue posible contactar un servicio: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise BackendError(
                "Un servicio devolvió una respuesta que no es JSON.",
                status_code=502,
                code="INVALID_BACKEND_RESPONSE",
            ) from exc

        if response.is_error:
            raise BackendError(
                payload.get("detail", "El servicio rechazó la solicitud."),
                status_code=response.status_code,
                code=payload.get("code", "BACKEND_ERROR"),
            )
        return payload

    def list_products(self, *, request_id: str) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            f"{self._settings.menu_url}/api/v1/products",
            request_id=request_id,
            params={"available": "true", "limit": 100},
        )
        return payload["items"]

    def create_order(
        self,
        *,
        customer_id: str,
        items: list[dict[str, int]],
        idempotency_key: str,
        request_id: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self._settings.orders_url}/api/v1/orders",
            request_id=request_id,
            headers={"Idempotency-Key": idempotency_key},
            json={"customer_id": customer_id, "items": items},
        )

    def list_orders(self, *, customer_id: str, request_id: str) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            f"{self._settings.orders_url}/api/v1/orders",
            request_id=request_id,
            params={"customer_id": customer_id, "limit": 100},
        )
        return payload["items"]

    def get_balance(self, *, customer_id: str, request_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{self._settings.loyalty_url}/api/v1/customers/{customer_id}/points",
            request_id=request_id,
        )

    def health(self, *, request_id: str) -> dict[str, str]:
        dependencies: dict[str, str] = {}
        urls = {
            "menu": self._settings.menu_url,
            "orders": self._settings.orders_url,
            "loyalty": self._settings.loyalty_url,
        }
        for name, url in urls.items():
            try:
                payload = self._request("GET", f"{url}/health", request_id=request_id)
                dependencies[name] = payload["status"]
            except BackendError:
                dependencies[name] = "down"
        return dependencies

    def close(self) -> None:
        self._client.close()
