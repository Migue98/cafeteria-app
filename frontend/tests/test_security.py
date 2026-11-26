from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient
from test_frontend import FakeGateway

from app.config import load_settings
from app.main import create_app


def bootstrap(client):
    page = client.get("/")
    assert page.status_code == 200
    return re.search(r'name="csrf-token" content="([^"]+)"', page.text)[1]


@pytest.mark.parametrize(
    "path",
    ["/cart/items/1", "/cart/items/1/decrement", "/cart/items/1/remove", "/checkout"],
)
def test_mutations_require_session_and_valid_token(path):
    gateway = FakeGateway()
    client = TestClient(create_app(gateway))
    assert client.post(path).status_code == 403
    bootstrap(client)
    rejected = client.post(path, data={"csrf_token": "wrong"})
    assert rejected.status_code == 403
    assert rejected.json()["code"] == "CSRF_REJECTED"
    assert gateway.create_calls == []
    assert "Traceback" not in rejected.text


def test_normal_forms_and_htmx_support_the_same_library_token():
    gateway = FakeGateway()
    client = TestClient(create_app(gateway))
    token = bootstrap(client)
    form = client.post(
        "/cart/items/1", data={"csrf_token": token}, follow_redirects=False
    )
    assert form.status_code == 303
    fragment = client.post(
        "/cart/items/1", headers={"HX-Request": "true", "X-CSRF-Token": token}
    )
    assert fragment.status_code == 200
    assert 'name="csrf_token"' in fragment.text
    assert token in fragment.text
    receipt = client.post(
        "/checkout", data={"csrf_token": token}, headers={"Origin": "http://testserver"}
    )
    assert receipt.status_code == 200
    assert len(gateway.orders) == 1
    assert gateway.orders[0]["items"][0]["quantity"] == 2
    assert bootstrap(client) == token


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://evil.example"},
        {"Origin": "null"},
        {"Origin": "http://testserver.evil.example"},
        {"Origin": "http://testserver/path"},
        {"Origin": "http://["},
        {"Origin": "http://testserver", "Sec-Fetch-Site": "cross-site"},
        {"Referer": "https://evil.example/form"},
    ],
)
def test_cross_origin_forms_rejected_even_with_token(headers):
    client = TestClient(create_app(FakeGateway()))
    token = bootstrap(client)
    response = client.post("/cart/items/1", headers=headers, data={"csrf_token": token})
    assert response.status_code == 403


def test_token_from_another_session_and_modified_cookie_are_rejected():
    app = create_app(FakeGateway())
    first, second = TestClient(app), TestClient(app)
    stolen = bootstrap(first)
    bootstrap(second)
    assert (
        second.post("/cart/items/1", headers={"X-CSRF-Token": stolen}).status_code
        == 403
    )
    first.cookies.clear()
    first.cookies.set("cafeteria_session", "forged-unsigned-session")
    assert (
        first.post("/cart/items/1", headers={"X-CSRF-Token": stolen}).status_code == 403
    )


@pytest.mark.parametrize("cookie_value", [None, "unsigned", "raw-token", "tampered"])
def test_csrf_cookie_must_be_present_and_correctly_signed(cookie_value):
    client = TestClient(create_app(FakeGateway()))
    token = bootstrap(client)
    cookies = dict(client.cookies)
    signed = cookies.pop("cafeteria_csrf")
    if cookie_value is not None:
        cookies["cafeteria_csrf"] = {
            "raw-token": token,
            "tampered": signed + "changed",
        }.get(cookie_value, cookie_value)
    client.cookies.clear()
    client.cookies.update(cookies)
    assert (
        client.post("/cart/items/1", headers={"X-CSRF-Token": token}).status_code == 403
    )
    renewed = bootstrap(client)
    assert renewed != token
    assert (
        client.post(
            "/cart/items/1", data={"csrf_token": renewed}, follow_redirects=False
        ).status_code
        == 303
    )


