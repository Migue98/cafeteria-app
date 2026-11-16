"""Modelos públicos del servicio de menú."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(ge=1)
    sku: str = Field(pattern=r"^[A-Z0-9-]{3,32}$")
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(max_length=500)
    category: str = Field(min_length=1, max_length=50)
    price_cents: int = Field(ge=0)
    currency: Literal["MXN"] = "MXN"
    available: bool
    image_url: str | None = Field(default=None, max_length=500)
    created_at: datetime
    updated_at: datetime


class ProductList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Product]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class DependencyHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["up", "down"]
    latency_ms: float | None = Field(default=None, ge=0)


class HealthDependencies(BaseModel):
    postgres: DependencyHealth


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: Literal["svc-menu"] = "svc-menu"
    status: Literal["healthy", "degraded"]
    version: str
    dependencies: HealthDependencies


class Problem(BaseModel):
    type: str
    title: str
    status: int = Field(ge=400, le=599)
    detail: str
    code: str = Field(pattern=r"^[A-Z0-9_]+$")
    trace_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    instance: str
    errors: list[dict[str, Any]] | None = None
