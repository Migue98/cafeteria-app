"""Configuración del servicio obtenida del entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    menu_url: str
    loyalty_url: str
    app_version: str
    http_timeout_seconds: float


def load_settings() -> Settings:
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql://cafeteria:cafeteria@localhost:5432/cafeteria",
        ),
        menu_url=os.getenv("MENU_URL", "http://localhost:8001"),
        loyalty_url=os.getenv("LOYALTY_URL", "http://localhost:8003"),
        app_version=os.getenv("APP_VERSION", "dev"),
        http_timeout_seconds=float(os.getenv("HTTP_TIMEOUT_SECONDS", "3")),
    )
