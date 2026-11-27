"""Clics reales y actualizaciones HTMX contra el Compose, sin simular servicios."""

from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest
from playwright.sync_api import Locator, Page, expect

from ..support import ApiClient

pytestmark = [pytest.mark.e2e, pytest.mark.browser]


def product(page: Page, name: str) -> Locator:
    return page.locator(".product-card").filter(
        has=page.get_by_role("heading", name=name, exact=True)
    )


def cart_item(page: Page, name: str) -> Locator:
    return page.locator("#cart-panel .cart-item").filter(
        has=page.get_by_role("heading", name=name, exact=True)
    )


def htmx_click(page: Page, button: Locator, path: str) -> None:
    """Exige XHR y CSRF; un formulario que navegue sin HTMX no pasa la prueba."""
    with page.expect_response(
        lambda response: response.url.endswith(path) and response.request.method == "POST"
    ) as received:
        button.click()
    response = received.value
    assert response.status == 200
    assert response.request.headers.get("hx-request") == "true"
    assert response.request.headers.get("x-csrf-token")
    assert not response.request.is_navigation_request()


def confirmed_order(page: Page, api: ApiClient) -> dict:
    expect(page.get_by_role("heading", name="Ya lo estamos preparando.")).to_be_visible()
    order_id = str(UUID(page.locator(".receipt").get_attribute("data-order-id")))
    result = api.json("GET", f"{api.orders_url}/api/v1/orders/{order_id}")
    assert result.status == 200
    return result.body


def assert_single_award(api: ApiClient, order: dict, loyalty_snapshot: Callable) -> None:
    customer_id = order["customer_id"]
    fetched = api.json("GET", f"{api.orders_url}/api/v1/orders/{order['id']}")
    listed = api.json("GET", f"{api.orders_url}/api/v1/orders", query={"customer_id": customer_id})
    balance = api.json("GET", f"{api.loyalty_url}/api/v1/customers/{customer_id}/points")
    points = order["total_cents"] // 1000
    assert fetched.status == listed.status == balance.status == 200
    assert fetched.body["loyalty_status"] == "awarded"
    assert fetched.body["points_earned"] == balance.body["balance"] == points
    assert listed.body["total"] == 1
    assert loyalty_snapshot(customer_id) == {
        "account_count": 1,
        "balance": points,
        "movement_count": 1,
        "distinct_orders": 1,
        "movement_points": points,
    }


@pytest.mark.parametrize(
    "viewport",
    [{"width": 1280, "height": 800}, {"width": 390, "height": 844}],
    ids=["desktop", "mobile-width"],
)
def test_cart_checkout_receipt_and_history(
    page: Page,
    api: ApiClient,
    browser_errors: list[str],
    loyalty_snapshot: Callable,
    viewport: dict,
) -> None:
    page.set_viewport_size(viewport)
    page.goto(f"{api.frontend_url}/")
    expect(page.locator(".cart-empty")).to_contain_text("Tu carrito está esperando")
    navigations: list[str] = []
    page.on(
        "framenavigated",
        lambda frame: navigations.append(frame.url) if frame == page.main_frame else None,
    )

    htmx_click(
        page,
        product(page, "Café americano").get_by_role("button", name="Agregar al carrito"),
        "/cart/items/1",
    )
    coffee = cart_item(page, "Café americano")
    expect(page.locator(".cart-count")).to_have_text("1")
    htmx_click(
        page, coffee.get_by_role("button", name="Agregar otro Café americano"), "/cart/items/1"
    )
    expect(coffee.locator(".quantity-controls strong")).to_have_text("2")
    expect(page.locator(".cart-total strong")).to_have_text("$70.00")
    htmx_click(
        page,
        coffee.get_by_role("button", name="Quitar uno de Café americano"),
        "/cart/items/1/decrement",
    )
    expect(coffee.locator(".quantity-controls strong")).to_have_text("1")
    expect(page.locator(".cart-total strong")).to_have_text("$35.00")
    htmx_click(page, coffee.get_by_role("button", name="Eliminar"), "/cart/items/1/remove")
    expect(page.locator(".cart-empty")).to_be_visible()
    expect(page.locator(".cart-count")).to_have_text("0")

    htmx_click(
        page,
        product(page, "Café americano").get_by_role("button", name="Agregar al carrito"),
        "/cart/items/1",
    )
    htmx_click(
        page, coffee.get_by_role("button", name="Agregar otro Café americano"), "/cart/items/1"
    )
    htmx_click(
        page,
        product(page, "Croissant").get_by_role("button", name="Agregar al carrito"),
        "/cart/items/11",
    )
    expect(page.locator(".cart-count")).to_have_text("3")
    expect(page.locator(".cart-total strong")).to_have_text("$109.00")
    assert navigations == [], "El carrito debe actualizarse mediante HTMX sin recargar la página"

    page.get_by_role("button", name="Confirmar pedido").click()
    order = confirmed_order(page, api)
    assert order["total_cents"] == 10900
    assert {(item["product_id"], item["quantity"]) for item in order["items"]} == {(1, 2), (11, 1)}
    expect(page.locator(".receipt-total strong")).to_have_text("$109.00")
    expect(page.locator("#receipt-points")).to_contain_text("+10 puntos")
    page.get_by_role("link", name="Ver mis pedidos").click()
    expect(page.get_by_role("heading", name="Mis pedidos", exact=True)).to_be_visible()
    expect(page.locator(".order-card")).to_have_count(1)
    expect(page.locator(".order-card")).to_contain_text(order["id"][:13])
    expect(page.locator(".order-card")).to_contain_text("2 × Café americano")
    expect(page.locator(".order-card")).to_contain_text("1 × Croissant")
    expect(page.locator(".order-card .status")).to_have_text("Puntos acreditados")
    expect(page.locator(".history-balance strong")).to_have_text("10")
    assert_single_award(api, order, loyalty_snapshot)
    assert not browser_errors, browser_errors


