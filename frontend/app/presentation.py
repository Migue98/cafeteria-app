"""Plantillas, filtros y respuestas HTML del frontend."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from .clients import BackendError
from .services.cart import read_cart
from .services.storefront import StorefrontService


def money(value: int) -> str:
    return f"${value / 100:,.2f}"


def date_time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return value
    return parsed.strftime("%d/%m/%Y · %H:%M %Z").strip()


def create_templates() -> Jinja2Templates:
    templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")
    templates.env.filters["money"] = money
    templates.env.filters["date_time"] = date_time
    templates.env.globals["navigation_cart_count"] = lambda session: sum(
        read_cart(session).values()
    )
    return templates


def render_error(request: Request, templates: Jinja2Templates, error: BackendError) -> Response:
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={"message": str(error), "code": error.code},
        status_code=error.status_code,
    )


def render_cart_error(
    request: Request,
    templates: Jinja2Templates,
    error: BackendError,
    *,
    product_id: int | None = None,
) -> Response:
    if request.headers.get("HX-Request") != "true":
        return render_error(request, templates, error)
    target = "#cart-feedback"
    if (
        product_id is not None
        and request.headers.get("HX-Trigger") == f"product-add-form-{product_id}"
    ):
        target = f"#product-feedback-{product_id}"
    return templates.TemplateResponse(
        request=request,
        name="_cart_error.html",
        context={"message": str(error)},
        status_code=error.status_code,
        headers={"HX-Retarget": target, "HX-Reswap": "innerHTML"},
    )


def render_home(
    request: Request,
    service: StorefrontService,
    templates: Jinja2Templates,
    *,
    category: str | None = None,
    checkout_error: str | None = None,
    status_code: int = 200,
) -> Response:
    try:
        context = service.menu_context(
            request.session,
            request_id=request.state.request_id,
            traceparent=request.state.traceparent,
            category=category,
            checkout_error=checkout_error,
        )
    except BackendError as exc:
        return render_error(request, templates, exc)
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context=context,
        status_code=status_code,
    )


def render_cart(
    request: Request, service: StorefrontService, templates: Jinja2Templates
) -> Response:
    if request.headers.get("HX-Request") == "true":
        try:
            context = service.current_cart(
                request.session,
                request_id=request.state.request_id,
                traceparent=request.state.traceparent,
            )
        except BackendError as exc:
            return render_cart_error(request, templates, exc)
        return templates.TemplateResponse(
            request=request, name="_cart_response.html", context=context
        )
    return RedirectResponse(url="/#cart-panel", status_code=303)
