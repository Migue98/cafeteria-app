"""Comprobación de dependencias críticas y degradación por lealtad."""

from ..clients import LoyaltyClient, LoyaltyUnavailable, MenuClient
from ..models import DependencyHealth, HealthDependencies, HealthResponse
from ..repository import OrderRepository


def check_health(
    repository: OrderRepository,
    menu: MenuClient,
    loyalty: LoyaltyClient,
    *,
    version: str,
    request_id: str,
    traceparent: str,
) -> HealthResponse:
    postgres_latency = repository.health()
    menu_latency = menu.health(request_id=request_id, traceparent=traceparent)
    try:
        loyalty_latency = loyalty.health(request_id=request_id, traceparent=traceparent)
        loyalty_health = DependencyHealth(status="up", critical=False, latency_ms=loyalty_latency)
        status = "healthy"
    except LoyaltyUnavailable:
        loyalty_health = DependencyHealth(status="down", critical=False)
        status = "degraded"
    return HealthResponse(
        status=status,
        version=version,
        dependencies=HealthDependencies(
            postgres=DependencyHealth(status="up", critical=True, latency_ms=postgres_latency),
            menu=DependencyHealth(status="up", critical=True, latency_ms=menu_latency),
            loyalty=loyalty_health,
        ),
    )
