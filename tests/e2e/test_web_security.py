from __future__ import annotations

import pytest

from .conftest import ApiClient, BrowserSession

pytestmark = pytest.mark.e2e


def test_csrf_cannot_be_bypassed_with_htmx_header(api: ApiClient):
    for path in ("/cart/items/1", "/checkout"):
        rejected = api.json(
            "POST", f"{api.frontend_url}{path}", headers={"HX-Request": "true"}
        )
        assert rejected.status == 403
        assert rejected.body["code"] == "CSRF_REJECTED"
        assert rejected.headers["x-content-type-options"] == "nosniff"


def test_cross_origin_submission_is_rejected_without_changing_cart(
    api: ApiClient, browser: BrowserSession
):
    browser.request("GET", f"{api.frontend_url}/")
    rejected = browser.request(
        "POST",
        f"{api.frontend_url}/cart/items/1",
        headers={"Origin": "https://attacker.example"},
    )
    assert rejected.status == 403
    home = browser.request("GET", f"{api.frontend_url}/")
    assert "Tu carrito está esperando" in home.body
    valid = browser.request("POST", f"{api.frontend_url}/cart/items/1")
    assert valid.status == 200
    assert "$35.00" in valid.body


def test_local_assets_csp_and_rejected_host(api: ApiClient, browser: BrowserSession):
    home = browser.request("GET", f"{api.frontend_url}/")
    assert "/static/vendor/htmx-2.0.4.min.js" in home.body
    assert "unpkg.com" not in home.body
    assert home.headers["cache-control"] == "private, no-store"
    assert "script-src 'self'" in home.headers["content-security-policy"]
    cookie = home.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    asset = api.text(f"{api.frontend_url}/static/vendor/htmx-2.0.4.min.js")
    assert asset.status == 200
    rejected = api.json(
        "GET", f"{api.frontend_url}/health", headers={"Host": "untrusted.example"}
    )
    assert rejected.status == 400
