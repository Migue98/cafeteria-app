"""Salud y métricas del frontend."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from ..dependencies import GatewayDependency

router = APIRouter()


@router.get("/health", tags=["operación"])
def health(request: Request, backend: GatewayDependency) -> JSONResponse:
    dependencies = backend.health(
        request_id=request.state.request_id, traceparent=request.state.traceparent
    )
    status = (
        "healthy"
        if all(value == "healthy" for value in dependencies.values())
        else "degraded"
    )
    return JSONResponse(
        {
            "service": "frontend",
            "status": status,
            "version": request.app.state.app_version,
            "dependencies": dependencies,
        }
    )


@router.get("/metrics", tags=["operación"])
def metrics() -> Response:
    return Response(
        content=generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST}
    )
