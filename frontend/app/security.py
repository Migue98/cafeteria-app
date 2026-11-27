"""Integra CSRF de biblioteca y defensas del frontend sin estado por réplica."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from fastapi_csrf_protect import CsrfProtect
from fastapi_csrf_protect.exceptions import CsrfProtectError
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import Settings

MAX_FORM_BYTES = 8192
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
    "frame-src 'none'; frame-ancestors 'none'; form-action 'self'"
)


def security_headers(settings: Settings) -> dict[str, str]:
    headers = {
        "Content-Security-Policy": CSP,
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    }
    if settings.app_env == "production":
        headers["Strict-Transport-Security"] = "max-age=31536000"
    return headers


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.headers = security_headers(settings)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.update(self.headers)
                if not scope["path"].startswith("/static/"):
                    headers["Cache-Control"] = (
                        "no-store"
                        if scope["path"] in {"/livez", "/readyz"}
                        else "private, no-store"
                    )
            await send(message)

        await self.app(scope, receive, send_headers)


def _origin(value: str) -> tuple[str, str, int | None] | None:
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        return (
            parsed.scheme,
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
        )
    except ValueError:
        return None


class CSRFMiddleware:
    """Adapta formularios y sesiones a fastapi-csrf-protect antes de las rutas."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

        # load_config configura la clase: aislarla evita compartir secretos entre apps.
        class AppCsrfProtect(CsrfProtect):
            pass

        AppCsrfProtect.load_config(
            lambda: [
                ("secret_key", settings.session_secret),
                (
                    "cookie_key",
                    "__Host-cafeteria_csrf"
                    if settings.app_env == "production"
                    else "cafeteria_csrf",
                ),
                ("cookie_secure", settings.session_https_only),
                ("cookie_samesite", "lax"),
                ("httponly", True),
                ("max_age", settings.session_max_age_seconds),
                ("token_location", "header"),
                ("header_name", "X-CSRF-Token"),
            ]
        )
        self.csrf = AppCsrfProtect()

    @staticmethod
    def _token_request(scope: Scope, token: str) -> Request:
        # El formulario se adapta a la API de cabecera; la biblioteca valida todo
        # token, firma y caducidad. No se altera la petición que recibe la ruta.
        headers = MutableHeaders(raw=list(scope["headers"]))
        headers["X-CSRF-Token"] = token
        return Request({**scope, "headers": headers.raw})

    async def _valid_session_token(self, scope: Scope) -> bool:
        token = scope["session"].get("csrf_token")
        if not isinstance(token, str):
            return False
        try:
            await self.csrf.validate_csrf(self._token_request(scope, token))
        except CsrfProtectError:
            return False
        return True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        session = scope["session"]
        headers = Headers(scope=scope)
        if scope["method"] in SAFE_METHODS:
            cookie_headers: list[tuple[bytes, bytes]] = []
            if (
                scope["path"] not in {"/health", "/metrics"}
                and not scope["path"].startswith("/static/")
                and not await self._valid_session_token(scope)
            ):
                token, signed_token = self.csrf.generate_csrf_tokens()
                session["csrf_token"] = token
                cookie_response = Response()
                self.csrf.set_csrf_cookie(signed_token, cookie_response)
                cookie_headers = [
                    (name, value)
                    for name, value in cookie_response.raw_headers
                    if name == b"set-cookie"
                ]

            async def send_cookie(message: Message) -> None:
                if message["type"] == "http.response.start":
                    message.setdefault("headers", []).extend(cookie_headers)
                await send(message)

            await self.app(scope, receive, send_cookie)
            return

        async def reject(status: int = 403) -> None:
            await JSONResponse(
                {
                    "title": "Solicitud rechazada",
                    "detail": "Recarga el menú y vuelve a intentarlo.",
                    "status": status,
                    "code": "CSRF_REJECTED" if status == 403 else "FORM_TOO_LARGE",
                    "trace_id": scope.get("state", {}).get("trace_id"),
                },
                status_code=status,
            )(scope, receive, send)

        if (
            not await self._valid_session_token(scope)
            or headers.get("sec-fetch-site") == "cross-site"
        ):
            await reject()
            return
        target = self.settings.public_origin or str(Request(scope).base_url)
        source = headers.get("origin")
        referer = headers.get("referer")
        if source is not None:
            try:
                parsed = urlsplit(source)
                valid_source = not parsed.path and not parsed.query and not parsed.fragment
            except ValueError:
                valid_source = False
            if not valid_source or _origin(source) is None or _origin(source) != _origin(target):
                await reject()
                return
        elif referer is not None and (
            _origin(referer) is None or _origin(referer) != _origin(target)
        ):
            await reject()
            return

        supplied = headers.get("x-csrf-token")
        try:
            if int(headers.get("content-length", "0")) > MAX_FORM_BYTES:
                await reject(413)
                return
        except ValueError:
            await reject()
            return
        body = bytearray()
        if (
            supplied is None
            and headers.get("content-type", "").split(";", 1)[0]
            != "application/x-www-form-urlencoded"
        ):
            await reject()
            return
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > MAX_FORM_BYTES:
                await reject(413)
                return
            if not message.get("more_body", False):
                break
        if supplied is None:
            try:
                values = parse_qs(body.decode("utf-8"), max_num_fields=50).get("csrf_token", [])
                supplied = values[0] if len(values) == 1 else ""
            except (UnicodeDecodeError, ValueError):
                supplied = ""

        if not supplied or not supplied.isascii():
            await reject()
            return
        try:
            await self.csrf.validate_csrf(self._token_request(scope, supplied))
        except CsrfProtectError:
            await reject()
            return

        delivered = False

        async def replay_body() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay_body, send)
