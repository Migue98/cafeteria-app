"""Configuración del frontend obtenida del entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    menu_url: str
    orders_url: str
    loyalty_url: str
    http_timeout_seconds: float
    session_secret: str
    session_https_only: bool
    app_version: str


def load_settings() -> Settings:
    return Settings(
        menu_url=os.getenv("MENU_URL", "http://localhost:8001").rstrip("/"),
        orders_url=os.getenv("ORDERS_URL", "http://localhost:8002").rstrip("/"),
        loyalty_url=os.getenv("LOYALTY_URL", "http://localhost:8003").rstrip("/"),
        http_timeout_seconds=float(os.getenv("HTTP_TIMEOUT_SECONDS", "3")),
        session_secret=os.getenv(
            "SESSION_SECRET", "local-development-only-change-before-deploying"
        ),
        session_https_only=_as_bool(os.getenv("SESSION_HTTPS_ONLY", "false")),
        app_version=os.getenv("APP_VERSION", "dev"),
    )
