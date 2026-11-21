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
    loyalty_retry_enabled: bool
    loyalty_retry_interval_seconds: float
    loyalty_retry_batch_size: int


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} debe ser un booleano")


def _positive_float(name: str, default: str) -> float:
    value = float(os.getenv(name, default))
    if value <= 0:
        raise ValueError(f"{name} debe ser mayor que cero")
    return value


def _positive_int(name: str, default: str) -> int:
    value = int(os.getenv(name, default))
    if value <= 0:
        raise ValueError(f"{name} debe ser mayor que cero")
    return value


def load_settings() -> Settings:
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql://cafeteria:cafeteria@localhost:5432/cafeteria",
        ),
        menu_url=os.getenv("MENU_URL", "http://localhost:8001"),
        loyalty_url=os.getenv("LOYALTY_URL", "http://localhost:8003"),
        app_version=os.getenv("APP_VERSION", "dev"),
        http_timeout_seconds=_positive_float("HTTP_TIMEOUT_SECONDS", "3"),
        loyalty_retry_enabled=_boolean("LOYALTY_RETRY_ENABLED", True),
        loyalty_retry_interval_seconds=_positive_float("LOYALTY_RETRY_INTERVAL_SECONDS", "900"),
        loyalty_retry_batch_size=_positive_int("LOYALTY_RETRY_BATCH_SIZE", "100"),
    )
