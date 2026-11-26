"""Aplicación web server-side de la cafetería."""

from __future__ import annotations

import hashlib
import json
from contextlib import asynccontextmanager
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi import Path as PathParameter
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .clients import BackendError, BackendGateway, HttpBackendGateway
from .config import Settings, load_settings
from .observability import get_logger, install_observability
from .security import CSRFMiddleware, SecurityHeadersMiddleware, security_headers

LOGGER = get_logger("frontend")
BASE_DIR = Path(__file__).resolve().parent

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


def _money(value: int) -> str:
    return f"${value / 100:,.2f}"


def _date_time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return value
    return parsed.strftime("%d/%m/%Y · %H:%M")


def _customer_id(request: Request) -> str:
    raw = request.session.get("customer_id")
    try:
        customer_id = str(UUID(raw)) if raw else str(uuid4())
    except (TypeError, ValueError):
        customer_id = str(uuid4())
    request.session["customer_id"] = customer_id
    return customer_id


def _cart(request: Request) -> dict[int, int]:
    stored = request.session.get("cart", {})
    cart: dict[int, int] = {}
    if isinstance(stored, dict):
        for product_id, quantity in stored.items():
            try:
                parsed_id = int(product_id)
                parsed_quantity = int(quantity)
            except (TypeError, ValueError):
                continue
            if parsed_id >= 1 and 1 <= parsed_quantity <= 20:
                cart[parsed_id] = parsed_quantity
    return cart


def _save_cart(request: Request, cart: dict[int, int]) -> None:
    request.session["cart"] = {str(key): value for key, value in cart.items()}
    if cart:
        _customer_id(request)
        _checkout_key(request, cart)
    else:
        request.session.pop("checkout_attempt", None)


def _cart_context(
    cart: dict[int, int], products: list[dict[str, Any]]
) -> dict[str, Any]:
    product_map = {product["id"]: product for product in products}
    rows = []
    for product_id, quantity in sorted(cart.items()):
        product = product_map.get(product_id)
        if product is None:
            continue
        rows.append(
            {
                **product,
                "quantity": quantity,
                "line_total_cents": product["price_cents"] * quantity,
            }
        )
    return {
        "cart_rows": rows,
        "cart_count": sum(row["quantity"] for row in rows),
        "cart_total_cents": sum(row["line_total_cents"] for row in rows),
    }


