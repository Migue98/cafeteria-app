"""Errores de negocio del frontend; su estado HTTP se decide en las rutas."""


class ProductUnavailable(RuntimeError):
    """El producto solicitado no está disponible en el catálogo."""


class EmptyCart(RuntimeError):
    """La confirmación requiere al menos un producto."""
