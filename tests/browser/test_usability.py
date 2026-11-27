"""Regresiones de navegación móvil, recortes, teclado y errores visibles del carrito."""

import subprocess
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from .test_storefront import assert_single_award, confirmed_order, htmx_click, product

pytestmark = [pytest.mark.e2e, pytest.mark.browser]
OUTPUT = Path("test-results/browser/usability")


def capture(page, name):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(
        path=OUTPUT / f"{name}.png",
        full_page=not name.endswith(("-home", "-cart", "-cart-error")),
    )


def assert_no_overflow(page):
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), page.url


@pytest.mark.parametrize("width", [320, 390, 768, 1280, 1440])
def test_navigation_filters_and_layout_at_each_width(page: Page, api, browser_errors, width):
    page.set_viewport_size({"width": width, "height": 900})
    page.emulate_media(reduced_motion="reduce")
    page.goto(f"{api.frontend_url}/")
    navigation = page.get_by_role("navigation", name="Navegación principal")
    for name in ["Menú", "Mis pedidos", "Carrito"]:
        link = navigation.get_by_role("link", name=name)
        expect(link).to_be_visible()
        assert link.bounding_box()["height"] >= 44
    assert_no_overflow(page)
    # overflow:hidden ocultaba el texto del hero aunque el documento no desbordara.
    assert page.locator(".hero-copy").evaluate("""element => {
      const box = element.getBoundingClientRect();
      const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
      for (let text; text = walker.nextNode();) {
        if (!text.textContent.trim()) continue;
        const range = document.createRange(); range.selectNodeContents(text);
        for (const rect of range.getClientRects()) {
          if (rect.left < box.left - 1 || rect.right > box.right + 1) return false;
        }
      }
      return box.right <= innerWidth;
    }""")
    capture(page, f"{width}-home")
    page.get_by_role("link", name="Ver el menú", exact=True).click()
    heading = page.locator(".section-heading")
    assert heading.bounding_box()["y"] >= page.locator(".site-header").bounding_box()["height"]
    categories = page.get_by_role("navigation", name="Categorías del menú")
    categories.get_by_role("link", name="Postres", exact=True).click()
    expect(categories.get_by_role("link", name="Postres", exact=True)).to_have_attribute(
        "aria-current", "page"
    )
    assert 0 < page.locator(".product-card").count() < 20
    assert (
        page.locator(".product-card .category-postres").count()
        == page.locator(".product-card").count()
    )
    categories.get_by_role("link", name="Todo", exact=True).click()
    expect(page.locator(".product-card")).to_have_count(20)
    assert page.url.endswith("/#menu")
    assert_no_overflow(page)
    # Captura del catálogo acotada al viewport, sin generar una imagen de 20 tarjetas.
    OUTPUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=OUTPUT / f"{width}-menu.png")
    if width == 320:
        page.goto(f"{api.frontend_url}/?category=sin-productos#menu")
        expect(page.get_by_text("No encontramos productos en esta categoría.")).to_be_visible()
        assert_no_overflow(page)
        page.screenshot(path=OUTPUT / "320-empty-category.png")
    navigation.get_by_role("link", name="Mis pedidos", exact=True).click()
    expect(page.get_by_text("Todavía no tienes pedidos.", exact=True)).to_be_visible()
    expect(navigation.get_by_role("link", name="Mis pedidos", exact=True)).to_have_attribute(
        "aria-current", "page"
    )
    assert_no_overflow(page)
    capture(page, f"{width}-empty-history")
    assert not browser_errors, browser_errors


