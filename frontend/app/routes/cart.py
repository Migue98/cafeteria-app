"""Operaciones HTTP del carrito y respuestas progresivas/HTMX."""

from fastapi import APIRouter, Request
from fastapi import Path as PathParameter
from fastapi.responses import RedirectResponse, Response

from ..clients import BackendError
from ..dependencies import StorefrontDependency, TemplatesDependency
from ..exceptions import ProductUnavailable
from ..presentation import render_cart, render_error
from ..services.cart import decrement_item, remove_item

router = APIRouter()


@router.post("/cart/items/{product_id}", tags=["carrito"])
def add_to_cart(
    request: Request,
    service: StorefrontDependency,
    templates: TemplatesDependency,
    product_id: int = PathParameter(ge=1),
) -> Response:
    try:
        context = service.add_to_cart(
            request.session,
            product_id,
            request_id=request.state.request_id,
            traceparent=request.state.traceparent,
        )
    except ProductUnavailable as exc:
        return render_error(
            request,
            templates,
            BackendError(str(exc), status_code=404, code="PRODUCT_UNAVAILABLE"),
        )
    except BackendError as exc:
        return render_error(request, templates, exc)
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request, name="_cart.html", context=context
        )
    return RedirectResponse(url="/#cart-panel", status_code=303)


@router.post("/cart/items/{product_id}/decrement", tags=["carrito"])
def decrement_cart_item(
    request: Request,
    service: StorefrontDependency,
    templates: TemplatesDependency,
    product_id: int = PathParameter(ge=1),
) -> Response:
    decrement_item(request.session, product_id)
    return render_cart(request, service, templates)


@router.post("/cart/items/{product_id}/remove", tags=["carrito"])
def remove_cart_item(
    request: Request,
    service: StorefrontDependency,
    templates: TemplatesDependency,
    product_id: int = PathParameter(ge=1),
) -> Response:
    remove_item(request.session, product_id)
    return render_cart(request, service, templates)
