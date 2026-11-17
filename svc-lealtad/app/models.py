"""Modelos públicos del servicio de lealtad."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EarnPointsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: UUID
    customer_id: UUID
    amount_cents: int = Field(ge=1)
    currency: Literal["MXN"] = "MXN"
    occurred_at: datetime | None = None


class PointAward(BaseModel):
    model_config = ConfigDict(extra="forbid")

    movement_id: UUID
    order_id: UUID
    customer_id: UUID
    points_earned: int = Field(ge=0)
    balance: int = Field(ge=0)
    rule: Literal["1-point-per-10-mxn-v1"] = "1-point-per-10-mxn-v1"
    replayed: bool = False
    awarded_at: datetime


class PointsBalance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: UUID
    balance: int = Field(ge=0)
    updated_at: datetime | None


class DependencyHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["up", "down"]
    latency_ms: float | None = Field(default=None, ge=0)


class HealthDependencies(BaseModel):
    postgres: DependencyHealth


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: Literal["svc-lealtad"] = "svc-lealtad"
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
