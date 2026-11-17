"""Modelos públicos e internos del servicio de pedidos."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CreateOrderItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(ge=1)
    quantity: int = Field(ge=1, le=20)


class CreateOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: UUID
    items: list[CreateOrderItem] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def product_ids_must_be_unique(self) -> CreateOrderRequest:
        product_ids = [item.product_id for item in self.items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("product_id no puede repetirse")
        return self


class OrderItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(ge=1)
    sku: str
    product_name: str
    quantity: int = Field(ge=1)
    unit_price_cents: int = Field(ge=0)
    line_total_cents: int = Field(ge=0)


class Order(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    customer_id: UUID
    status: Literal["confirmed"] = "confirmed"
    loyalty_status: Literal["awarded", "pending"]
    points_earned: int | None = Field(default=None, ge=0)
    currency: Literal["MXN"] = "MXN"
    subtotal_cents: int = Field(ge=0)
    total_cents: int = Field(ge=0)
    items: list[OrderItem] = Field(min_length=1)
    replayed: bool = False
    created_at: datetime
    updated_at: datetime


class OrderList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Order]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class DependencyHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["up", "down"]
    critical: bool
    latency_ms: float | None = Field(default=None, ge=0)


class HealthDependencies(BaseModel):
    postgres: DependencyHealth
    menu: DependencyHealth
    loyalty: DependencyHealth


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: Literal["svc-pedidos"] = "svc-pedidos"
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


class MenuProduct(BaseModel):
    id: int
    sku: str
    name: str
    price_cents: int = Field(ge=0)
    currency: Literal["MXN"]
    available: bool
