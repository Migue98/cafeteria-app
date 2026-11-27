"""Checkout, historial y fragmentos de puntos."""

from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from ..clients import BackendError
from ..dependencies import StorefrontDependency, TemplatesDependency
from ..exceptions import EmptyCart
from ..presentation import render_error, render_home

router = APIRouter()


@router.post("/checkout", response_class=HTMLResponse, tags=["pedidos"])
def checkout(
    request: Request, service: StorefrontDependency, templates: TemplatesDependency
) -> Response:
    try:
        context = service.checkout(
            request.session,
            request_id=request.state.request_id,
            traceparent=request.state.traceparent,
        )
    except EmptyCart as exc:
        return render_home(request, service, templates, checkout_error=str(exc), status_code=400)
    except BackendError as exc:
        return render_home(
            request,
            service,
            templates,
            checkout_error=str(exc),
            status_code=exc.status_code,
        )
    return templates.TemplateResponse(
        request=request,
        name="receipt.html",
        context=context,
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/orders", response_class=HTMLResponse, tags=["pedidos"])
def orders(
    request: Request, service: StorefrontDependency, templates: TemplatesDependency
) -> Response:
    try:
        context = service.order_history(
            request.session,
            request_id=request.state.request_id,
            traceparent=request.state.traceparent,
        )
    except BackendError as exc:
        if request.headers.get("HX-Request") == "true":
            return Response(
                status_code=exc.status_code,
                headers={"HX-Reswap": "none", "Cache-Control": "private, no-store"},
            )
        return render_error(request, templates, exc)
    return templates.TemplateResponse(
        request=request,
        name="_order_history.html"
        if request.headers.get("HX-Request") == "true"
        else "orders.html",
        context=context,
        headers={"Cache-Control": "private, no-store", "Vary": "HX-Request"},
    )


@router.get("/orders/{order_id}/points", response_class=HTMLResponse, tags=["pedidos"])
def order_points(
    request: Request,
    order_id: UUID,
    service: StorefrontDependency,
    templates: TemplatesDependency,
) -> Response:
    try:
        context = service.order_points(
            request.session,
            str(order_id),
            request_id=request.state.request_id,
            traceparent=request.state.traceparent,
        )
    except BackendError as exc:
        return Response(
            status_code=exc.status_code,
            headers={"HX-Reswap": "none", "Cache-Control": "private, no-store"},
        )
    if context is None:
        return Response(status_code=404, headers={"Cache-Control": "private, no-store"})
    return templates.TemplateResponse(
        request=request,
        name="_receipt_points.html",
        context=context,
        headers={"Cache-Control": "private, no-store"},
    )
