"""Dependencias HTTP conectadas a los recursos de cada instancia de la app."""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.templating import Jinja2Templates

from .clients import BackendGateway
from .services.storefront import StorefrontService


def get_gateway(request: Request) -> BackendGateway:
    return request.app.state.gateway


GatewayDependency = Annotated[BackendGateway, Depends(get_gateway)]


def get_storefront(gateway: GatewayDependency) -> StorefrontService:
    return StorefrontService(gateway)


def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates


StorefrontDependency = Annotated[StorefrontService, Depends(get_storefront)]
TemplatesDependency = Annotated[Jinja2Templates, Depends(get_templates)]
