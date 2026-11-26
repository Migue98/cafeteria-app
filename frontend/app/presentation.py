"""Plantillas, filtros y respuestas HTML del frontend."""

from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from .clients import BackendError
from .services.storefront import StorefrontService


def money(value: int) -> str:
    return f"${value / 100:,.2f}"


def date_time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return value
    return parsed.strftime("%d/%m/%Y · %H:%M")


def create_templates() -> Jinja2Templates:
    templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")
    templates.env.filters["money"] = money
    templates.env.filters["date_time"] = date_time
    return templates


def render_error(
    request: Request, templates: Jinja2Templates, error: BackendError
) -> Response:
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={"message": str(error), "code": error.code},
        status_code=error.status_code,
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
            return HTMLResponse(escape(str(exc)), status_code=exc.status_code)
        return templates.TemplateResponse(
            request=request, name="_cart.html", context=context
        )
    return RedirectResponse(url="/#cart-panel", status_code=303)
