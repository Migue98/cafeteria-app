"""Clientes HTTP de los servicios de menú y lealtad."""

from __future__ import annotations

from time import perf_counter
from typing import Protocol

import httpx

from .models import MenuProduct, Order


class DependencyUnavailable(RuntimeError):
    """Una dependencia crítica no está disponible."""


class LoyaltyUnavailable(RuntimeError):
    """El servicio no crítico de lealtad no está disponible."""


class MenuClient(Protocol):
    def health(self, *, request_id: str, traceparent: str) -> float: ...

    def get_product(
        self,
        product_id: int,
        *,
        request_id: str,
        traceparent: str,
    ) -> MenuProduct | None: ...


class LoyaltyClient(Protocol):
    def health(self, *, request_id: str, traceparent: str) -> float: ...

    def award(
        self,
        order: Order,
        *,
        request_id: str,
        traceparent: str,
    ) -> int: ...


def _headers(request_id: str, traceparent: str) -> dict[str, str]:
    return {"X-Request-ID": request_id, "traceparent": traceparent}


class HttpMenuClient:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    def health(self, *, request_id: str, traceparent: str) -> float:
        started = perf_counter()
        try:
            response = httpx.get(
                f"{self._base_url}/health",
                headers=_headers(request_id, traceparent),
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise DependencyUnavailable("svc-menu no está disponible") from exc
        return round((perf_counter() - started) * 1000, 3)

    def get_product(
        self,
        product_id: int,
        *,
        request_id: str,
        traceparent: str,
    ) -> MenuProduct | None:
        try:
            response = httpx.get(
                f"{self._base_url}/api/v1/products/{product_id}",
                headers=_headers(request_id, traceparent),
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise DependencyUnavailable("svc-menu no está disponible") from exc
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise DependencyUnavailable("svc-menu rechazó la consulta del producto")
        return MenuProduct.model_validate(response.json())


class HttpLoyaltyClient:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    def health(self, *, request_id: str, traceparent: str) -> float:
        started = perf_counter()
        try:
            response = httpx.get(
                f"{self._base_url}/health",
                headers=_headers(request_id, traceparent),
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LoyaltyUnavailable("svc-lealtad no está disponible") from exc
        return round((perf_counter() - started) * 1000, 3)

    def award(
        self,
        order: Order,
        *,
        request_id: str,
        traceparent: str,
    ) -> int:
        headers = _headers(request_id, traceparent)
        headers["Idempotency-Key"] = str(order.id)
        try:
            response = httpx.post(
                f"{self._base_url}/api/v1/points/earn",
                headers=headers,
                json={
                    "order_id": str(order.id),
                    "customer_id": str(order.customer_id),
                    "amount_cents": order.total_cents,
                    "currency": order.currency,
                    "occurred_at": order.created_at.isoformat(),
                },
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise LoyaltyUnavailable("svc-lealtad no está disponible") from exc
        if response.status_code not in {200, 201}:
            raise LoyaltyUnavailable("svc-lealtad no pudo acreditar los puntos")
        return int(response.json()["points_earned"])