def _checkout_key(request: Request, cart: dict[int, int]) -> str:
    fingerprint = hashlib.sha256(
        json.dumps(cart, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    attempt = request.session.get("checkout_attempt", {})
    if isinstance(attempt, dict) and attempt.get("fingerprint") == fingerprint:
        key = attempt.get("key")
        if isinstance(key, str):
            return key
    key = f"frontend-order-{uuid4()}"
    request.session["checkout_attempt"] = {"fingerprint": fingerprint, "key": key}
    return key


def create_app(
    gateway: BackendGateway | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    backend = gateway or HttpBackendGateway(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        backend.close()

    application = FastAPI(
        title="Cafetería - Frontend",
        version="0.1.0",
        description="Interfaz HTML para menú, carrito, pedidos y puntos.",
        lifespan=lifespan,
        docs_url=None if settings.app_env == "production" else "/docs",
        redoc_url=None if settings.app_env == "production" else "/redoc",
        openapi_url=None if settings.app_env == "production" else "/openapi.json",
    )
    application.state.gateway = backend
    application.state.app_version = settings.app_version
    application.add_middleware(CSRFMiddleware, settings=settings)
    application.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie=(
            "__Host-cafeteria_session"
            if settings.app_env == "production"
            else "cafeteria_session"
        ),
        max_age=settings.session_max_age_seconds,
        same_site="lax",
        https_only=settings.session_https_only,
    )
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(settings.allowed_hosts),
        www_redirect=False,
    )
    application.mount(
        "/static", StaticFiles(directory=BASE_DIR / "static"), name="static"
    )
    templates = Jinja2Templates(directory=BASE_DIR / "templates")
    templates.env.filters["money"] = _money
    templates.env.filters["date_time"] = _date_time

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            {
                "title": "Error interno",
                "status": 500,
                "code": "INTERNAL_ERROR",
                "detail": "No pudimos completar la solicitud. Intenta de nuevo.",
                "trace_id": getattr(request.state, "trace_id", None),
            },
            status_code=500,
            headers={
                **security_headers(settings),
                "Cache-Control": "private, no-store",
            },
        )

    def invalid_request_id(request: Request) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "title": "Encabezado inválido",
                "status": 422,
                "detail": "X-Request-ID debe ser un UUID válido.",
                "code": "VALIDATION_ERROR",
                "trace_id": request.state.trace_id,
            },
        )

    install_observability(
        application,
        logger=LOGGER,
        requests=HTTP_REQUESTS,
        duration=HTTP_DURATION,
        invalid_response=invalid_request_id,
    )
    application.add_middleware(SecurityHeadersMiddleware, settings=settings)

    def customer_balance(request: Request, customer_id: str) -> int | None:
        try:
            return backend.get_balance(
                customer_id=customer_id,
                request_id=request.state.request_id,
                traceparent=request.state.traceparent,
            )["balance"]
        except BackendError:
            return None

    def menu_context(
        request: Request,
        *,
        category: str | None = None,
        checkout_error: str | None = None,
    ) -> dict[str, Any]:
        customer_id = _customer_id(request)
        cart = _cart(request)
        if cart:
            _checkout_key(request, cart)
        products = backend.list_products(
            request_id=request.state.request_id, traceparent=request.state.traceparent
        )
        categories = sorted({product["category"] for product in products})
        visible_products = [
            product
            for product in products
            if category is None or product["category"] == category
        ]
        try:
            balance = backend.get_balance(
                customer_id=customer_id,
                request_id=request.state.request_id,
                traceparent=request.state.traceparent,
            )["balance"]
            balance_available = True
        except BackendError:
            balance = 0
            balance_available = False
        return {
            "request": request,
            "products": visible_products,
            "all_products": products,
            "categories": categories,
            "selected_category": category,
            "customer_id": customer_id,
            "balance": balance,
            "balance_available": balance_available,
            "checkout_error": checkout_error,
            **_cart_context(cart, products),
        }

    def render_home(
        request: Request,
        *,
        category: str | None = None,
        checkout_error: str | None = None,
        status_code: int = 200,
    ) -> Response:
        try:
            context = menu_context(
                request, category=category, checkout_error=checkout_error
            )
        except BackendError as exc:
            return templates.TemplateResponse(
                request=request,
                name="error.html",
                context={"message": str(exc), "code": exc.code},
                status_code=exc.status_code,
            )
        return templates.TemplateResponse(
            request=request,
            name="home.html",
            context=context,
            status_code=status_code,
        )

    @application.get("/health", tags=["operación"])
    def health(request: Request) -> JSONResponse:
        dependencies = backend.health(
            request_id=request.state.request_id, traceparent=request.state.traceparent
        )
        status = (
            "healthy"
            if all(value == "healthy" for value in dependencies.values())
            else "degraded"
        )
        return JSONResponse(
            {
                "service": "frontend",
                "status": status,
                "version": application.state.app_version,
                "dependencies": dependencies,
            }
        )

    @application.get("/metrics", tags=["operación"])
    def metrics() -> Response:
        return Response(
            content=generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST}
        )

    @application.get("/", response_class=HTMLResponse, tags=["interfaz"])
    def home(request: Request, category: str | None = None) -> Response:
        return render_home(request, category=category)

    @application.post("/cart/items/{product_id}", tags=["carrito"])
    def add_to_cart(
        request: Request,
        product_id: int = PathParameter(ge=1),
    ) -> Response:
        try:
            products = backend.list_products(
                request_id=request.state.request_id,
                traceparent=request.state.traceparent,
            )
        except BackendError as exc:
            return templates.TemplateResponse(
                request=request,
                name="error.html",
                context={"message": str(exc), "code": exc.code},
                status_code=exc.status_code,
            )
        if product_id not in {product["id"] for product in products}:
            return templates.TemplateResponse(
                request=request,
                name="error.html",
                context={
                    "message": "El producto no está disponible.",
                    "code": "PRODUCT_UNAVAILABLE",
                },
                status_code=404,
            )
        cart = _cart(request)
        cart[product_id] = min(cart.get(product_id, 0) + 1, 20)
        _save_cart(request, cart)
        if request.headers.get("HX-Request") == "true":
            return templates.TemplateResponse(
                request=request,
                name="_cart.html",
                context=_cart_context(cart, products),
            )
        return RedirectResponse(url="/#cart-panel", status_code=303)

    @application.post("/cart/items/{product_id}/decrement", tags=["carrito"])
    def decrement_cart_item(
        request: Request,
        product_id: int = PathParameter(ge=1),
    ) -> Response:
        cart = _cart(request)
        if product_id in cart:
            cart[product_id] -= 1
            if cart[product_id] <= 0:
                cart.pop(product_id)
        _save_cart(request, cart)
        if request.headers.get("HX-Request") == "true":
            try:
                products = backend.list_products(
                    request_id=request.state.request_id,
                    traceparent=request.state.traceparent,
                )
            except BackendError as exc:
                return HTMLResponse(escape(str(exc)), status_code=exc.status_code)
            return templates.TemplateResponse(
                request=request,
                name="_cart.html",
                context=_cart_context(cart, products),
            )
        return RedirectResponse(url="/#cart-panel", status_code=303)

    @application.post("/cart/items/{product_id}/remove", tags=["carrito"])
    def remove_cart_item(
        request: Request,
        product_id: int = PathParameter(ge=1),
    ) -> Response:
        cart = _cart(request)
        cart.pop(product_id, None)
        _save_cart(request, cart)
        if request.headers.get("HX-Request") == "true":
            try:
                products = backend.list_products(
                    request_id=request.state.request_id,
                    traceparent=request.state.traceparent,
                )
            except BackendError as exc:
                return HTMLResponse(escape(str(exc)), status_code=exc.status_code)
            return templates.TemplateResponse(
                request=request,
                name="_cart.html",
                context=_cart_context(cart, products),
            )
        return RedirectResponse(url="/#cart-panel", status_code=303)

    @application.post("/checkout", response_class=HTMLResponse, tags=["pedidos"])
    def checkout(request: Request) -> Response:
        cart = _cart(request)
        if not cart:
            return render_home(
                request,
                checkout_error="Agrega al menos un producto antes de confirmar.",
                status_code=400,
            )
        customer_id = _customer_id(request)
        try:
            order = backend.create_order(
                customer_id=customer_id,
                items=[
                    {"product_id": product_id, "quantity": quantity}
                    for product_id, quantity in sorted(cart.items())
                ],
                idempotency_key=_checkout_key(request, cart),
                request_id=request.state.request_id,
                traceparent=request.state.traceparent,
            )
        except BackendError as exc:
            return render_home(
                request,
                checkout_error=str(exc),
                status_code=exc.status_code,
            )

        _save_cart(request, {})
        request.session.pop("checkout_attempt", None)
        return templates.TemplateResponse(
            request=request,
            name="receipt.html",
            context={"order": order, "balance": customer_balance(request, customer_id)},
            headers={"Cache-Control": "private, no-store"},
        )

    @application.get("/orders", response_class=HTMLResponse, tags=["pedidos"])
    def orders(request: Request) -> Response:
        customer_id = _customer_id(request)
        try:
            order_items = backend.list_orders(
                customer_id=customer_id,
                request_id=request.state.request_id,
                traceparent=request.state.traceparent,
            )
        except BackendError as exc:
            if request.headers.get("HX-Request") == "true":
                return Response(
                    status_code=exc.status_code,
                    headers={"HX-Reswap": "none", "Cache-Control": "private, no-store"},
                )
            return templates.TemplateResponse(
                request=request,
                name="error.html",
                context={"message": str(exc), "code": exc.code},
                status_code=exc.status_code,
            )
        return templates.TemplateResponse(
            request=request,
            name=(
                "_order_history.html"
                if request.headers.get("HX-Request") == "true"
                else "orders.html"
            ),
            context={
                "orders": order_items,
                "balance": customer_balance(request, customer_id),
                "has_pending": any(
                    order["loyalty_status"] == "pending" for order in order_items
                ),
            },
            headers={"Cache-Control": "private, no-store", "Vary": "HX-Request"},
        )

    @application.get(
        "/orders/{order_id}/points", response_class=HTMLResponse, tags=["pedidos"]
    )
    def order_points(request: Request, order_id: UUID) -> Response:
        customer_id = _customer_id(request)
        try:
            order = backend.get_order(
                order_id=str(order_id),
                request_id=request.state.request_id,
                traceparent=request.state.traceparent,
            )
        except BackendError as exc:
            return Response(
                status_code=exc.status_code,
                headers={"HX-Reswap": "none", "Cache-Control": "private, no-store"},
            )
        if order["customer_id"] != customer_id:
            return Response(
                status_code=404, headers={"Cache-Control": "private, no-store"}
            )
        return templates.TemplateResponse(
            request=request,
            name="_receipt_points.html",
            context={"order": order, "balance": customer_balance(request, customer_id)},
            headers={"Cache-Control": "private, no-store"},
        )

    return application


app = create_app()
