"""Configuración del frontend obtenida del entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit


def _as_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("Se esperaba un valor booleano")


@dataclass(frozen=True, slots=True)
class Settings:
    menu_url: str
    orders_url: str
    loyalty_url: str
    http_timeout_seconds: float
    session_secret: str
    session_https_only: bool
    app_version: str
    app_env: str = "development"
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "[::1]", "testserver")
    public_origin: str = ""
    session_max_age_seconds: int = 86400

    def __post_init__(self) -> None:
        if self.app_env not in {"development", "test", "production"}:
            raise ValueError("APP_ENV debe ser development, test o production")
        if self.session_max_age_seconds <= 0:
            raise ValueError("SESSION_MAX_AGE_SECONDS debe ser mayor que cero")
        if not self.allowed_hosts or any(
            not host or "*" in host or "/" in host or " " in host
            for host in self.allowed_hosts
        ):
            raise ValueError(
                "ALLOWED_HOSTS debe contener hosts explícitos, sin comodines"
            )
        if self.public_origin:
            parsed = urlsplit(self.public_origin)
            origin_port = parsed.port  # También rechaza puertos inválidos al iniciar.
            if (
                parsed.scheme not in {"http", "https"}
                or origin_port == 0
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "PUBLIC_ORIGIN debe ser un origen sin ruta ni credenciales"
                )
            if parsed.hostname not in self.allowed_hosts:
                raise ValueError("El host de PUBLIC_ORIGIN debe estar en ALLOWED_HOSTS")
        if self.app_env == "production":
            if len(self.session_secret) < 32 or self.session_secret.startswith(
                "local-development"
            ):
                raise ValueError(
                    "Producción requiere SESSION_SECRET aleatorio de al menos 32 caracteres"
                )
            if not self.session_https_only:
                raise ValueError("Producción requiere SESSION_HTTPS_ONLY=true")
            if not self.public_origin.startswith("https://"):
                raise ValueError("Producción requiere PUBLIC_ORIGIN con HTTPS")


def load_settings() -> Settings:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    if app_env == "production" and not os.getenv("ALLOWED_HOSTS", "").strip():
        raise ValueError("Producción requiere ALLOWED_HOSTS explícito")
    return Settings(
        menu_url=os.getenv("MENU_URL", "http://localhost:8001").rstrip("/"),
        orders_url=os.getenv("ORDERS_URL", "http://localhost:8002").rstrip("/"),
        loyalty_url=os.getenv("LOYALTY_URL", "http://localhost:8003").rstrip("/"),
        http_timeout_seconds=float(os.getenv("HTTP_TIMEOUT_SECONDS", "3")),
        session_secret=os.getenv(
            "SESSION_SECRET", "local-development-only-change-before-deploying"
        ),
        session_https_only=_as_bool(
            os.getenv(
                "SESSION_HTTPS_ONLY", "true" if app_env == "production" else "false"
            )
        ),
        app_version=os.getenv("APP_VERSION", "dev"),
        app_env=app_env,
        allowed_hosts=tuple(
            host.strip().lower()
            for host in os.getenv(
                "ALLOWED_HOSTS", "localhost,127.0.0.1,[::1],testserver"
            ).split(",")
        ),
        public_origin=os.getenv("PUBLIC_ORIGIN", "").rstrip("/"),
        session_max_age_seconds=int(os.getenv("SESSION_MAX_AGE_SECONDS", "86400")),
    )
