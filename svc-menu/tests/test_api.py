from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Product
from app.repository import RepositoryUnavailable


def make_products() -> list[Product]:
    now = datetime(2026, 11, 16, tzinfo=UTC)
    categories = ["bebidas-calientes", "bebidas-frias", "panaderia", "alimentos", "postres"]
    return [
        Product(
            id=index,
            sku=f"PRODUCTO-{index:02d}",
            name=f"Producto {index}",
            description=f"Descripción del producto {index}.",
            category=categories[(index - 1) % len(categories)],
            price_cents=3000 + index * 100,
            available=index != 20,
            created_at=now,
            updated_at=now,
        )
        for index in range(1, 21)
    ]


class FakeRepository:
    def __init__(self) -> None:
        self.products = make_products()

    def health(self) -> float:
        return 1.25

    def list_products(self, *, category, available, limit, offset):
        filtered = [product for product in self.products if product.available is available]
        if category is not None:
            filtered = [product for product in filtered if product.category == category]
        return filtered[offset : offset + limit], len(filtered)

    def get_product(self, product_id: int):
        return next((product for product in self.products if product.id == product_id), None)


class FailingRepository(FakeRepository):
    def health(self) -> float:
        raise RepositoryUnavailable("sin conexión")

    def list_products(self, **kwargs):
        raise RepositoryUnavailable("sin conexión")


def client(repository=None) -> TestClient:
    return TestClient(create_app(repository or FakeRepository()))


def test_health_reports_postgres_and_request_id() -> None:
    response = client().get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "svc-menu",
        "status": "healthy",
        "version": "dev",
        "dependencies": {"postgres": {"status": "up", "latency_ms": 1.25}},
    }
    UUID(response.headers["X-Request-ID"])


def test_list_products_uses_contract_defaults() -> None:
    response = client().get("/api/v1/products")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 19
    assert payload["limit"] == 20
    assert payload["offset"] == 0
    assert len(payload["items"]) == 19
    assert payload["items"][0]["currency"] == "MXN"


def test_list_products_filters_and_paginates() -> None:
    response = client().get(
        "/api/v1/products",
        params={"category": "bebidas-calientes", "limit": 2, "offset": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 4
    assert [item["id"] for item in payload["items"]] == [6, 11]


def test_list_can_include_unavailable_products() -> None:
    response = client().get("/api/v1/products", params={"available": "false"})

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == 20


def test_get_product() -> None:
    response = client().get("/api/v1/products/3")

    assert response.status_code == 200
    assert response.json()["sku"] == "PRODUCTO-03"


def test_missing_product_uses_problem_json() -> None:
    response = client().get("/api/v1/products/999")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "PRODUCT_NOT_FOUND"
    assert len(response.json()["trace_id"]) == 32


def test_invalid_query_uses_problem_json() -> None:
    response = client().get("/api/v1/products", params={"limit": 101})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_invalid_request_id_is_rejected() -> None:
    response = client().get("/health", headers={"X-Request-ID": "not-a-uuid"})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    UUID(response.headers["X-Request-ID"])


def test_dependency_failure_returns_503() -> None:
    response = client(FailingRepository()).get("/health")

    assert response.status_code == 503
    assert response.json()["code"] == "DEPENDENCY_UNAVAILABLE"


def test_metrics_are_exposed_for_prometheus() -> None:
    test_client = client()
    test_client.get("/health")
    response = test_client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "http_requests_total" in response.text
    assert "http_request_duration_seconds" in response.text


def test_generated_openapi_contains_contract_paths() -> None:
    paths = client().get("/openapi.json").json()["paths"]

    expected_paths = {
        "/health",
        "/metrics",
        "/api/v1/products",
        "/api/v1/products/{product_id}",
    }
    assert expected_paths <= set(paths)