def test_keyboard_cart_focus_receipt_and_history_at_320px(page: Page, api, browser_errors):
    page.set_viewport_size({"width": 320, "height": 900})
    page.emulate_media(reduced_motion="reduce")
    page.goto(f"{api.frontend_url}/")
    page.keyboard.press("Tab")
    expect(page.get_by_role("link", name="Saltar al contenido")).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.locator("#main-content")).to_be_focused()
    button = product(page, "Café americano").get_by_role("button", name="Agregar al carrito")
    button.focus()
    with page.expect_response(lambda r: r.url.endswith("/cart/items/1") and r.status == 200):
        page.keyboard.press("Enter")
    expect(page.locator("#nav-cart-count")).to_have_text("(1)")
    expect(page.locator("#product-add-1")).to_be_focused()
    page.locator(".nav-cart").click()
    plus = page.get_by_role("button", name="Agregar otro Café americano")
    assert plus.bounding_box()["height"] >= 44 and plus.bounding_box()["width"] >= 44
    plus.focus()
    with page.expect_response(lambda r: r.url.endswith("/cart/items/1") and r.status == 200):
        page.keyboard.press("Enter")
    expect(page.locator(".cart-count")).to_have_text("2")
    expect(page.locator("#nav-cart-count")).to_have_text("(2)")
    expect(plus).to_be_focused()
    assert_no_overflow(page)
    capture(page, "320-cart")
    remove = page.get_by_role("button", name="Eliminar", exact=True)
    remove.focus()
    with page.expect_response(lambda r: r.url.endswith("/cart/items/1/remove") and r.status == 200):
        page.keyboard.press("Enter")
    expect(page.locator(".cart-count")).to_have_text("0")
    expect(page.locator("#cart-title")).to_be_focused()
    htmx_click(page, page.locator("#product-add-1"), "/cart/items/1")
    page.get_by_role("button", name="Confirmar pedido").click()
    expect(page.get_by_role("heading", name="Ya lo estamos preparando.")).to_be_visible()
    expect(page.locator(".receipt-total")).to_contain_text("Total del pedido")
    assert_no_overflow(page)
    capture(page, "320-receipt")
    page.get_by_role("link", name="Ver mis pedidos").click()
    expect(page.locator(".order-card .status")).to_have_text("Puntos acreditados")
    expect(page.locator(".order-card time")).to_have_attribute(
        "title", "Hora local (America/Mexico_City)"
    )
    assert_no_overflow(page)
    capture(page, "320-history")
    assert not browser_errors, browser_errors


def test_cart_shows_loading_error_and_recovers_without_losing_the_page(
    page: Page, api, compose_command
):
    page.set_viewport_size({"width": 390, "height": 844})
    page.emulate_media(reduced_motion="reduce")
    page.goto(f"{api.frontend_url}/")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    button = page.locator("#product-add-1")
    original_url = page.url
    try:
        subprocess.run([*compose_command, "pause", "svc-menu"], check=True)
        with page.expect_response(
            lambda r: r.url.endswith("/cart/items/1") and r.request.method == "POST"
        ) as failed:
            button.click()
            expect(button).to_be_disabled()
            expect(button.locator(".button-busy")).to_be_visible()
            expect(button.locator(".button-label")).to_be_hidden()
        assert failed.value.status == 503
        assert failed.value.headers["hx-retarget"] == "#product-feedback-1"
        expect(page.locator("#product-feedback-1").get_by_role("alert")).to_contain_text(
            "No pudimos actualizar el carrito."
        )
        expect(button).to_be_enabled()
        expect(page.locator(".cart-count")).to_have_text("0")
        assert page.url == original_url
        capture(page, "390-cart-error")
    finally:
        subprocess.run([*compose_command, "unpause", "svc-menu"], check=True)
        api.wait_until_healthy()
    htmx_click(page, button, "/cart/items/1")
    expect(page.locator("#product-feedback-1")).to_be_empty()
    expect(page.locator(".cart-count")).to_have_text("1")
    expect(page.locator("#nav-cart-count")).to_have_text("(1)")
    assert page.url == original_url
    assert_no_overflow(page)
    assert not errors, errors


def test_checkout_failure_is_visible_and_can_be_retried(
    page: Page, api, compose_command, loyalty_snapshot
):
    page.set_viewport_size({"width": 320, "height": 900})
    page.emulate_media(reduced_motion="reduce")
    page.goto(f"{api.frontend_url}/")
    htmx_click(page, page.locator("#product-add-1"), "/cart/items/1")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        subprocess.run([*compose_command, "stop", "svc-pedidos"], check=True)
        page.get_by_role("button", name="Confirmar pedido").click()
        alert = page.get_by_role("alert")
        expect(alert).to_contain_text("No pudimos confirmar el pedido.")
        assert alert.bounding_box()["y"] < 200
        expect(page.locator(".cart-count")).to_have_text("1")
        assert_no_overflow(page)
        page.screenshot(path=OUTPUT / "320-checkout-error.png")
    finally:
        subprocess.run([*compose_command, "start", "svc-pedidos"], check=True)
        api.wait_until_healthy()
    page.get_by_role("link", name="Volver al carrito").click()
    page.get_by_role("button", name="Confirmar pedido").click()
    order = confirmed_order(page, api)
    assert_single_award(api, order, loyalty_snapshot)
    assert not errors, errors
