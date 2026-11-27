"""Construcción y ciclo de vida de la aplicación del servicio de pedidos."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from .clients import HttpLoyaltyClient, HttpMenuClient, LoyaltyClient, MenuClient
from .config import load_settings
from .error_handlers import install_error_handlers, invalid_request_id
from .loyalty_retry import loyalty_retry_loop
from .metrics import HTTP_DURATION, HTTP_REQUESTS
from .observability import Telemetry, create_telemetry, get_logger, install_observability
from .repository import OrderRepository, PostgresOrderRepository
from .routes import router

LOGGER = get_logger("svc-pedidos")


def create_app(
    repository: OrderRepository | None = None,
    menu_client: MenuClient | None = None,
    loyalty_client: LoyaltyClient | None = None,
    *,
    telemetry: Telemetry | None = None,
) -> FastAPI:
    settings = load_settings()
    telemetry = telemetry or create_telemetry(LOGGER.name, settings.app_version)
    configured_repository = repository or PostgresOrderRepository(
        settings.database_url, tracer_provider=telemetry.provider
    )
    configured_menu_client = menu_client or HttpMenuClient(
        settings.menu_url, settings.http_timeout_seconds, tracer_provider=telemetry.provider
    )
    configured_loyalty_client = loyalty_client or HttpLoyaltyClient(
        settings.loyalty_url, settings.http_timeout_seconds, tracer_provider=telemetry.provider
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        retry_task: asyncio.Task[None] | None = None
        if settings.loyalty_retry_enabled:
            retry_task = asyncio.create_task(
                loyalty_retry_loop(
                    configured_repository,
                    configured_loyalty_client,
                    interval_seconds=settings.loyalty_retry_interval_seconds,
                    batch_size=settings.loyalty_retry_batch_size,
                    tracer=telemetry.tracer,
                ),
                name="loyalty-retry",
            )
        app.state.loyalty_retry_task = retry_task
        try:
            yield
        finally:
            if retry_task is not None:
                retry_task.cancel()
                with suppress(asyncio.CancelledError):
                    await retry_task
            if menu_client is None:
                configured_menu_client.close()
            if loyalty_client is None:
                configured_loyalty_client.close()

    application = FastAPI(
        title="Cafetería - Servicio de pedidos",
        version="0.1.0",
        description="Creación, persistencia y consulta de pedidos.",
        lifespan=lifespan,
    )
    application.state.repository = configured_repository
    application.state.menu_client = configured_menu_client
    application.state.loyalty_client = configured_loyalty_client
    application.state.app_version = settings.app_version
    install_observability(
        application,
        logger=LOGGER,
        requests=HTTP_REQUESTS,
        duration=HTTP_DURATION,
        invalid_response=invalid_request_id,
        telemetry=telemetry,
    )
    install_error_handlers(application)
    application.include_router(router)
    return application


app = create_app()