@pytest.mark.parametrize("view", ["receipt", "history"])
def test_pending_points_update_automatically_without_duplicate_checkout(
    page: Page,
    api: ApiClient,
    browser_errors: list[str],
    loyalty_outage: Callable,
    loyalty_snapshot: Callable,
    view: str,
) -> None:
    page.set_viewport_size({"width": 320, "height": 900})
    page.goto(f"{api.frontend_url}/")
    htmx_click(
        page,
        product(page, "Café americano").get_by_role("button", name="Agregar al carrito"),
        "/cart/items/1",
    )
    checkouts: list[str] = []
    page.on(
        "request",
        lambda request: (
            checkouts.append(request.url)
            if request.method == "POST" and request.url.endswith("/checkout")
            else None
        ),
    )
    with loyalty_outage():
        page.get_by_role("button", name="Confirmar pedido").click()
        order = confirmed_order(page, api)
        assert order["loyalty_status"] == "pending"
        expect(page.locator("#receipt-points")).to_contain_text("Puntos pendientes")
        if view == "history":
            page.get_by_role("link", name="Ver mis pedidos").click()
            expect(page.locator(".status")).to_have_text("Puntos pendientes")
            expect(page.locator(".history-balance strong")).to_have_text("Saldo no disponible")
        target = page.locator("#receipt-points" if view == "receipt" else "#order-history")
        expect(target).to_have_attribute("hx-trigger", "every 15s")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        output = Path("test-results/browser/usability")
        output.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=output / f"320-{view}-pending.png", full_page=True)

    # No recarga, evaluate(), fetch() ni cambio del temporizador de producción.
    path = f"/orders/{order['id']}/points" if view == "receipt" else "/orders"
    current_url = page.url
    navigations: list[str] = []
    page.on(
        "framenavigated",
        lambda frame: navigations.append(frame.url) if frame == page.main_frame else None,
    )
    with page.expect_response(
        lambda response: (
            response.url.endswith(path) and response.request.headers.get("hx-request") == "true"
        ),
        timeout=45_000,
    ) as polling:
        if view == "receipt":
            expect(target).to_contain_text("+3 puntos", timeout=45_000)
            expect(target).to_contain_text("Tu nuevo saldo es de 3 puntos.")
        else:
            expect(page.locator(".status")).to_have_text("Puntos acreditados", timeout=45_000)
            expect(page.locator(".history-balance strong")).to_have_text("3")
    assert polling.value.status == 200
    assert polling.value.request.method == "GET"
    assert not polling.value.request.is_navigation_request()
    assert target.get_attribute("hx-trigger") is None
    assert page.url == current_url
    assert navigations == []
    assert len(checkouts) == 1
    assert_single_award(api, order, loyalty_snapshot)
    assert not browser_errors, browser_errors
