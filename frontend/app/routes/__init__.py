"""Rutas HTTP del frontend agrupadas por responsabilidad."""

from fastapi import APIRouter

from . import cart, catalog, operations, orders

router = APIRouter()
router.include_router(operations.router)
router.include_router(catalog.router)
router.include_router(cart.router)
router.include_router(orders.router)
