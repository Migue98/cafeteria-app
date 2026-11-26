"""Salud de dependencias y exposición de métricas."""

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from ..dependencies import LoyaltyDependency, MenuDependency, RepositoryDependency
from ..models import HealthResponse
from ..services.health import check_health

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["operación"],
    operation_id="ordersHealth",
)
def health(
    request: Request,
    repository: RepositoryDependency,
    menu: MenuDependency,
    loyalty: LoyaltyDependency,
) -> HealthResponse:
    return check_health(
        repository,
        menu,
        loyalty,
        version=request.app.state.app_version,
        request_id=request.state.request_id,
        traceparent=request.state.traceparent,
    )


@router.get(
    "/metrics",
    response_class=Response,
    tags=["operación"],
    operation_id="ordersMetrics",
)
def metrics() -> Response:
    return Response(content=generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})