def test_valid_csrf_cookie_and_token_cannot_be_moved_to_another_session():
    app = create_app(FakeGateway())
    first, second = TestClient(app), TestClient(app)
    first_token = bootstrap(first)
    bootstrap(second)
    cookies = dict(second.cookies)
    cookies["cafeteria_csrf"] = first.cookies["cafeteria_csrf"]
    second.cookies.clear()
    second.cookies.update(cookies)
    assert (
        second.post("/cart/items/1", headers={"X-CSRF-Token": first_token}).status_code
        == 403
    )


def test_csrf_settings_are_isolated_between_app_instances():
    first = TestClient(
        create_app(FakeGateway(), replace(load_settings(), session_secret="first-test"))
    )
    first_token = bootstrap(first)
    second = TestClient(
        create_app(
            FakeGateway(), replace(load_settings(), session_secret="second-test")
        )
    )
    second_token = bootstrap(second)
    for client, token in ((first, first_token), (second, second_token)):
        assert (
            client.post(
                "/cart/items/1", data={"csrf_token": token}, follow_redirects=False
            ).status_code
            == 303
        )


def test_expired_tokens_reject_post_and_can_be_renewed_by_loading_menu(monkeypatch):
    from itsdangerous.timed import TimestampSigner

    settings = load_settings()
    gateway = FakeGateway()
    client = TestClient(create_app(gateway, settings))
    token = bootstrap(client)
    assert (
        client.post(
            "/cart/items/1", data={"csrf_token": token}, follow_redirects=False
        ).status_code
        == 303
    )
    now = TimestampSigner("test-only").get_timestamp()
    # Renueva la sesión sin rotar el CSRF: después solo habrá caducado este último.
    monkeypatch.setattr(
        TimestampSigner,
        "get_timestamp",
        lambda self: now + settings.session_max_age_seconds // 2,
    )
    assert bootstrap(client) == token
    monkeypatch.setattr(
        TimestampSigner,
        "get_timestamp",
        lambda self: now + settings.session_max_age_seconds + 1,
    )
    assert client.post("/cart/items/1", data={"csrf_token": token}).status_code == 403
    renewed = bootstrap(client)
    assert renewed != token
    assert client.post("/checkout", data={"csrf_token": renewed}).status_code == 200
    assert gateway.orders[0]["items"][0]["quantity"] == 1


