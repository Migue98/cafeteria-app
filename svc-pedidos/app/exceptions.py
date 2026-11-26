"""Errores de negocio independientes de la capa HTTP."""

from uuid import UUID


class ProductUnavailable(RuntimeError):
    def __init__(self, product_id: int) -> None:
        self.product_id = product_id
        super().__init__(f"El producto {product_id} no está disponible")


class IdempotencyConflict(RuntimeError):
    """La misma clave fue reutilizada con una solicitud diferente."""


class OrderNotFound(RuntimeError):
    def __init__(self, order_id: UUID) -> None:
        super().__init__(f"No existe el pedido {order_id}.")
