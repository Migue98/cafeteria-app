"""Inyección de los recursos de cada aplicación con Depends de FastAPI."""

from typing import Annotated

from fastapi import Depends, Request

from .clients import LoyaltyClient, MenuClient
from .repository import OrderRepository
from .services.orders import OrderService


def get_repository(request: Request) -> OrderRepository:
    return request.app.state.repository


def get_menu_client(request: Request) -> MenuClient:
    return request.app.state.menu_client


def get_loyalty_client(request: Request) -> LoyaltyClient:
    return request.app.state.loyalty_client


RepositoryDependency = Annotated[OrderRepository, Depends(get_repository)]
MenuDependency = Annotated[MenuClient, Depends(get_menu_client)]
LoyaltyDependency = Annotated[LoyaltyClient, Depends(get_loyalty_client)]


def get_order_service(
    repository: RepositoryDependency,
    menu: MenuDependency,
    loyalty: LoyaltyDependency,
) -> OrderService:
    return OrderService(repository, menu, loyalty)


OrderServiceDependency = Annotated[OrderService, Depends(get_order_service)]
