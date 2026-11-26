"""Página del menú."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from ..dependencies import StorefrontDependency, TemplatesDependency
from ..presentation import render_home

router = APIRouter()


@router.get("/", response_class=HTMLResponse, tags=["interfaz"])
def home(
    request: Request,
    service: StorefrontDependency,
    templates: TemplatesDependency,
    category: str | None = None,
) -> Response:
    return render_home(request, service, templates, category=category)
