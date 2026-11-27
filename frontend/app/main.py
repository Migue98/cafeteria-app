"""Construcción y configuración de la aplicación web de la cafetería."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .clients import BackendGateway, HttpBackendGateway
from .config import Settings, load_settings
from .error_handlers import install_error_handlers, invalid_request_id
from .metrics import HTTP_DURATION, HTTP_REQUESTS
from .observability import Telemetry, create_telemetry, get_logger, install_observability
from .presentation import create_templates
from .routes import router
from .security import CSRFMiddleware, SecurityHeadersMiddleware

LOGGER = get_logger("frontend")
BASE_DIR = Path(__file__).resolve().parent


def create_app(
    gateway: BackendGateway | None = None,
    settings: Settings | None = None,
    *,
    telemetry: Telemetry | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    telemetry = telemetry or create_telemetry(LOGGER.name, settings.app_version)
    backend = gateway or HttpBackendGateway(settings, tracer_provider=telemetry.provider)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
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
    application.state.templates = create_templates()
    application.add_middleware(CSRFMiddleware, settings=settings)
    application.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie=(
            "__Host-cafeteria_session" if settings.app_env == "production" else "cafeteria_session"
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
    application.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    install_error_handlers(application, settings)
    install_observability(
        application,
        logger=LOGGER,
        requests=HTTP_REQUESTS,
        duration=HTTP_DURATION,
        invalid_response=invalid_request_id,
        telemetry=telemetry,
    )
    application.add_middleware(SecurityHeadersMiddleware, settings=settings)
    application.include_router(router)
    return application


app = create_app()
