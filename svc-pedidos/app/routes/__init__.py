"""Rutas HTTP de pedidos y operación."""

from fastapi import APIRouter

from . import operations, orders

router = APIRouter()
router.include_router(operations.router)
router.include_router(orders.router)
