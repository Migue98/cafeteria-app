"""Métricas HTTP y de negocio registradas una sola vez por proceso."""

from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Peticiones HTTP atendidas.",
    ["service", "method", "route", "status_code"],
)
HTTP_DURATION = Histogram(
    "http_request_duration_seconds",
    "Duración de las peticiones HTTP.",
    ["service", "method", "route"],
)
ORDERS_CREATED = Counter("cafe_orders_total", "Pedidos creados.", ["status"])
ORDER_VALUE = Counter(
    "cafe_order_value_cents_total",
    "Valor acumulado de pedidos confirmados en centavos.",
)