def test_duplicate_token_fields_are_rejected():
    client = TestClient(create_app(FakeGateway()))
    token = bootstrap(client)
    response = client.post(
        "/cart/items/1",
        content=f"csrf_token={token}&csrf_token={token}",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 403


def test_chunked_and_declared_body_limits_apply_with_valid_token():
    client = TestClient(create_app(FakeGateway()))
    token = bootstrap(client)
    response = client.post(
        "/cart/items/1",
        content=iter([b"x" * 5000, b"y" * 5000]),
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 413
    response = client.post(
        "/cart/items/1", data={"csrf_token": token, "extra": "x" * 9000}
    )
    assert response.status_code == 413
    response = client.post(
        "/cart/items/1",
        data={"csrf_token": token},
        headers={"X-CSRF-Token": "incorrect"},
    )
    assert response.status_code == 403


def test_production_environment_requires_explicit_allowed_hosts(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("ALLOWED_HOSTS", raising=False)
    with pytest.raises(ValueError, match="ALLOWED_HOSTS"):
        load_settings()


def test_every_rendered_form_contains_token_and_has_no_inline_js():
    client = TestClient(create_app(FakeGateway()))
    token = bootstrap(client)
    client.post("/cart/items/1", data={"csrf_token": token})
    page = client.get("/")

    class FormAudit(HTMLParser):
        def __init__(self):
            super().__init__()
            self.forms = 0
            self.fields = 0
            self.scripts = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            assert not any(name.startswith("on") for name in attrs)
            if tag == "form":
                self.forms += 1
            if tag == "input" and attrs.get("name") == "csrf_token":
                self.fields += 1
                assert attrs["value"] == token
            if tag == "script":
                self.scripts.append(attrs.get("src"))

    audit = FormAudit()
    audit.feed(page.text)
    assert audit.forms >= 6
    assert audit.forms == audit.fields
    assert audit.scripts == ["/static/vendor/htmx-2.0.4.min.js"]


@pytest.mark.parametrize("path", ["/", "/orders", "/not-a-route", "/static/styles.css"])
def test_security_headers_apply_to_success_and_errors(path):
    client = TestClient(create_app(FakeGateway()))
    response = client.get(path)
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    csp = response.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    if not path.startswith("/static/"):
        assert response.headers["Cache-Control"] == "private, no-store"
    assert "Strict-Transport-Security" not in response.headers


def test_unknown_host_is_rejected_with_security_headers():
    response = TestClient(create_app(FakeGateway())).get(
        "/", headers={"Host": "attacker.example"}
    )
    assert response.status_code == 400
    assert response.headers["X-Frame-Options"] == "DENY"


def test_local_htmx_has_pinned_content_and_license():
    client = TestClient(create_app(FakeGateway()))
    asset = client.get("/static/vendor/htmx-2.0.4.min.js")
    assert asset.status_code == 200
    assert (
        hashlib.sha256(asset.content.replace(b"\r\n", b"\n")).hexdigest()
        == "69caefd0da92269066e725d7fe175e26b9d50c962e3056459c0c477154cdb9d3"
    )
    assert "Zero-Clause BSD" in client.get("/static/vendor/LICENSE.htmx").text


def production_settings(**overrides):
    return replace(
        load_settings(),
        app_env="production",
        session_secret="test-only-random-secret-with-more-than-32-characters",
        session_https_only=True,
        public_origin="https://cafe.example",
        allowed_hosts=("cafe.example", "localhost"),
        **overrides,
    )


def test_production_cookies_hsts_origin_and_docs():
    client = TestClient(
        create_app(FakeGateway(), production_settings()),
        base_url="https://cafe.example",
    )
    initial = client.get("/")
    token = re.search(r'name="csrf-token" content="([^"]+)"', initial.text)[1]
    csrf_cookie = next(
        cookie
        for cookie in initial.headers.get_list("set-cookie")
        if cookie.startswith("__Host-cafeteria_csrf=")
    )
    for flag in ("HttpOnly", "Secure", "SameSite=lax", "Path=/", "Max-Age=86400"):
        assert flag.lower() in csrf_cookie.lower()
    assert "Domain=" not in csrf_cookie
    response = client.get("/")
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("__Host-cafeteria_session=")
    for flag in ("HttpOnly", "Secure", "SameSite=lax", "Path=/", "Max-Age=86400"):
        assert flag.lower() in cookie.lower()
    assert "Domain=" not in cookie
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000"
    assert (
        client.post(
            "/cart/items/1",
            data={"csrf_token": token},
            headers={"Origin": "https://cafe.example"},
            follow_redirects=False,
        ).status_code
        == 303
    )
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


@pytest.mark.parametrize(
    "changes",
    [
        {"session_secret": "short"},
        {"session_secret": "local-development-only-change-before-deploying"},
        {"session_https_only": False},
        {"public_origin": "http://cafe.example"},
        {"public_origin": ""},
        {"allowed_hosts": ("*",)},
        {"public_origin": "https://other.example"},
        {"public_origin": "https://cafe.example/path"},
    ],
)
def test_unsafe_production_configuration_fails_early(changes):
    settings = production_settings()
    with pytest.raises(ValueError):
        replace(settings, **changes)


def test_unhandled_error_has_safe_body_and_headers():
    class BrokenGateway(FakeGateway):
        def list_products(self, **kwargs):
            raise RuntimeError("private-secret-diagnostic")

    client = TestClient(create_app(BrokenGateway()), raise_server_exceptions=False)
    response = client.get("/")
    assert response.status_code == 500
    assert "private-secret" not in response.text
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.json()["trace_id"]
