"""Configuración del servicio obtenida del entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    app_version: str


def load_settings() -> Settings:
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql://cafeteria:cafeteria@localhost:5432/cafeteria",
        ),
        app_version=os.getenv("APP_VERSION", "dev"),
    )
