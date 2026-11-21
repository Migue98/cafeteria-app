from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import EarnPointsRequest, PointAward, PointsBalance
from app.repository import RepositoryUnavailable, StoredAward

CUSTOMER_ID = UUID("11111111-1111-4111-8111-111111111111")
ORDER_ID = UUID("22222222-2222-4222-8222-222222222222")


class FakeRepository:
    def __init__(self) -> None:
        self.by_key: dict[str, StoredAward] = {}
        self.by_order: dict[UUID, StoredAward] = {}
        self.balances: dict[UUID, PointsBalance] = {}

    def health(self) -> float:
        return 1.5

    def get_by_idempotency_key(self, key: str):
        return self.by_key.get(key)

    def get_by_order_id(self, order_id: UUID):
        return self.by_order.get(order_id)

    def bind_idempotency_key(self, key: str, movement_id: UUID):
        stored = next(
            award for award in self.by_order.values() if award.award.movement_id == movement_id
        )
        return self.by_key.setdefault(key, stored)

    def save_award(
        self,
        payload: EarnPointsRequest,
        *,
        points_earned: int,
        idempotency_key: str,
        request_hash: str,
        movement_id: UUID,
        awarded_at: datetime,
    ):
        if idempotency_key in self.by_key or payload.order_id in self.by_order:
            return None
        previous = self.balances.get(
            payload.customer_id,
            PointsBalance(customer_id=payload.customer_id, balance=0, updated_at=None),
        )
        balance = previous.balance + points_earned
        award = PointAward(
            movement_id=movement_id,
            order_id=payload.order_id,
            customer_id=payload.customer_id,
            points_earned=points_earned,
            balance=balance,
            awarded_at=awarded_at,
        )
        stored = StoredAward(award=award, request_hash=request_hash)
        self.by_key[idempotency_key] = stored
        self.by_order[payload.order_id] = stored
        self.balances[payload.customer_id] = PointsBalance(
            customer_id=payload.customer_id,
            balance=balance,
            updated_at=awarded_at,
        )
        return award

    def get_balance(self, customer_id: UUID) -> PointsBalance:
        return self.balances.get(
            customer_id,
            PointsBalance(customer_id=customer_id, balance=0, updated_at=None),
        )


class FailingRepository(FakeRepository):
    def health(self) -> float:
        raise RepositoryUnavailable("PostgreSQL no está disponible")

    def get_balance(self, customer_id: UUID) -> PointsBalance:
        raise RepositoryUnavailable("PostgreSQL no está disponible")


def make_client(repository: FakeRepository | None = None) -> tuple[TestClient, FakeRepository]:
    repository = repository or FakeRepository()
    return TestClient(create_app(repository)), repository


def award_payload(
    *,
    order_id: UUID = ORDER_ID,
    customer_id: UUID = CUSTOMER_ID,
    amount_cents: int = 10900,
) -> dict:
    return {
        "order_id": str(order_id),
        "customer_id": str(customer_id),
        "amount_cents": amount_cents,
        "currency": "MXN",
    }


def earn(client: TestClient, *, key: str = "loyalty-test-001", payload: dict | None = None):
    return client.post(
        "/api/v1/points/earn",
        headers={"Idempotency-Key": key},
        json=payload or award_payload(),
    )


def test_health_reports_postgres() -> None:
    client, _ = make_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "svc-lealtad",
        "status": "healthy",
        "version": "dev",
        "dependencies": {"postgres": {"status": "up", "latency_ms": 1.5}},
    }


def test_earn_points_uses_complete_ten_peso_units() -> None:
    client, _ = make_client()

    response = earn(client)

    assert response.status_code == 201
    assert response.json()["points_earned"] == 10
    assert response.json()["balance"] == 10
    assert response.json()["rule"] == "1-point-per-10-mxn-v1"
    assert response.json()["replayed"] is False


def test_amount_below_ten_pesos_records_zero_points() -> None:
    client, _ = make_client()

    response = earn(client, payload=award_payload(amount_cents=999))

    assert response.status_code == 201
    assert response.json()["points_earned"] == 0
    assert response.json()["balance"] == 0


def test_same_key_and_body_replays_original_award() -> None:
    client, repository = make_client()

    first = earn(client)
    second = earn(client)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["movement_id"] == first.json()["movement_id"]
    assert second.json()["replayed"] is True
    assert len(repository.by_order) == 1


def test_same_key_with_different_body_conflicts() -> None:
    client, _ = make_client()
    earn(client)

    response = earn(client, payload=award_payload(amount_cents=11900))

    assert response.status_code == 409
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_same_order_with_other_key_replays() -> None:
    client, repository = make_client()
    first = earn(client)

    second = earn(client, key="loyalty-test-002")

    assert second.status_code == 200
    assert second.json()["movement_id"] == first.json()["movement_id"]
    assert second.json()["replayed"] is True
    assert len(repository.by_order) == 1


def test_key_used_to_replay_order_cannot_be_reused_for_another_order() -> None:
    client, repository = make_client()
    earn(client)
    replay = earn(client, key="loyalty-alias-002")
    assert replay.status_code == 200

    response = earn(
        client,
        key="loyalty-alias-002",
        payload=award_payload(order_id=UUID("33333333-3333-4333-8333-333333333333")),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert len(repository.by_order) == 1
    assert repository.get_balance(CUSTOMER_ID).balance == 10


def test_same_order_with_different_data_conflicts() -> None:
    client, _ = make_client()
    earn(client)

    response = earn(
        client,
        key="loyalty-test-002",
        payload=award_payload(amount_cents=11900),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ORDER_ALREADY_AWARDED"


def test_balance_accumulates_and_replay_keeps_original_balance() -> None:
    client, _ = make_client()
    first = earn(client)
    second_order = UUID("33333333-3333-4333-8333-333333333333")

    second = earn(
        client,
        key="loyalty-test-002",
        payload=award_payload(order_id=second_order, amount_cents=5500),
    )
    replay = earn(client)
    balance = client.get(f"/api/v1/customers/{CUSTOMER_ID}/points")

    assert first.json()["balance"] == 10
    assert second.json()["points_earned"] == 5
    assert second.json()["balance"] == 15
    assert replay.json()["balance"] == 10
    assert balance.json()["balance"] == 15


def test_unknown_customer_has_zero_balance() -> None:
    client, _ = make_client()
    customer_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"

    response = client.get(f"/api/v1/customers/{customer_id}/points")

    assert response.status_code == 200
    assert response.json() == {
        "customer_id": customer_id,
        "balance": 0,
        "updated_at": None,
    }


def test_idempotency_key_is_required() -> None:
    client, _ = make_client()

    response = client.post("/api/v1/points/earn", json=award_payload())

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_invalid_request_id_is_rejected() -> None:
    client, _ = make_client()

    response = client.get("/health", headers={"X-Request-ID": "invalid"})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    UUID(response.headers["X-Request-ID"])


def test_database_failure_returns_problem_json() -> None:
    client, _ = make_client(FailingRepository())

    response = client.get("/health")

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "DEPENDENCY_UNAVAILABLE"


def test_metrics_and_openapi_paths_are_available() -> None:
    client, _ = make_client()
    earn(client)

    metrics = client.get("/metrics")
    paths = client.get("/openapi.json").json()["paths"]

    assert metrics.status_code == 200
    assert "cafe_loyalty_points_total" in metrics.text
    assert "cafe_loyalty_awards_total" in metrics.text
    assert {
        "/health",
        "/metrics",
        "/api/v1/points/earn",
        "/api/v1/customers/{customer_id}/points",
    } <= set(paths)
